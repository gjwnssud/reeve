import { useState, useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Button, Input, Label, Badge,
  Dialog, DialogContent, DialogHeader, DialogTitle,
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@reeve/ui";
import { BboxCanvas } from "@reeve/ui/composites";
import {
  Loader2, Plus, RefreshCw, Save, CheckCircle2, PauseCircle, XCircle,
  AlertTriangle, Eye,
} from "lucide-react";

import {
  getManufacturers, getVehicleModels,
  createManufacturer, createVehicleModel,
  updateAnalyzedVehicle, saveToTraining,
  holdAnalyzedVehicle, rejectAnalyzedVehicle,
  extractErrorMessage,
} from "../../lib/api";
import { streamAnalyze } from "../../lib/analyzeApi";
import { useAnalyzeStore, type ImageState } from "../../stores/analyze-store";

interface Props {
  image: ImageState | null;
  onClose: () => void;
}

type Bbox = [number, number, number, number];

const HOLD_REASON_CHIPS = ["차량 일부 가림", "조명 부족", "각도 모호", "동일 차량 중복"];
const REJECT_REASON_CHIPS = ["오탐 (차량 아님)", "잘못된 차종", "이미지 품질 불가", "라벨 모호"];

export function ImageDetailDialog({ image, onClose }: Props) {
  const qc = useQueryClient();
  const updateImage = useAnalyzeStore((s) => s.updateImage);
  const removeImage = useAnalyzeStore((s) => s.removeImage);

  const [bbox, setBbox] = useState<Bbox | null>(null);
  const [mfId, setMfId] = useState<number | null>(null);
  const [modelId, setModelId] = useState<number | null>(null);

  const [inlineAddMf, setInlineAddMf] = useState(false);
  const [inlineAddModel, setInlineAddModel] = useState(false);
  const [newMfCode, setNewMfCode] = useState("");
  const [newMfKo, setNewMfKo] = useState("");
  const [newMfEn, setNewMfEn] = useState("");
  const [newMfDomestic, setNewMfDomestic] = useState(false);
  const [newModelCode, setNewModelCode] = useState("");
  const [newModelKo, setNewModelKo] = useState("");
  const [newModelEn, setNewModelEn] = useState("");

  const [isSaving, setSaving] = useState(false);
  const [isApproving, setApproving] = useState(false);
  const [isHolding, setHolding] = useState(false);
  const [isRejecting, setRejecting] = useState(false);
  const [isReanalyzing, setReanalyzing] = useState(false);
  const [reanalyzeMsg, setReanalyzeMsg] = useState<{ text: string; ok: boolean } | null>(null);
  const [progressText, setProgressText] = useState<string | null>(null);
  const [reasonMode, setReasonMode] = useState<"hold" | "reject" | null>(null);
  const [reasonText, setReasonText] = useState("");
  const reasonInputRef = useRef<HTMLInputElement | null>(null);

  const open = image !== null;

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
    if (!image) return;
    const r = image.result;
    setMfId(r?.matched_manufacturer_id ?? null);
    setModelId(r?.matched_model_id ?? null);
    const initBbox: Bbox | null = (image.selectedBbox as Bbox | undefined)
      ?? (image.detections?.[0]?.bbox as Bbox | undefined)
      ?? null;
    setBbox(initBbox);
    setInlineAddMf(false);
    setInlineAddModel(false);
    setReanalyzeMsg(null);
    setProgressText(null);
    setReasonMode(null);
    setReasonText("");
  }, [image]);

  const hasAnalyzedId = image?.result?.id != null;
  const result = image?.result;

  const refreshAdminQueries = () => {
    void qc.invalidateQueries({ queryKey: ["analyzed-vehicles"] });
    void qc.invalidateQueries({ queryKey: ["vehicle-counts"] });
  };

  const handleSave = async () => {
    if (!image || !hasAnalyzedId || !result) { toast.error("저장할 분석 결과가 없습니다"); return; }
    if (!mfId || !modelId) { toast.error("제조사와 모델을 선택하세요"); return; }
    const mf = manufacturers?.find((m) => m.id === mfId);
    const md = models?.find((m) => m.id === modelId);
    setSaving(true);
    try {
      const res = await updateAnalyzedVehicle(result.id, {
        matched_manufacturer_id: mfId,
        matched_model_id: modelId,
        manufacturer: mf?.korean_name,
        model: md?.korean_name,
      });
      updateImage(image.id, {
        result: {
          ...result,
          manufacturer: mf?.korean_name ?? null,
          model: md?.korean_name ?? null,
          matched_manufacturer_id: mfId,
          matched_model_id: modelId,
        },
      });
      refreshAdminQueries();
      toast.success(res.training_synced ? "학습 데이터에 즉시 반영됨" : "저장되었습니다");
    } catch (e) {
      toast.error(extractErrorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  const handleApprove = async () => {
    if (!image || !hasAnalyzedId || !result) { toast.error("저장할 분석 결과가 없습니다"); return; }
    if (!mfId || !modelId) { toast.error("제조사와 모델을 먼저 선택하세요"); return; }
    setApproving(true);
    try {
      const mf = manufacturers?.find((m) => m.id === mfId);
      const md = models?.find((m) => m.id === modelId);
      await updateAnalyzedVehicle(result.id, {
        matched_manufacturer_id: mfId,
        matched_model_id: modelId,
        manufacturer: mf?.korean_name,
        model: md?.korean_name,
      });
      await saveToTraining(result.id);
      refreshAdminQueries();
      toast.success("승인 완료");
      removeImage(image.id);
      onClose();
    } catch (e) {
      toast.error(extractErrorMessage(e));
    } finally {
      setApproving(false);
    }
  };

  const submitHold = async () => {
    if (!image || !hasAnalyzedId || !result) return;
    setHolding(true);
    try {
      await holdAnalyzedVehicle(result.id, reasonText.trim() || undefined);
      refreshAdminQueries();
      toast.success("보류 처리됨");
      removeImage(image.id);
      onClose();
    } catch (e) {
      toast.error(extractErrorMessage(e));
    } finally {
      setHolding(false);
    }
  };

  const submitReject = async () => {
    if (!image || !hasAnalyzedId || !result) return;
    setRejecting(true);
    try {
      await rejectAnalyzedVehicle(result.id, reasonText.trim() || undefined);
      refreshAdminQueries();
      toast.success("반려 처리됨");
      removeImage(image.id);
      onClose();
    } catch (e) {
      toast.error(extractErrorMessage(e));
    } finally {
      setRejecting(false);
    }
  };

  const handleReanalyze = async () => {
    if (!image || !hasAnalyzedId || !result) { toast.error("재분석할 분석 결과가 없습니다"); return; }
    const useBbox: Bbox = bbox ?? [0, 0, 1, 1];
    setReanalyzing(true);
    setReanalyzeMsg(null);
    setProgressText("재분석 시작 중...");
    try {
      for await (const ev of streamAnalyze(result.id, useBbox)) {
        if (ev.event === "progress") {
          setProgressText(ev.message);
        } else if (ev.event === "completed" && ev.result) {
          updateImage(image.id, { result: ev.result, status: "done", selectedBbox: useBbox });
          setMfId(ev.result.matched_manufacturer_id);
          setModelId(ev.result.matched_model_id);
          setReanalyzeMsg({
            text: `${ev.result.manufacturer ?? "-"} / ${ev.result.model ?? "-"}`,
            ok: true,
          });
          setProgressText(null);
          refreshAdminQueries();
        } else if (ev.event === "error") {
          setReanalyzeMsg({ text: ev.message, ok: false });
          setProgressText(null);
        }
      }
    } catch (e) {
      setReanalyzeMsg({ text: extractErrorMessage(e), ok: false });
      setProgressText(null);
    } finally {
      setReanalyzing(false);
    }
  };

  const handleAddMf = async () => {
    if (!newMfCode || !newMfKo || !newMfEn) { toast.error("모든 필드를 입력하세요"); return; }
    try {
      const mf = await createManufacturer({
        code: newMfCode.toUpperCase(),
        korean_name: newMfKo,
        english_name: newMfEn,
        is_domestic: newMfDomestic,
      });
      await qc.invalidateQueries({ queryKey: ["manufacturers"] });
      setMfId(mf.id);
      setModelId(null);
      setInlineAddMf(false);
      setNewMfCode(""); setNewMfKo(""); setNewMfEn(""); setNewMfDomestic(false);
      toast.success("제조사가 추가되었습니다");
    } catch (e) {
      toast.error(extractErrorMessage(e));
    }
  };

  const handleAddModel = async () => {
    if (!mfId) { toast.error("제조사를 먼저 선택하세요"); return; }
    if (!newModelCode || !newModelKo || !newModelEn) { toast.error("모든 필드를 입력하세요"); return; }
    const mf = manufacturers?.find((m) => m.id === mfId);
    if (!mf) return;
    try {
      const mdl = await createVehicleModel({
        code: newModelCode.toUpperCase(),
        korean_name: newModelKo,
        english_name: newModelEn,
        manufacturer_id: mfId,
        manufacturer_code: mf.code,
      });
      await qc.invalidateQueries({ queryKey: ["vehicle-models", mfId] });
      setModelId(mdl.id);
      setInlineAddModel(false);
      setNewModelCode(""); setNewModelKo(""); setNewModelEn("");
      toast.success("모델이 추가되었습니다");
    } catch (e) {
      toast.error(extractErrorMessage(e));
    }
  };

  // Keyboard shortcuts: A approve / H hold / R reject
  useEffect(() => {
    if (!open || !image) return;
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || target?.isContentEditable) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;

      if (e.key === "a" || e.key === "A") {
        e.preventDefault();
        if (hasAnalyzedId && mfId && modelId) void handleApprove();
      } else if (e.key === "h" || e.key === "H") {
        e.preventDefault();
        if (hasAnalyzedId) {
          setReasonMode("hold");
          setTimeout(() => reasonInputRef.current?.focus(), 0);
        }
      } else if (e.key === "r" || e.key === "R") {
        e.preventDefault();
        if (hasAnalyzedId) {
          setReasonMode("reject");
          setTimeout(() => reasonInputRef.current?.focus(), 0);
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, image, hasAnalyzedId, mfId, modelId]);

  if (!image) return null;

  const yoloBboxes: Bbox[] = (image.detections ?? [])
    .map((d) => d.bbox as Bbox)
    .filter(Boolean);

  const visualEvidence = result?.visual_evidence?.trim() ?? "";

  const finalConf = result?.confidence_score ?? null;
  const busy = isSaving || isApproving || isHolding || isRejecting;

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose(); }} modal>
      <DialogContent
        className="max-h-[90vh] max-w-5xl overflow-y-auto"
        onPointerDownOutside={(e) => e.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle className="truncate text-sm">
            {image.file.name}{result?.id ? ` · #${result.id}` : ""}
          </DialogTitle>
        </DialogHeader>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_360px]">
          {/* Canvas */}
          <div>
            <p className="mb-1 text-xs text-muted-foreground">
              YOLO 감지박스를 선택하거나 직접 드래그하여 영역을 조정합니다
            </p>
            <BboxCanvas
              imageSrc={image.preview}
              bbox={bbox}
              yoloDetections={yoloBboxes}
              editable
              onChange={(b) => setBbox(b as Bbox | null)}
            />
            {bbox && (
              <p className="mt-1 text-xs text-muted-foreground">
                [{bbox[0]}, {bbox[1]}, {bbox[2]}, {bbox[3]}] ({bbox[2] - bbox[0]}×{bbox[3] - bbox[1]}px)
              </p>
            )}
          </div>

          {/* Form */}
          <div className="space-y-3">
            {result ? (
              <p className="text-sm text-muted-foreground">
                현재: {result.manufacturer ?? "N/A"} / {result.model ?? "N/A"}
                {finalConf != null && finalConf > 0 && (
                  <span className="ml-2">({finalConf.toFixed(1)}%)</span>
                )}
              </p>
            ) : image.status === "failed" ? (
              <p className="text-sm text-destructive">{image.error ?? "분석 오류"}</p>
            ) : (
              <p className="text-sm text-muted-foreground">분석 결과 없음</p>
            )}

            {/* 신뢰도 + 시각적 근거 */}
            {result && (
              <div className="space-y-1.5 rounded-md border bg-muted/30 p-2.5 text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-medium">VLM 분석</span>
                  <span className="font-mono tabular-nums">
                    {finalConf != null ? `${finalConf.toFixed(1)}%` : "-"}
                  </span>
                </div>
                {visualEvidence ? (
                  <div className="flex gap-1.5 text-muted-foreground">
                    <Eye className="mt-0.5 h-3 w-3 shrink-0" />
                    <p className="whitespace-pre-wrap break-words text-[11px] leading-relaxed">{visualEvidence}</p>
                  </div>
                ) : (
                  <p className="text-[11px] text-muted-foreground">시각적 근거 없음</p>
                )}
                {finalConf != null && finalConf < 60 && (
                  <div className="flex items-center gap-1 text-amber-700 dark:text-amber-400">
                    <AlertTriangle className="h-3 w-3" />
                    <span>신뢰도가 낮습니다. 보류 또는 반려를 권장합니다.</span>
                  </div>
                )}
              </div>
            )}

            {/* Manufacturer */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label>제조사</Label>
                {hasAnalyzedId && (
                  <button
                    type="button"
                    onClick={() => setInlineAddMf(!inlineAddMf)}
                    className="text-xs text-primary hover:underline"
                  >
                    {inlineAddMf ? "취소" : <><Plus className="inline h-3 w-3" /> 추가</>}
                  </button>
                )}
              </div>
              {inlineAddMf ? (
                <div className="space-y-1.5 rounded-md border bg-muted/40 p-2">
                  <Input placeholder="코드 (예: HYUNDAI)" value={newMfCode} onChange={(e) => setNewMfCode(e.target.value)} />
                  <Input placeholder="한글명" value={newMfKo} onChange={(e) => setNewMfKo(e.target.value)} />
                  <Input placeholder="영문명" value={newMfEn} onChange={(e) => setNewMfEn(e.target.value)} />
                  <label className="flex items-center gap-2 text-xs">
                    <input
                      type="checkbox"
                      className="h-3.5 w-3.5 rounded border-input accent-primary"
                      checked={newMfDomestic}
                      onChange={(e) => setNewMfDomestic(e.target.checked)}
                    />
                    국내 제조사
                  </label>
                  <Button size="sm" className="w-full" onClick={handleAddMf}>저장</Button>
                </div>
              ) : (
                <Select
                  value={mfId ? String(mfId) : ""}
                  onValueChange={(v) => { setMfId(Number(v)); setModelId(null); }}
                  disabled={!hasAnalyzedId}
                >
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
                {mfId && hasAnalyzedId && (
                  <button
                    type="button"
                    onClick={() => setInlineAddModel(!inlineAddModel)}
                    className="text-xs text-primary hover:underline"
                  >
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
                <Select
                  value={modelId ? String(modelId) : ""}
                  onValueChange={(v) => setModelId(Number(v))}
                  disabled={!mfId || !hasAnalyzedId}
                >
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
              <p className={`rounded p-2 text-xs ${reanalyzeMsg.ok
                ? "bg-green-50 text-green-700 dark:bg-green-950/30 dark:text-green-400"
                : "bg-red-50 text-red-700 dark:bg-red-950/30 dark:text-red-400"}`}>
                {reanalyzeMsg.ok ? "완료: " : "오류: "}{reanalyzeMsg.text}
              </p>
            )}

            {/* 사유 입력 영역 */}
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

            {!reasonMode && (
              <div className="flex flex-col gap-2 pt-1">
                <Button
                  onClick={handleApprove}
                  disabled={!hasAnalyzedId || busy || !mfId || !modelId}
                  className="w-full"
                >
                  {isApproving ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <CheckCircle2 className="mr-1 h-4 w-4" />}
                  승인 <Badge variant="outline" className="ml-2 px-1.5 py-0 text-[10px]">A</Badge>
                </Button>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    onClick={() => setReasonMode("hold")}
                    disabled={!hasAnalyzedId || busy}
                    className="flex-1"
                  >
                    {isHolding ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <PauseCircle className="mr-1 h-4 w-4" />}
                    보류 <Badge variant="outline" className="ml-1 px-1.5 py-0 text-[10px]">H</Badge>
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => setReasonMode("reject")}
                    disabled={!hasAnalyzedId || busy}
                    className="flex-1"
                  >
                    {isRejecting ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <XCircle className="mr-1 h-4 w-4" />}
                    반려 <Badge variant="outline" className="ml-1 px-1.5 py-0 text-[10px]">R</Badge>
                  </Button>
                </div>

                <div className="my-1 h-px bg-border" />

                {result?.review_status !== "approved" && (
                  <Button
                    onClick={handleSave}
                    disabled={!hasAnalyzedId || isSaving || !mfId || !modelId}
                    variant="secondary"
                    className="w-full"
                  >
                    {isSaving ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Save className="mr-1 h-4 w-4" />}
                    매칭만 저장 (상태 유지)
                  </Button>
                )}
                <Button
                  variant="outline"
                  onClick={handleReanalyze}
                  disabled={!hasAnalyzedId || isReanalyzing}
                  className="w-full"
                >
                  {isReanalyzing ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-1 h-4 w-4" />}
                  재분석 (선택 영역 기준)
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
