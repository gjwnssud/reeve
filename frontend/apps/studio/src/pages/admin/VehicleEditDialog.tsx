import { useState, useEffect, useCallback, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Button, Input, Label, Dialog, DialogContent, DialogHeader, DialogTitle,
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue, Badge,
} from "@reeve/ui";
import { BboxCanvas } from "@reeve/ui/composites";
import {
  Loader2, RefreshCw, Save, Plus, CheckCircle2, PauseCircle, XCircle,
  ChevronLeft, ChevronRight, AlertTriangle, Eye,
} from "lucide-react";

import {
  getManufacturers, getVehicleModels, createManufacturer, createVehicleModel,
  updateAnalyzedVehicle, saveToTraining, reanalyzeVehicle,
  holdAnalyzedVehicle, rejectAnalyzedVehicle, reopenAnalyzedVehicle,
  extractErrorMessage, type AnalyzedVehicle,
} from "../../lib/api";
import { streamAnalyze } from "../../lib/analyzeApi";

type Bbox = [number, number, number, number];

interface Props {
  vehicle: AnalyzedVehicle | null;
  open: boolean;
  onClose: () => void;
  onPrev?: () => void;
  onNext?: () => void;
  positionLabel?: string;
}

const HOLD_REASON_CHIPS = ["차량 일부 가림", "조명 부족", "각도 모호", "동일 차량 중복"];
const REJECT_REASON_CHIPS = ["오탐 (차량 아님)", "잘못된 차종", "이미지 품질 불가", "라벨 모호"];

export function VehicleEditDialog({ vehicle, open, onClose, onPrev, onNext, positionLabel }: Props) {
  const qc = useQueryClient();
  const [bbox, setBbox] = useState<Bbox | null>(null);
  const [mfId, setMfId] = useState<number | null>(null);
  const [modelId, setModelId] = useState<number | null>(null);
  const [isReanalyzing, setReanalyzing] = useState(false);
  const [isReanalyzingBbox, setReanalyzingBbox] = useState(false);
  const [reanalyzeMsg, setReanalyzeMsg] = useState<{ text: string; ok: boolean } | null>(null);
  const [progressText, setProgressText] = useState<string | null>(null);
  const [inlineAddMf, setInlineAddMf] = useState(false);
  const [inlineAddModel, setInlineAddModel] = useState(false);
  const [newMfCode, setNewMfCode] = useState("");
  const [newMfKo, setNewMfKo] = useState("");
  const [newMfEn, setNewMfEn] = useState("");
  const [newModelCode, setNewModelCode] = useState("");
  const [newModelKo, setNewModelKo] = useState("");
  const [newModelEn, setNewModelEn] = useState("");
  const [reasonMode, setReasonMode] = useState<"hold" | "reject" | null>(null);
  const [reasonText, setReasonText] = useState("");
  const reasonInputRef = useRef<HTMLInputElement | null>(null);

  const { data: manufacturers } = useQuery({
    queryKey: ["manufacturers"],
    queryFn: () => getManufacturers(),
    enabled: open,
  });

  const { data: models } = useQuery({
    queryKey: ["vehicle-models", mfId],
    queryFn: () => getVehicleModels({ manufacturerId: mfId ?? undefined }),
    enabled: open && mfId != null,
  });

  useEffect(() => {
    if (!vehicle) return;
    setMfId(vehicle.matched_manufacturer_id);
    setModelId(vehicle.matched_model_id);
    setReanalyzeMsg(null);
    setProgressText(null);
    setInlineAddMf(false);
    setInlineAddModel(false);
    setReasonMode(null);
    setReasonText("");
    const initBbox: Bbox | null = vehicle.selected_bbox ?? (vehicle.yolo_detections?.[0]?.bbox ?? null);
    setBbox(initBbox);
  }, [vehicle]);

  const invalidate = useCallback(() => {
    void qc.invalidateQueries({ queryKey: ["analyzed-vehicles"] });
    void qc.invalidateQueries({ queryKey: ["vehicle-counts"] });
  }, [qc]);

  const { mutateAsync: patchVehicle, isPending: isSaving } = useMutation({
    mutationFn: ({ id, mfId, modelId }: { id: number; mfId: number; modelId: number }) =>
      updateAnalyzedVehicle(id, { matched_manufacturer_id: mfId, matched_model_id: modelId }),
    onSuccess: invalidate,
  });

  const { mutateAsync: approve, isPending: isApproving } = useMutation({
    mutationFn: (id: number) => saveToTraining(id),
    onSuccess: invalidate,
  });

  const { mutateAsync: hold, isPending: isHolding } = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason?: string }) => holdAnalyzedVehicle(id, reason),
    onSuccess: invalidate,
  });

  const { mutateAsync: reject, isPending: isRejecting } = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason?: string }) => rejectAnalyzedVehicle(id, reason),
    onSuccess: invalidate,
  });

  const { mutateAsync: reopen, isPending: isReopening } = useMutation({
    mutationFn: (id: number) => reopenAnalyzedVehicle(id),
    onSuccess: invalidate,
  });

  const advance = () => {
    if (onNext) onNext();
    else onClose();
  };

  const handleSave = async () => {
    if (!vehicle || !mfId || !modelId) {
      toast.error("제조사와 모델을 선택하세요");
      return;
    }
    try {
      const res = await patchVehicle({ id: vehicle.id, mfId, modelId });
      if (res.training_synced) {
        toast.success("학습 데이터에 즉시 반영됨");
      } else {
        toast.success("저장되었습니다");
      }
    } catch (e) {
      toast.error(extractErrorMessage(e));
    }
  };

  const handleApprove = async () => {
    if (!vehicle) return;
    if (!mfId || !modelId) {
      toast.error("제조사와 모델을 먼저 선택하세요");
      return;
    }
    try {
      // 변경된 매칭이 있으면 먼저 PATCH
      if (vehicle.matched_manufacturer_id !== mfId || vehicle.matched_model_id !== modelId) {
        await patchVehicle({ id: vehicle.id, mfId, modelId });
      }
      await approve(vehicle.id);
      toast.success("승인 완료");
      advance();
    } catch (e) {
      toast.error(extractErrorMessage(e));
    }
  };

  const submitHold = async () => {
    if (!vehicle) return;
    try {
      await hold({ id: vehicle.id, reason: reasonText.trim() || undefined });
      toast.success("보류 처리됨");
      advance();
    } catch (e) {
      toast.error(extractErrorMessage(e));
    }
  };

  const submitReject = async () => {
    if (!vehicle) return;
    try {
      await reject({ id: vehicle.id, reason: reasonText.trim() || undefined });
      toast.success("반려 처리됨");
      advance();
    } catch (e) {
      toast.error(extractErrorMessage(e));
    }
  };

  const handleReopen = async () => {
    if (!vehicle) return;
    try {
      await reopen(vehicle.id);
      toast.success("검수 대기로 되돌림");
    } catch (e) {
      toast.error(extractErrorMessage(e));
    }
  };

  const handleReanalyze = async () => {
    if (!vehicle) return;
    setReanalyzing(true);
    setReanalyzeMsg(null);
    setProgressText(null);
    try {
      const res = await reanalyzeVehicle(vehicle.id);
      const d = res.data;
      setReanalyzeMsg({ text: `${d.manufacturer ?? "-"} / ${d.model ?? "-"}`, ok: true });
      setMfId(d.matched_manufacturer_id);
      setModelId(d.matched_model_id);
      invalidate();
    } catch (e) {
      setReanalyzeMsg({ text: extractErrorMessage(e), ok: false });
    } finally {
      setReanalyzing(false);
    }
  };

  const handleReanalyzeBbox = async () => {
    if (!vehicle) return;
    const useBbox: Bbox = bbox ?? [0, 0, 1, 1];
    setReanalyzingBbox(true);
    setReanalyzeMsg(null);
    setProgressText("재분석 시작 중...");
    try {
      for await (const ev of streamAnalyze(vehicle.id, useBbox)) {
        if (ev.event === "progress") {
          setProgressText(ev.message);
        } else if (ev.event === "completed" && ev.result) {
          setMfId(ev.result.matched_manufacturer_id);
          setModelId(ev.result.matched_model_id);
          setReanalyzeMsg({
            text: `${ev.result.manufacturer ?? "-"} / ${ev.result.model ?? "-"}`,
            ok: true,
          });
          setProgressText(null);
          invalidate();
        } else if (ev.event === "error") {
          setReanalyzeMsg({ text: ev.message, ok: false });
          setProgressText(null);
        }
      }
    } catch (e) {
      setReanalyzeMsg({ text: extractErrorMessage(e), ok: false });
      setProgressText(null);
    } finally {
      setReanalyzingBbox(false);
    }
  };

  const handleAddMf = async () => {
    if (!newMfCode || !newMfKo || !newMfEn) { toast.error("모든 필드를 입력하세요"); return; }
    try {
      const mf = await createManufacturer({
        code: newMfCode.toUpperCase(), korean_name: newMfKo,
        english_name: newMfEn, is_domestic: false,
      });
      await qc.invalidateQueries({ queryKey: ["manufacturers"] });
      setMfId(mf.id);
      setInlineAddMf(false);
      setNewMfCode(""); setNewMfKo(""); setNewMfEn("");
      toast.success("제조사가 추가되었습니다");
    } catch (e) { toast.error(extractErrorMessage(e)); }
  };

  const handleAddModel = async () => {
    if (!mfId || !newModelCode || !newModelKo || !newModelEn) { toast.error("모든 필드를 입력하세요"); return; }
    const mf = manufacturers?.find((m) => m.id === mfId);
    if (!mf) return;
    try {
      const mdl = await createVehicleModel({
        code: newModelCode.toUpperCase(), korean_name: newModelKo,
        english_name: newModelEn, manufacturer_id: mfId,
        manufacturer_code: mf.code,
      });
      await qc.invalidateQueries({ queryKey: ["vehicle-models", mfId] });
      setModelId(mdl.id);
      setInlineAddModel(false);
      setNewModelCode(""); setNewModelKo(""); setNewModelEn("");
      toast.success("모델이 추가되었습니다");
    } catch (e) { toast.error(extractErrorMessage(e)); }
  };

  // Keyboard shortcuts within dialog
  useEffect(() => {
    if (!open || !vehicle) return;
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || target?.isContentEditable) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;

      if (e.key === "a" || e.key === "A") {
        e.preventDefault();
        if (mfId && modelId) void handleApprove();
      } else if (e.key === "h" || e.key === "H") {
        e.preventDefault();
        setReasonMode("hold");
        setTimeout(() => reasonInputRef.current?.focus(), 0);
      } else if (e.key === "r" || e.key === "R") {
        e.preventDefault();
        setReasonMode("reject");
        setTimeout(() => reasonInputRef.current?.focus(), 0);
      } else if (e.key === "ArrowLeft") {
        if (onPrev) { e.preventDefault(); onPrev(); }
      } else if (e.key === "ArrowRight") {
        if (onNext) { e.preventDefault(); onNext(); }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, vehicle, mfId, modelId, onPrev, onNext]);

  if (!vehicle) return null;

  const imageSrc = vehicle.original_image_path
    ? `/${vehicle.original_image_path}`
    : vehicle.image_path ? `/${vehicle.image_path}` : "";

  const yoloBboxes = (vehicle.yolo_detections ?? [])
    .map((d) => d.bbox)
    .filter(Boolean) as Bbox[];

  const visualEvidence = vehicle.raw_result?.visual_evidence?.trim() ?? "";
  const rawConf = typeof vehicle.raw_result?.confidence === "number" ? vehicle.raw_result.confidence : null;
  const finalConf = vehicle.confidence_score ?? null;
  const reviewStatus = vehicle.review_status;
  const isApproved = reviewStatus === "approved";
  const isOnHold = reviewStatus === "on_hold";
  const isRejected = reviewStatus === "rejected";
  const busy = isApproving || isHolding || isRejecting || isReopening || isSaving;

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose(); }} modal>
      <DialogContent
        className="max-h-[90vh] max-w-5xl overflow-y-auto"
        onPointerDownOutside={(e) => e.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle className="flex items-center justify-between gap-2">
            <span>차량데이터 편집 #{vehicle.id}</span>
            <div className="flex items-center gap-1.5 text-sm font-normal">
              {positionLabel && <span className="text-muted-foreground">{positionLabel}</span>}
              <Button size="icon" variant="ghost" className="h-7 w-7" disabled={!onPrev} onClick={onPrev}>
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button size="icon" variant="ghost" className="h-7 w-7" disabled={!onNext} onClick={onNext}>
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </DialogTitle>
        </DialogHeader>

        {/* 상태 배너 */}
        {isApproved && (
          <div className="mb-2 flex items-center gap-2 rounded-md border border-green-300 bg-green-50 px-3 py-2 text-sm text-green-800 dark:border-green-800 dark:bg-green-950/40 dark:text-green-300">
            <CheckCircle2 className="h-4 w-4" />
            <span>이 항목은 이미 학습셋에 포함됨. 제조사/모델을 수정 후 저장하면 즉시 학습 데이터와 동기화됩니다.</span>
          </div>
        )}
        {isOnHold && (
          <div className="mb-2 flex items-center gap-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
            <PauseCircle className="h-4 w-4" />
            <span>보류 중{vehicle.review_reason ? ` — 사유: ${vehicle.review_reason}` : ""}</span>
          </div>
        )}
        {isRejected && (
          <div className="mb-2 flex items-center gap-2 rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-800 dark:bg-red-950/40 dark:text-red-300">
            <XCircle className="h-4 w-4" />
            <span>반려됨{vehicle.review_reason ? ` — 사유: ${vehicle.review_reason}` : ""} (학습 데이터에서 제외)</span>
          </div>
        )}

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_360px]">
          {/* Canvas */}
          <div>
            <p className="mb-1 text-xs text-muted-foreground">
              기존 박스 드래그(이동/코너 조절) 또는 빈 영역 드래그(새 박스)
            </p>
            <BboxCanvas
              imageSrc={imageSrc}
              bbox={bbox}
              yoloDetections={yoloBboxes}
              editable
              onChange={setBbox}
            />
            {bbox && (
              <p className="mt-1 text-xs text-muted-foreground">
                [{bbox[0]}, {bbox[1]}, {bbox[2]}, {bbox[3]}] ({bbox[2] - bbox[0]}×{bbox[3] - bbox[1]}px)
              </p>
            )}
          </div>

          {/* Form */}
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              현재: {vehicle.manufacturer ?? "N/A"} / {vehicle.model ?? "N/A"}
            </p>

            {/* 신뢰도 + 시각적 근거 */}
            <div className="space-y-1.5 rounded-md border bg-muted/30 p-2.5 text-xs">
              <div className="flex items-center justify-between">
                <span className="font-medium">VLM 신뢰도</span>
                <span className="font-mono tabular-nums">
                  {rawConf != null ? `${(rawConf * 100).toFixed(1)}% (raw)` : "-"}
                  {finalConf != null && (
                    <> → <span className="text-foreground">{finalConf.toFixed(1)}%</span></>
                  )}
                </span>
              </div>
              {visualEvidence && (
                <div className="flex gap-1.5 text-muted-foreground">
                  <Eye className="mt-0.5 h-3 w-3 shrink-0" />
                  <p className="whitespace-pre-wrap break-words text-[11px] leading-relaxed">{visualEvidence}</p>
                </div>
              )}
              {!visualEvidence && (
                <p className="text-[11px] text-muted-foreground">시각적 근거 없음</p>
              )}
              {finalConf != null && finalConf < 60 && (
                <div className="flex items-center gap-1 text-amber-700 dark:text-amber-400">
                  <AlertTriangle className="h-3 w-3" />
                  <span>신뢰도가 낮습니다. 보류 또는 반려를 권장합니다.</span>
                </div>
              )}
            </div>

            {/* Manufacturer */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label>제조사</Label>
                <button type="button" onClick={() => setInlineAddMf(!inlineAddMf)} className="text-xs text-primary hover:underline">
                  {inlineAddMf ? "취소" : <><Plus className="inline h-3 w-3" /> 추가</>}
                </button>
              </div>
              {inlineAddMf ? (
                <div className="space-y-1.5 rounded-md border bg-muted/40 p-2">
                  <Input placeholder="코드 (예: HYUNDAI)" value={newMfCode} onChange={(e) => setNewMfCode(e.target.value)} />
                  <Input placeholder="한글명" value={newMfKo} onChange={(e) => setNewMfKo(e.target.value)} />
                  <Input placeholder="영문명" value={newMfEn} onChange={(e) => setNewMfEn(e.target.value)} />
                  <Button size="sm" className="w-full" onClick={handleAddMf}>저장</Button>
                </div>
              ) : (
                <Select value={mfId ? String(mfId) : ""} onValueChange={(v) => { setMfId(Number(v)); setModelId(null); }}>
                  <SelectTrigger><SelectValue placeholder="제조사 선택" /></SelectTrigger>
                  <SelectContent>
                    {manufacturers?.map((m) => (
                      <SelectItem key={m.id} value={String(m.id)}>{m.korean_name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>

            {/* Model */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label>차량 모델</Label>
                {mfId && (
                  <button type="button" onClick={() => setInlineAddModel(!inlineAddModel)} className="text-xs text-primary hover:underline">
                    {inlineAddModel ? "취소" : <><Plus className="inline h-3 w-3" /> 추가</>}
                  </button>
                )}
              </div>
              {inlineAddModel ? (
                <div className="space-y-1.5 rounded-md border bg-muted/40 p-2">
                  <Input placeholder="모델 코드" value={newModelCode} onChange={(e) => setNewModelCode(e.target.value)} />
                  <Input placeholder="한글명" value={newModelKo} onChange={(e) => setNewModelKo(e.target.value)} />
                  <Input placeholder="영문명" value={newModelEn} onChange={(e) => setNewModelEn(e.target.value)} />
                  <Button size="sm" className="w-full" onClick={handleAddModel}>저장</Button>
                </div>
              ) : (
                <Select value={modelId ? String(modelId) : ""} onValueChange={(v) => setModelId(Number(v))} disabled={!mfId}>
                  <SelectTrigger><SelectValue placeholder="모델 선택" /></SelectTrigger>
                  <SelectContent>
                    {models?.map((m) => (
                      <SelectItem key={m.id} value={String(m.id)}>{m.korean_name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>

            {progressText && (
              <p className="rounded bg-blue-50 p-2 text-xs text-blue-700 dark:bg-blue-950/30 dark:text-blue-400">
                {progressText}
              </p>
            )}
            {reanalyzeMsg && (
              <p className={`rounded p-2 text-xs ${reanalyzeMsg.ok ? "bg-green-50 text-green-700 dark:bg-green-950/30 dark:text-green-400" : "bg-red-50 text-red-700 dark:bg-red-950/30 dark:text-red-400"}`}>
                {reanalyzeMsg.ok ? "완료: " : "오류: "}{reanalyzeMsg.text}
              </p>
            )}

            {/* 사유 입력 영역 (보류/반려 클릭 시 표시) */}
            {reasonMode && (
              <div className="space-y-2 rounded-md border border-amber-300 bg-amber-50/60 p-2.5 dark:border-amber-700 dark:bg-amber-950/30">
                <Label className="text-xs">
                  {reasonMode === "hold" ? "보류 사유 (선택)" : "반려 사유 (선택)"}
                </Label>
                <Input
                  ref={reasonInputRef}
                  placeholder="이유를 입력하거나 아래 칩을 클릭"
                  value={reasonText}
                  onChange={(e) => setReasonText(e.target.value)}
                />
                <div className="flex flex-wrap gap-1">
                  {(reasonMode === "hold" ? HOLD_REASON_CHIPS : REJECT_REASON_CHIPS).map((chip) => (
                    <button
                      key={chip}
                      type="button"
                      onClick={() => setReasonText(chip)}
                      className="rounded-full border border-border bg-background px-2 py-0.5 text-xs hover:border-primary hover:bg-muted"
                    >
                      {chip}
                    </button>
                  ))}
                </div>
                <div className="flex gap-1.5">
                  <Button
                    size="sm"
                    variant={reasonMode === "hold" ? "outline" : "destructive"}
                    onClick={() => (reasonMode === "hold" ? submitHold() : submitReject())}
                    disabled={busy}
                    className="flex-1"
                  >
                    {reasonMode === "hold" ? "보류 확정" : "반려 확정"}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => { setReasonMode(null); setReasonText(""); }}>
                    취소
                  </Button>
                </div>
              </div>
            )}

            {/* 메인 액션 버튼들 */}
            {!reasonMode && (
              <div className="flex flex-col gap-2 pt-1">
                <Button
                  onClick={handleApprove}
                  disabled={busy || !mfId || !modelId}
                  className="w-full"
                >
                  {isApproving ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <CheckCircle2 className="mr-1 h-4 w-4" />}
                  승인 <Badge variant="outline" className="ml-2 px-1.5 py-0 text-[10px]">A</Badge>
                </Button>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    onClick={() => setReasonMode("hold")}
                    disabled={busy}
                    className="flex-1"
                  >
                    {isHolding ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <PauseCircle className="mr-1 h-4 w-4" />}
                    보류 <Badge variant="outline" className="ml-1 px-1.5 py-0 text-[10px]">H</Badge>
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => setReasonMode("reject")}
                    disabled={busy}
                    className="flex-1"
                  >
                    {isRejecting ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <XCircle className="mr-1 h-4 w-4" />}
                    반려 <Badge variant="outline" className="ml-1 px-1.5 py-0 text-[10px]">R</Badge>
                  </Button>
                </div>

                {(isApproved || isOnHold || isRejected) && (
                  <Button variant="ghost" onClick={handleReopen} disabled={busy} className="w-full text-muted-foreground">
                    {isReopening ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : null}
                    검수 대기로 되돌리기
                  </Button>
                )}

                <div className="my-1 h-px bg-border" />

                {!isApproved && (
                  <Button onClick={handleSave} disabled={isSaving || !mfId || !modelId} variant="secondary" className="w-full">
                    {isSaving ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Save className="mr-1 h-4 w-4" />}
                    매칭만 저장 (상태 유지)
                  </Button>
                )}
                <Button
                  variant="outline"
                  onClick={handleReanalyzeBbox}
                  disabled={isReanalyzingBbox || isReanalyzing || !bbox}
                  className="w-full"
                >
                  {isReanalyzingBbox ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-1 h-4 w-4" />}
                  재분석 (선택 영역)
                </Button>
                <Button
                  variant="outline"
                  onClick={handleReanalyze}
                  disabled={isReanalyzing || isReanalyzingBbox}
                  className="w-full"
                >
                  {isReanalyzing ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-1 h-4 w-4" />}
                  재분석 (기존 이미지)
                </Button>
                <Button variant="ghost" onClick={onClose} className="w-full">
                  닫기 <Badge variant="outline" className="ml-2 px-1.5 py-0 text-[10px]">Esc</Badge>
                </Button>
              </div>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
