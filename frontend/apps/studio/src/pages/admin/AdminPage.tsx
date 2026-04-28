import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Button, Badge, Skeleton, Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
  RangeSlider,
} from "@reeve/ui";
import {
  Pencil, Trash2, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight,
  CheckCircle2, Loader2, PauseCircle, XCircle, ArrowUpDown, ArrowUp, ArrowDown,
} from "lucide-react";

import {
  getAnalyzedVehicles, getVehicleCounts, deleteAnalyzedVehicle, deleteAllUnverified,
  saveToTraining, getManufacturers, getVehicleModels, extractErrorMessage, streamBatchAction,
  type AnalyzedVehicle, type StatusFilter, type ReviewStatus, type ReviewSort,
  type BatchActionType, type BatchActionEvent,
} from "../../lib/api";
import { VehicleEditDialog } from "./VehicleEditDialog";
import { BatchSaveButton } from "./BatchSaveButton";

type TabKey =
  | "all"
  | "pending"
  | "on_hold"
  | "approved"
  | "rejected"
  | "uploaded"
  | "yolo_failed";

interface TabDef {
  key: TabKey;
  label: string;
  reviewStatus?: ReviewStatus;
  status?: StatusFilter;
}

const STATUS_TABS: TabDef[] = [
  { key: "all", label: "전체" },
  { key: "uploaded", label: "업로드", status: "uploaded" },
  { key: "yolo_failed", label: "YOLO 탐지실패", status: "yolo_failed" },
  { key: "pending", label: "검수 대기", status: "analysis_complete" },
  { key: "approved", label: "검수완료", reviewStatus: "approved" },
  { key: "on_hold", label: "보류", reviewStatus: "on_hold" },
  { key: "rejected", label: "반려", reviewStatus: "rejected" },
];

const PAGE_SIZE_OPTIONS = [10, 20, 50, 100] as const;

interface RowStatus {
  variant: "default" | "secondary" | "destructive" | "outline";
  label: string;
  rowClass?: string;
  badgeClass?: string;
}

function rowStatus(item: AnalyzedVehicle): RowStatus {
  switch (item.review_status) {
    case "approved":
      return { variant: "default", label: "검수완료" };
    case "on_hold":
      return {
        variant: "outline",
        label: "보류",
        rowClass: "bg-amber-50/40 dark:bg-amber-950/20",
        badgeClass: "border-amber-500 bg-amber-100 text-amber-900 dark:bg-amber-900/40 dark:text-amber-200",
      };
    case "rejected":
      return {
        variant: "secondary",
        label: "반려",
        rowClass: "opacity-60",
        badgeClass: "line-through",
      };
    case "pending":
    default: {
      const stage = item.processing_stage;
      if (stage === "uploaded") return { variant: "secondary", label: "업로드" };
      if (stage === "yolo_detected") {
        return item.yolo_detections?.length
          ? { variant: "outline", label: "감지완료" }
          : { variant: "destructive", label: "탐지실패" };
      }
      if (stage === "analysis_complete") {
        return item.manufacturer && item.model
          ? { variant: "default", label: "분석완료" }
          : { variant: "destructive", label: "분석실패" };
      }
      return { variant: "secondary", label: stage ?? "대기" };
    }
  }
}

function ConfidenceGauge({ value }: { value: number | null }) {
  if (value == null) return <span className="text-muted-foreground">-</span>;
  const v = Math.max(0, Math.min(100, value));
  const color = v >= 85 ? "bg-green-500" : v >= 60 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-muted">
        <div className={`h-full ${color}`} style={{ width: `${v}%` }} />
      </div>
      <span className="font-mono text-xs tabular-nums">{v.toFixed(0)}%</span>
    </div>
  );
}

interface ConfidencePreset {
  key: string;
  label: string;
  range: [number, number];
}

const CONFIDENCE_PRESETS: ConfidencePreset[] = [
  { key: "high", label: "고신뢰 ≥85", range: [85, 100] },
  { key: "mid", label: "애매 60~85", range: [60, 85] },
  { key: "low", label: "저신뢰 <60", range: [0, 60] },
];

interface BatchProgress {
  action: BatchActionType;
  current: number;
  total: number;
  succeeded: number;
  failed: number;
}

export function AdminPage() {
  const qc = useQueryClient();
  const [tabKey, setTabKey] = useState<TabKey>("all");
  const [mfFilter, setMfFilter] = useState<number | undefined>(undefined);
  const [modelFilter, setModelFilter] = useState<number | undefined>(undefined);
  const [confidenceRange, setConfidenceRange] = useState<[number, number]>([0, 100]);
  const [sort, setSort] = useState<ReviewSort>("created_desc");
  const [pageSize, setPageSize] = useState<number>(20);
  const [page, setPage] = useState(0);
  const [editIndex, setEditIndex] = useState<number | null>(null);
  const [activeRow, setActiveRow] = useState<number | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [batchBusy, setBatchBusy] = useState<BatchActionType | "delete" | null>(null);
  const [batchProgress, setBatchProgress] = useState<BatchProgress | null>(null);
  const batchAbortRef = useRef<AbortController | null>(null);

  const tab: TabDef = STATUS_TABS.find((t) => t.key === tabKey) ?? STATUS_TABS[0]!;

  const minConf = confidenceRange[0] > 0 ? confidenceRange[0] : undefined;
  const maxConf = confidenceRange[1] < 100 ? confidenceRange[1] : undefined;

  const { data: counts } = useQuery({
    queryKey: ["vehicle-counts"],
    queryFn: getVehicleCounts,
    refetchInterval: 10_000,
  });

  const { data: manufacturers } = useQuery({
    queryKey: ["manufacturers"],
    queryFn: () => getManufacturers(),
  });

  const { data: vehicleModels } = useQuery({
    queryKey: ["vehicle-models", mfFilter],
    queryFn: () => getVehicleModels(mfFilter),
    enabled: mfFilter !== undefined,
  });

  const { data, isLoading } = useQuery({
    queryKey: ["analyzed-vehicles", tabKey, mfFilter, modelFilter, minConf, maxConf, sort, page, pageSize],
    queryFn: () => getAnalyzedVehicles({
      skip: page * pageSize,
      limit: pageSize,
      status: tab.status,
      review_status: tab.reviewStatus,
      manufacturer_id: mfFilter,
      model_id: modelFilter,
      min_confidence: minConf,
      max_confidence: maxConf,
      sort,
    }),
  });

  const items = data?.items ?? [];

  useEffect(() => {
    setSelected(new Set());
    setActiveRow(null);
  }, [page, tabKey, mfFilter, modelFilter, minConf, maxConf, sort, pageSize, data?.items]);

  const { mutateAsync: doDelete } = useMutation({
    mutationFn: deleteAnalyzedVehicle,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["analyzed-vehicles"] });
      void qc.invalidateQueries({ queryKey: ["vehicle-counts"] });
    },
  });

  const handleDelete = async (id: number) => {
    if (!confirm(`#${id} 삭제하시겠습니까? (이미지 파일과 학습 데이터도 함께 삭제)`)) return;
    try {
      await doDelete(id);
      toast.success("삭제되었습니다");
    } catch (e) {
      toast.error(extractErrorMessage(e));
    }
  };

  const handleDeleteAll = async () => {
    if (!confirm("미검수(승인 안 된) 전체를 삭제하시겠습니까? (보류/반려 포함, 복구 불가)")) return;
    try {
      const res = await deleteAllUnverified();
      await qc.invalidateQueries({ queryKey: ["analyzed-vehicles"] });
      await qc.invalidateQueries({ queryKey: ["vehicle-counts"] });
      toast.success(res.message);
    } catch (e) {
      toast.error(extractErrorMessage(e));
    }
  };

  const handleBulkDelete = async () => {
    if (selected.size === 0) { toast.error("선택된 항목이 없습니다"); return; }
    if (!confirm(`선택한 ${selected.size}개 항목을 삭제하시겠습니까? (복구 불가)`)) return;
    setBatchBusy("delete");
    let ok = 0, fail = 0;
    for (const id of selected) {
      try { await deleteAnalyzedVehicle(id); ok++; } catch { fail++; }
    }
    await qc.invalidateQueries({ queryKey: ["analyzed-vehicles"] });
    await qc.invalidateQueries({ queryKey: ["vehicle-counts"] });
    setSelected(new Set());
    setBatchBusy(null);
    if (fail === 0) toast.success(`삭제 완료: ${ok}개`);
    else toast.error(`삭제 완료: ${ok}개 (실패: ${fail}개)`);
  };

  const runBatchAction = async (action: BatchActionType, reason?: string) => {
    if (selected.size === 0) { toast.error("선택된 항목이 없습니다"); return; }
    const labelMap: Record<BatchActionType, string> = {
      approve: "검수 승인",
      hold: "보류",
      reject: "반려",
    };
    if (!confirm(`선택한 ${selected.size}개 항목을 ${labelMap[action]} 처리하시겠습니까?`)) return;

    const ids = Array.from(selected);
    const controller = new AbortController();
    batchAbortRef.current = controller;
    setBatchBusy(action);
    setBatchProgress({ action, current: 0, total: ids.length, succeeded: 0, failed: 0 });

    try {
      await streamBatchAction({ action, ids, reason }, (ev: BatchActionEvent) => {
        if (ev.type === "start") {
          setBatchProgress({ action, current: 0, total: ev.total, succeeded: 0, failed: 0 });
        } else if (ev.type === "progress") {
          setBatchProgress({
            action,
            current: ev.current,
            total: ev.total,
            succeeded: ev.succeeded,
            failed: ev.failed,
          });
        } else if (ev.type === "done") {
          setBatchProgress({
            action,
            current: ev.total,
            total: ev.total,
            succeeded: ev.succeeded,
            failed: ev.failed,
          });
          if (ev.failed === 0) toast.success(`${labelMap[action]} 완료: ${ev.succeeded}건`);
          else toast.error(`${labelMap[action]}: ${ev.succeeded}건 성공 / ${ev.failed}건 실패`);
        }
      }, controller.signal);
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        toast.error(extractErrorMessage(e));
      }
    } finally {
      await qc.invalidateQueries({ queryKey: ["analyzed-vehicles"] });
      await qc.invalidateQueries({ queryKey: ["vehicle-counts"] });
      setSelected(new Set());
      setBatchBusy(null);
      setTimeout(() => setBatchProgress(null), 2500);
    }
  };

  const handleBulkApprove = () => runBatchAction("approve");
  const handleBulkHold = () => {
    const reason = prompt("보류 사유 (선택):") ?? undefined;
    void runBatchAction("hold", reason || undefined);
  };
  const handleBulkReject = () => {
    const reason = prompt("반려 사유 (선택):") ?? undefined;
    void runBatchAction("reject", reason || undefined);
  };

  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / pageSize);

  const changeTab = (k: TabKey) => { setTabKey(k); setPage(0); };
  const changeMf = (v: string) => {
    setMfFilter(v === "all" ? undefined : Number(v));
    setModelFilter(undefined);
    setPage(0);
  };
  const changeModel = (v: string) => { setModelFilter(v === "all" ? undefined : Number(v)); setPage(0); };

  const applyPreset = (preset: ConfidencePreset) => {
    setConfidenceRange(preset.range);
    setPage(0);
  };

  const cycleSort = (field: "created" | "confidence") => {
    const desc: ReviewSort = field === "created" ? "created_desc" : "confidence_desc";
    const asc: ReviewSort = field === "created" ? "created_asc" : "confidence_asc";
    setSort((cur) => (cur === desc ? asc : desc));
    setPage(0);
  };

  const sortIcon = (field: "created" | "confidence") => {
    const desc: ReviewSort = field === "created" ? "created_desc" : "confidence_desc";
    const asc: ReviewSort = field === "created" ? "created_asc" : "confidence_asc";
    if (sort === desc) return <ArrowDown className="h-3 w-3" />;
    if (sort === asc) return <ArrowUp className="h-3 w-3" />;
    return <ArrowUpDown className="h-3 w-3 opacity-40" />;
  };

  const allOnPageSelected = useMemo(
    () => items.length > 0 && items.every((it) => selected.has(it.id)),
    [items, selected],
  );

  const togglePageSelectAll = (checked: boolean) => {
    setSelected((prev) => {
      const next = new Set(prev);
      for (const it of items) {
        if (checked) next.add(it.id); else next.delete(it.id);
      }
      return next;
    });
  };

  const toggleOne = (id: number, checked: boolean) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (checked) next.add(id); else next.delete(id);
      return next;
    });
  };

  // Keyboard navigation: J/↓ next, K/↑ prev, Enter open, Space toggle select
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (!target) return;
      const tag = target.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || target.isContentEditable) return;
      if (editIndex !== null) return; // dialog will own keyboard

      if (items.length === 0) return;
      const cur = activeRow ?? -1;

      if (e.key === "j" || e.key === "ArrowDown") {
        e.preventDefault();
        setActiveRow(Math.min(items.length - 1, cur + 1));
      } else if (e.key === "k" || e.key === "ArrowUp") {
        e.preventDefault();
        setActiveRow(Math.max(0, cur === -1 ? 0 : cur - 1));
      } else if (e.key === "Enter" && activeRow !== null) {
        e.preventDefault();
        setEditIndex(activeRow);
      } else if (e.key === " " && activeRow !== null) {
        e.preventDefault();
        const id = items[activeRow]?.id;
        if (id !== undefined) toggleOne(id, !selected.has(id));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [items, activeRow, editIndex, selected]);

  const verifiedTotal = (counts?.approved ?? 0) + (counts?.rejected ?? 0);
  const overallTotal = counts?.all ?? 0;
  const progressPct = overallTotal > 0 ? Math.round((verifiedTotal / overallTotal) * 100) : 0;

  const currentVehicle = editIndex !== null ? items[editIndex] ?? null : null;

  return (
    <div className="mx-auto max-w-7xl p-6">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <h1 className="text-xl font-semibold">차량데이터 관리</h1>
        <div className="flex flex-wrap gap-2">
          <BatchSaveButton />
          <Button variant="destructive" size="sm" onClick={() => void handleDeleteAll()}>
            <Trash2 className="mr-1 h-4 w-4" /> 미검수 전체 삭제
          </Button>
        </div>
      </div>

      {/* Stats cards */}
      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard label="전체" value={overallTotal} />
        <StatCard
          label="검수 진행률"
          value={`${progressPct}%`}
          hint={`승인 ${counts?.approved ?? 0} · 반려 ${counts?.rejected ?? 0}`}
        />
        <StatCard
          label="평균 신뢰도"
          value={counts?.avg_confidence != null ? `${counts.avg_confidence.toFixed(1)}%` : "-"}
          hint={`고 ${counts?.high_confidence ?? 0} · 중 ${counts?.mid_confidence ?? 0} · 저 ${counts?.low_confidence ?? 0}`}
        />
        <StatCard label="보류" value={counts?.on_hold ?? 0} hint="추가 검토 대기" tone="amber" />
      </div>

      {/* Status tabs */}
      <div className="mb-4 flex flex-wrap gap-1">
        {STATUS_TABS.map((t) => {
          const cnt = (() => {
            switch (t.key) {
              case "all": return counts?.all ?? 0;
              case "pending": return counts?.analysis_complete ?? 0;
              case "on_hold": return counts?.on_hold ?? 0;
              case "approved": return counts?.approved ?? 0;
              case "rejected": return counts?.rejected ?? 0;
              case "uploaded": return counts?.uploaded ?? 0;
              case "yolo_failed": return counts?.yolo_failed ?? 0;
            }
          })();
          const active = tabKey === t.key;
          return (
            <button
              key={t.key}
              type="button"
              onClick={() => changeTab(t.key)}
              className={`flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm transition ${
                active
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-border hover:border-primary/50 hover:bg-muted/50"
              }`}
            >
              {t.label}
              <span className={`rounded-full px-1.5 py-0.5 text-xs font-medium ${
                active ? "bg-white/20 text-white" : "bg-muted text-muted-foreground"
              }`}>
                {cnt}
              </span>
            </button>
          );
        })}
      </div>

      {/* Filters */}
      <div className="mb-3 space-y-2">
        <div className="flex flex-wrap items-end gap-2">
          {/* 제조사 */}
          <div className="flex flex-col gap-1">
            <span className="text-xs text-muted-foreground">제조사</span>
            <Select value={mfFilter !== undefined ? String(mfFilter) : "all"} onValueChange={changeMf}>
              <SelectTrigger className="w-44">
                <SelectValue placeholder="전체 제조사" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">전체 제조사</SelectItem>
                {manufacturers?.map((m) => (
                  <SelectItem key={m.id} value={String(m.id)}>{m.korean_name} ({m.code})</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* 모델 — 제조사 선택 시 활성화 */}
          <div className="flex flex-col gap-1">
            <span className="text-xs text-muted-foreground">모델</span>
            <Select
              value={modelFilter !== undefined ? String(modelFilter) : "all"}
              onValueChange={changeModel}
              disabled={mfFilter === undefined}
            >
              <SelectTrigger className="w-44">
                <SelectValue placeholder={mfFilter === undefined ? "제조사 먼저 선택" : "전체 모델"} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">전체 모델</SelectItem>
                {vehicleModels?.map((m) => (
                  <SelectItem key={m.id} value={String(m.id)}>{m.korean_name} ({m.code})</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* 신뢰도 슬라이더 */}
          <div className="flex min-w-[220px] flex-1 flex-col gap-1">
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">신뢰도 (%)</span>
              <span className="font-mono text-xs tabular-nums text-muted-foreground">
                {confidenceRange[0]} ~ {confidenceRange[1]}
              </span>
            </div>
            <RangeSlider
              min={0}
              max={100}
              values={confidenceRange}
              onChange={(v) => { setConfidenceRange(v); setPage(0); }}
              ariaLabelMin="최소 신뢰도"
              ariaLabelMax="최대 신뢰도"
            />
          </div>

          {/* 프리셋 + 초기화 */}
          <div className="flex flex-wrap items-center gap-1">
            {CONFIDENCE_PRESETS.map((p) => {
              const active = confidenceRange[0] === p.range[0] && confidenceRange[1] === p.range[1];
              return (
                <button
                  key={p.key}
                  type="button"
                  onClick={() => applyPreset(p)}
                  className={`rounded-full border px-3 py-1 text-xs transition ${
                    active ? "border-primary bg-primary/10 text-primary" : "border-border hover:bg-muted"
                  }`}
                >
                  {p.label}
                </button>
              );
            })}
            {(confidenceRange[0] !== 0 || confidenceRange[1] !== 100 || mfFilter !== undefined) && (
              <button
                type="button"
                onClick={() => { setConfidenceRange([0, 100]); setMfFilter(undefined); setModelFilter(undefined); setPage(0); }}
                className="rounded-full border border-border px-3 py-1 text-xs text-muted-foreground hover:bg-muted"
              >
                초기화
              </button>
            )}
          </div>

          <span className="ml-auto self-end text-sm text-muted-foreground">총 {total}개</span>
        </div>
      </div>

      {/* Bulk actions */}
      {selected.size > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-2 rounded-md border border-primary/30 bg-primary/5 px-3 py-2">
          <span className="text-sm font-medium">{selected.size}개 선택</span>
          <Button size="sm" variant="secondary" disabled={batchBusy !== null} onClick={() => void handleBulkApprove()}>
            {batchBusy === "approve" ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <CheckCircle2 className="mr-1 h-4 w-4" />}
            일괄 승인
          </Button>
          <Button size="sm" variant="outline" disabled={batchBusy !== null} onClick={handleBulkHold}>
            {batchBusy === "hold" ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <PauseCircle className="mr-1 h-4 w-4" />}
            일괄 보류
          </Button>
          <Button size="sm" variant="outline" disabled={batchBusy !== null} onClick={handleBulkReject}>
            {batchBusy === "reject" ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <XCircle className="mr-1 h-4 w-4" />}
            일괄 반려
          </Button>
          <Button size="sm" variant="destructive" disabled={batchBusy !== null} onClick={() => void handleBulkDelete()}>
            {batchBusy === "delete" ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Trash2 className="mr-1 h-4 w-4" />}
            삭제
          </Button>
        </div>
      )}

      {batchProgress && (
        <div className="mb-3 space-y-1 rounded-md border bg-muted/30 px-3 py-2">
          <div className="flex items-center justify-between text-xs">
            <span>일괄 처리 중 ({batchProgress.action})</span>
            <span className="font-mono">
              {batchProgress.current}/{batchProgress.total} · 성공 {batchProgress.succeeded} · 실패 {batchProgress.failed}
            </span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
            <div
              className="h-full bg-primary transition-all"
              style={{
                width: `${batchProgress.total > 0 ? (batchProgress.current / batchProgress.total) * 100 : 0}%`,
              }}
            />
          </div>
        </div>
      )}

      {/* Table */}
      <div className="rounded-md border">
        <table className="w-full text-sm">
          <thead className="border-b bg-muted/50">
            <tr>
              <th className="w-10 px-3 py-3 text-left">
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-input accent-primary"
                  checked={allOnPageSelected}
                  onChange={(e) => togglePageSelectAll(e.target.checked)}
                  aria-label="전체 선택"
                />
              </th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">이미지</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">상태</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                <button type="button" onClick={() => cycleSort("confidence")} className="inline-flex items-center gap-1 hover:text-foreground">
                  신뢰도 {sortIcon("confidence")}
                </button>
              </th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">제조사 / 모델</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">시각적 근거</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                <button type="button" onClick={() => cycleSort("created")} className="inline-flex items-center gap-1 hover:text-foreground">
                  등록일 {sortIcon("created")}
                </button>
              </th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">작업</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: 10 }).map((_, i) => (
                <tr key={i} className="border-b">
                  {Array.from({ length: 8 }).map((__, j) => (
                    <td key={j} className="px-4 py-3"><Skeleton className="h-4 w-full" /></td>
                  ))}
                </tr>
              ))
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-4 py-10 text-center text-muted-foreground">
                  데이터가 없습니다
                </td>
              </tr>
            ) : (
              items.map((item, idx) => {
                const si = rowStatus(item);
                const imgPath = item.original_image_path ?? item.image_path;
                const imgSrc = imgPath ? `/${imgPath}` : "";
                const date = item.created_at
                  ? new Date(item.created_at).toLocaleString("ko-KR", { dateStyle: "short", timeStyle: "short" })
                  : "-";
                const checked = selected.has(item.id);
                const evidence = item.raw_result?.visual_evidence?.trim() ?? "";
                const lowConfBorder = (item.confidence_score ?? 100) < 40
                  ? "border-l-2 border-l-red-500/70"
                  : "";
                const isActive = activeRow === idx;
                return (
                  <tr
                    key={item.id}
                    className={`cursor-pointer border-b transition-colors ${si.rowClass ?? ""} ${
                      isActive ? "ring-2 ring-inset ring-primary/40" : checked ? "bg-primary/5" : "hover:bg-muted/30"
                    } ${lowConfBorder}`}
                    onClick={() => setActiveRow(idx)}
                    onDoubleClick={() => setEditIndex(idx)}
                  >
                    <td className="px-3 py-2" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        className="h-4 w-4 rounded border-input accent-primary"
                        checked={checked}
                        onChange={(e) => toggleOne(item.id, e.target.checked)}
                        aria-label={`#${item.id} 선택`}
                      />
                    </td>
                    <td className="px-4 py-2">
                      {imgSrc ? (
                        <img
                          src={imgSrc}
                          alt=""
                          className="h-10 w-14 rounded object-cover"
                          onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = "none"; }}
                        />
                      ) : (
                        <span className="text-muted-foreground">-</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <Badge variant={si.variant} className={si.badgeClass}>{si.label}</Badge>
                      {item.review_status === "on_hold" && item.review_reason && (
                        <div className="mt-1 max-w-[160px] truncate text-xs text-amber-700 dark:text-amber-400" title={item.review_reason}>
                          {item.review_reason}
                        </div>
                      )}
                      {item.review_status === "rejected" && item.review_reason && (
                        <div className="mt-1 max-w-[160px] truncate text-xs text-muted-foreground" title={item.review_reason}>
                          {item.review_reason}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <ConfidenceGauge value={item.confidence_score} />
                    </td>
                    <td className="px-4 py-3">
                      <div>{item.manufacturer ?? <span className="text-muted-foreground">-</span>}</div>
                      <div className="text-xs text-muted-foreground">{item.model ?? "-"}</div>
                    </td>
                    <td className="px-4 py-3 align-top">
                      {evidence ? (
                        <div
                          className="max-w-[220px] truncate text-xs text-muted-foreground"
                          title={evidence}
                        >
                          {evidence}
                        </div>
                      ) : (
                        <span className="text-muted-foreground">-</span>
                      )}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-muted-foreground">{date}</td>
                    <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                      <div className="flex gap-1">
                        <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => setEditIndex(idx)}>
                          <Pencil className="h-3.5 w-3.5" />
                        </Button>
                        <Button size="icon" variant="ghost" className="h-7 w-7 text-destructive hover:text-destructive" onClick={() => void handleDelete(item.id)}>
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      <div className="mt-2 text-xs text-muted-foreground">
        키보드: ↓/J 다음 · ↑/K 이전 · Enter 열기 · Space 선택 · 다이얼로그: A 승인 · H 보류 · R 반려 · ←/→ 이전·다음
      </div>

      {/* Pagination */}
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        {/* 페이지당 표시 */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">페이지당</span>
          <Select value={String(pageSize)} onValueChange={(v) => { setPageSize(Number(v)); setPage(0); }}>
            <SelectTrigger className="h-8 w-20 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PAGE_SIZE_OPTIONS.map((n) => (
                <SelectItem key={n} value={String(n)}>{n}개</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* 페이지 버튼 */}
        {totalPages > 1 && (
          <div className="flex items-center gap-1">
            <Button size="icon" variant="outline" className="h-8 w-8" disabled={page === 0} onClick={() => setPage(0)}>
              <ChevronsLeft className="h-4 w-4" />
            </Button>
            <Button size="icon" variant="outline" className="h-8 w-8" disabled={page === 0} onClick={() => setPage(page - 1)}>
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <div className="flex gap-1">
              {Array.from({ length: Math.min(7, totalPages) }, (_, i) => {
                const start = Math.max(0, Math.min(page - 3, totalPages - 7));
                const p = start + i;
                if (p >= totalPages) return null;
                return (
                  <button
                    key={p}
                    type="button"
                    onClick={() => setPage(p)}
                    className={`h-8 min-w-[2rem] rounded-md border px-2 text-sm transition ${
                      p === page ? "border-primary bg-primary text-primary-foreground" : "border-border hover:bg-muted"
                    }`}
                  >
                    {p + 1}
                  </button>
                );
              })}
            </div>
            <Button size="icon" variant="outline" className="h-8 w-8" disabled={page >= totalPages - 1} onClick={() => setPage(page + 1)}>
              <ChevronRight className="h-4 w-4" />
            </Button>
            <Button size="icon" variant="outline" className="h-8 w-8" disabled={page >= totalPages - 1} onClick={() => setPage(totalPages - 1)}>
              <ChevronsRight className="h-4 w-4" />
            </Button>
          </div>
        )}

        <span className="text-sm text-muted-foreground">{page + 1}/{Math.max(1, totalPages)} · 총 {total}개</span>
      </div>

      <VehicleEditDialog
        vehicle={currentVehicle}
        open={currentVehicle !== null}
        onClose={() => setEditIndex(null)}
        onPrev={editIndex !== null && editIndex > 0 ? () => setEditIndex(editIndex - 1) : undefined}
        onNext={editIndex !== null && editIndex < items.length - 1 ? () => setEditIndex(editIndex + 1) : undefined}
        positionLabel={editIndex !== null ? `${editIndex + 1} / ${items.length}` : undefined}
      />
    </div>
  );
}

function StatCard({
  label, value, hint, tone,
}: {
  label: string;
  value: number | string;
  hint?: string;
  tone?: "amber";
}) {
  const accent = tone === "amber" ? "text-amber-700 dark:text-amber-400" : "";
  return (
    <div className="rounded-md border bg-card px-3 py-2">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={`text-xl font-semibold tabular-nums ${accent}`}>{value}</div>
      {hint && <div className="mt-0.5 text-xs text-muted-foreground">{hint}</div>}
    </div>
  );
}
