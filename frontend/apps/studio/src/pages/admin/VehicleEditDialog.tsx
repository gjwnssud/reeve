import { useState, useEffect, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Button, Input, Label, Dialog, DialogContent, DialogHeader, DialogTitle,
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@reeve/ui";
import { BboxCanvas } from "@reeve/ui/composites";
import { Loader2, RefreshCw, Save, Plus } from "lucide-react";

import {
  getManufacturers, getVehicleModels, createManufacturer, createVehicleModel,
  updateAnalyzedVehicle, saveToTraining, reanalyzeVehicle,
  extractErrorMessage, type AnalyzedVehicle,
} from "../../lib/api";
import { streamAnalyze } from "../../lib/analyzeApi";

type Bbox = [number, number, number, number];

interface Props {
  vehicle: AnalyzedVehicle | null;
  open: boolean;
  onClose: () => void;
}

export function VehicleEditDialog({ vehicle, open, onClose }: Props) {
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

  const { data: manufacturers } = useQuery({
    queryKey: ["manufacturers"],
    queryFn: () => getManufacturers(),
    enabled: open,
  });

  const { data: models } = useQuery({
    queryKey: ["vehicle-models", mfId],
    queryFn: () => getVehicleModels(mfId ?? undefined),
    enabled: open && mfId != null,
  });

  // Reset state when vehicle changes
  useEffect(() => {
    if (!vehicle) return;
    setMfId(vehicle.matched_manufacturer_id);
    setModelId(vehicle.matched_model_id);
    setReanalyzeMsg(null);
    setInlineAddMf(false);
    setInlineAddModel(false);
    // Resolve initial bbox: selected_bbox → first yolo → null
    const initBbox: Bbox | null = vehicle.selected_bbox ??
      (vehicle.yolo_detections?.[0]?.bbox ?? null);
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

  const { mutateAsync: saveTraining, isPending: isSavingTraining } = useMutation({
    mutationFn: (id: number) => saveToTraining(id),
    onSuccess: invalidate,
  });

  const handleSave = async () => {
    if (!vehicle || !mfId || !modelId) {
      toast.error("제조사와 모델을 선택하세요");
      return;
    }
    try {
      await patchVehicle({ id: vehicle.id, mfId, modelId });
      toast.success("저장되었습니다");
    } catch (e) {
      toast.error(extractErrorMessage(e));
    }
  };

  const handleSaveTraining = async () => {
    if (!vehicle) return;
    try {
      await saveTraining(vehicle.id);
      toast.success("학습 데이터로 저장되었습니다");
      onClose();
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

  // Inline add manufacturer
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

  // Inline add model
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

  if (!vehicle) return null;

  const imageSrc = vehicle.original_image_path
    ? `/${vehicle.original_image_path}`
    : vehicle.image_path ? `/${vehicle.image_path}` : "";

  const yoloBboxes = (vehicle.yolo_detections ?? [])
    .map((d) => d.bbox)
    .filter(Boolean) as Bbox[];

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose(); }}
      modal>
      <DialogContent
        className="max-w-4xl max-h-[90vh] overflow-y-auto"
        onPointerDownOutside={(e) => e.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle>차량데이터 편집 #{vehicle.id}</DialogTitle>
        </DialogHeader>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_340px]">
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
                [{bbox[0]}, {bbox[1]}, {bbox[2]}, {bbox[3]}] ({bbox[2]-bbox[0]}×{bbox[3]-bbox[1]}px)
              </p>
            )}
          </div>

          {/* Form */}
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              현재: {vehicle.manufacturer ?? "N/A"} / {vehicle.model ?? "N/A"}
            </p>

            {/* Manufacturer */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label>제조사</Label>
                <button
                  type="button"
                  onClick={() => setInlineAddMf(!inlineAddMf)}
                  className="text-xs text-primary hover:underline"
                >
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
                <Select
                  value={mfId ? String(mfId) : ""}
                  onValueChange={(v) => { setMfId(Number(v)); setModelId(null); }}
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
                {mfId && (
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
                  disabled={!mfId}
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
              <p className={`text-xs rounded p-2 ${reanalyzeMsg.ok ? "bg-green-50 text-green-700 dark:bg-green-950/30 dark:text-green-400" : "bg-red-50 text-red-700 dark:bg-red-950/30 dark:text-red-400"}`}>
                {reanalyzeMsg.ok ? "완료: " : "오류: "}{reanalyzeMsg.text}
              </p>
            )}

            <div className="flex flex-col gap-2 pt-2">
              <Button onClick={handleSave} disabled={isSaving || !mfId || !modelId} className="w-full">
                {isSaving ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Save className="mr-1 h-4 w-4" />}
                저장
              </Button>
              <Button variant="secondary" onClick={handleSaveTraining} disabled={isSavingTraining || !mfId || !modelId} className="w-full">
                {isSavingTraining ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : null}
                저장완료 (학습 데이터 적재)
              </Button>
              <Button
                variant="outline"
                onClick={handleReanalyzeBbox}
                disabled={isReanalyzingBbox || isReanalyzing || !bbox}
                className="w-full"
              >
                {isReanalyzingBbox ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-1 h-4 w-4" />}
                재분석 (선택 영역 기준)
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
              <Button variant="ghost" onClick={onClose} className="w-full">닫기</Button>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
