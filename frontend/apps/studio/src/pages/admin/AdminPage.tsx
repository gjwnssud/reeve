import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button, Badge, Skeleton, Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@reeve/ui";
import { Pencil, Trash2, ChevronLeft, ChevronRight } from "lucide-react";

import {
  getAnalyzedVehicles, getVehicleCounts, deleteAnalyzedVehicle, deleteAllUnverified,
  getManufacturers, extractErrorMessage,
  type AnalyzedVehicle, type StatusFilter,
} from "../../lib/api";
import { VehicleEditDialog } from "./VehicleEditDialog";
import { BatchSaveButton } from "./BatchSaveButton";

const STATUS_TABS: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "전체" },
  { value: "uploaded", label: "업로드" },
  { value: "yolo_detected", label: "감지완료" },
  { value: "analysis_complete", label: "분석완료" },
  { value: "verified", label: "검증완료" },
];

const PAGE_SIZE = 20;

function statusInfo(item: AnalyzedVehicle): { variant: "default" | "secondary" | "destructive" | "outline"; label: string } {
  if (item.is_verified) return { variant: "default", label: "검증완료" };
  const s = item.processing_stage;
  if (s === "analysis_complete" || s === "verified") {
    return item.manufacturer && item.model
      ? { variant: "default", label: "분석완료" }
      : { variant: "destructive", label: "분석실패" };
  }
  if (s === "yolo_detected") {
    return item.yolo_detections?.length
      ? { variant: "outline", label: "감지완료" }
      : { variant: "destructive", label: "탐지실패" };
  }
  return { variant: "secondary", label: s ?? "업로드" };
}

export function AdminPage() {
  const qc = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [mfFilter, setMfFilter] = useState<number | undefined>(undefined);
  const [page, setPage] = useState(0);
  const [editVehicle, setEditVehicle] = useState<AnalyzedVehicle | null>(null);

  const { data: counts } = useQuery({
    queryKey: ["vehicle-counts"],
    queryFn: getVehicleCounts,
    refetchInterval: 10_000,
  });

  const { data: manufacturers } = useQuery({
    queryKey: ["manufacturers"],
    queryFn: () => getManufacturers(),
  });

  const { data, isLoading } = useQuery({
    queryKey: ["analyzed-vehicles", statusFilter, mfFilter, page],
    queryFn: () => getAnalyzedVehicles({
      skip: page * PAGE_SIZE,
      limit: PAGE_SIZE,
      status: statusFilter,
      manufacturer_id: mfFilter,
    }),
  });

  const { mutateAsync: doDelete } = useMutation({
    mutationFn: deleteAnalyzedVehicle,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["analyzed-vehicles"] });
      void qc.invalidateQueries({ queryKey: ["vehicle-counts"] });
    },
  });

  const handleDelete = async (id: number) => {
    if (!confirm(`#${id} 삭제하시겠습니까?`)) return;
    try {
      await doDelete(id);
      toast.success("삭제되었습니다");
    } catch (e) {
      toast.error(extractErrorMessage(e));
    }
  };

  const handleDeleteAll = async () => {
    if (!confirm("미검수 전체를 삭제하시겠습니까? (복구 불가)")) return;
    try {
      const res = await deleteAllUnverified();
      await qc.invalidateQueries({ queryKey: ["analyzed-vehicles"] });
      await qc.invalidateQueries({ queryKey: ["vehicle-counts"] });
      toast.success(res.message);
    } catch (e) {
      toast.error(extractErrorMessage(e));
    }
  };

  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / PAGE_SIZE);

  const changeTab = (s: StatusFilter) => { setStatusFilter(s); setPage(0); };
  const changeMf = (v: string) => { setMfFilter(v === "all" ? undefined : Number(v)); setPage(0); };

  return (
    <div className="mx-auto max-w-6xl p-6">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <h1 className="text-xl font-semibold">차량데이터 관리</h1>
        <div className="flex flex-wrap gap-2">
          <BatchSaveButton />
          <Button variant="destructive" size="sm" onClick={() => void handleDeleteAll()}>
            <Trash2 className="mr-1 h-4 w-4" /> 미검수 전체 삭제
          </Button>
        </div>
      </div>

      {/* Status tabs */}
      <div className="mb-4 flex flex-wrap gap-1">
        {STATUS_TABS.map(({ value, label }) => {
          const cnt = value === "all" ? (counts?.all ?? 0)
            : value === "uploaded" ? (counts?.uploaded ?? 0)
            : value === "yolo_detected" ? (counts?.yolo_detected ?? 0)
            : value === "analysis_complete" ? (counts?.analysis_complete ?? 0)
            : (counts?.verified ?? 0);
          return (
            <button
              key={value}
              type="button"
              onClick={() => changeTab(value)}
              className={`flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm transition ${
                statusFilter === value
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-border hover:border-primary/50 hover:bg-muted/50"
              }`}
            >
              {label}
              <span className={`rounded-full px-1.5 py-0.5 text-xs font-medium ${
                statusFilter === value ? "bg-white/20 text-white" : "bg-muted text-muted-foreground"
              }`}>
                {cnt}
              </span>
            </button>
          );
        })}
      </div>

      {/* Manufacturer filter */}
      <div className="mb-4 flex items-center gap-2">
        <Select value={mfFilter !== undefined ? String(mfFilter) : "all"} onValueChange={changeMf}>
          <SelectTrigger className="w-52">
            <SelectValue placeholder="전체 제조사" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">전체 제조사</SelectItem>
            {manufacturers?.map((m) => (
              <SelectItem key={m.id} value={String(m.id)}>{m.korean_name} ({m.code})</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="text-sm text-muted-foreground">총 {total}개</span>
      </div>

      {/* Table */}
      <div className="rounded-md border">
        <table className="w-full text-sm">
          <thead className="border-b bg-muted/50">
            <tr>
              {["이미지", "상태", "제조사", "모델", "등록일", "작업"].map((h) => (
                <th key={h} className="px-4 py-3 text-left font-medium text-muted-foreground">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: 10 }).map((_, i) => (
                <tr key={i} className="border-b">
                  {Array.from({ length: 6 }).map((__, j) => (
                    <td key={j} className="px-4 py-3"><Skeleton className="h-4 w-full" /></td>
                  ))}
                </tr>
              ))
            ) : !data?.items.length ? (
              <tr>
                <td colSpan={6} className="px-4 py-10 text-center text-muted-foreground">
                  데이터가 없습니다
                </td>
              </tr>
            ) : (
              data.items.map((item) => {
                const si = statusInfo(item);
                const imgPath = item.original_image_path ?? item.image_path;
                const imgSrc = imgPath ? `/${imgPath}` : "";
                const date = item.created_at
                  ? new Date(item.created_at).toLocaleString("ko-KR", {
                      dateStyle: "short", timeStyle: "short",
                    })
                  : "-";
                return (
                  <tr key={item.id} className="border-b hover:bg-muted/30 transition-colors">
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
                      <Badge variant={si.variant}>{si.label}</Badge>
                    </td>
                    <td className="px-4 py-3">{item.manufacturer ?? <span className="text-muted-foreground">-</span>}</td>
                    <td className="px-4 py-3">{item.model ?? <span className="text-muted-foreground">-</span>}</td>
                    <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">{date}</td>
                    <td className="px-4 py-3">
                      <div className="flex gap-1">
                        <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => setEditVehicle(item)}>
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

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="mt-4 flex items-center justify-center gap-2">
          <Button size="icon" variant="outline" className="h-8 w-8" disabled={page === 0} onClick={() => setPage(page - 1)}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <div className="flex gap-1">
            {Array.from({ length: Math.min(7, totalPages) }, (_, i) => {
              const half = 3;
              const start = Math.max(0, Math.min(page - half, totalPages - 7));
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
          <span className="text-sm text-muted-foreground">{page + 1}/{totalPages} · 총 {total}개</span>
        </div>
      )}

      <VehicleEditDialog
        vehicle={editVehicle}
        open={editVehicle !== null}
        onClose={() => setEditVehicle(null)}
      />
    </div>
  );
}
