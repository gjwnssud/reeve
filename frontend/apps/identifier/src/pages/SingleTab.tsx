import { useCallback, useReducer, useRef, useState } from "react";
import { toast } from "sonner";
import { Badge, Button, Card, CardContent } from "@reeve/ui";
import { CircleX, ImagePlus, Loader2, Upload } from "lucide-react";

import { BboxOverlay } from "../components/BboxOverlay";
import { extractErrorMessage, postDetect, postIdentify } from "../lib/api";
import { resolveResultStatus } from "../lib/status";
import type {
  DetectionResult,
  IdentificationResult,
  VehicleDetection,
} from "../lib/types";

type Bbox = [number, number, number, number];
type Phase = "idle" | "detecting" | "detected" | "identifying" | "done" | "error";

type State = {
  phase: Phase;
  file: File | null;
  previewUrl: string | null;
  imageWidth: number;
  imageHeight: number;
  detections: VehicleDetection[];
  selectedIndex: number; // -1이면 bbox 없음(전체 이미지로 판별)
  currentBbox: Bbox | null;
  result: IdentificationResult | null;
  errorMessage: string | null;
};

type Action =
  | { type: "reset" }
  | { type: "file_loaded"; file: File; previewUrl: string }
  | { type: "detect_start" }
  | { type: "detect_success"; payload: DetectionResult }
  | { type: "select_detection"; index: number }
  | { type: "set_bbox"; bbox: Bbox }
  | { type: "identify_start" }
  | { type: "identify_success"; result: IdentificationResult }
  | { type: "error"; message: string };

const initialState: State = {
  phase: "idle",
  file: null,
  previewUrl: null,
  imageWidth: 0,
  imageHeight: 0,
  detections: [],
  selectedIndex: -1,
  currentBbox: null,
  result: null,
  errorMessage: null,
};

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "reset":
      if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
      return initialState;
    case "file_loaded":
      if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
      return {
        ...initialState,
        phase: "detecting",
        file: action.file,
        previewUrl: action.previewUrl,
      };
    case "detect_start":
      return { ...state, phase: "detecting", errorMessage: null };
    case "detect_success": {
      const { detections, image_width, image_height } = action.payload;
      const first = detections[0];
      if (!first) {
        return {
          ...state,
          phase: "detected",
          detections: [],
          selectedIndex: -1,
          currentBbox: null,
          imageWidth: image_width,
          imageHeight: image_height,
        };
      }
      return {
        ...state,
        phase: "detected",
        detections,
        selectedIndex: 0,
        currentBbox: first.bbox as Bbox,
        imageWidth: image_width,
        imageHeight: image_height,
      };
    }
    case "select_detection": {
      const det = state.detections[action.index];
      if (!det) return state;
      return {
        ...state,
        selectedIndex: action.index,
        currentBbox: det.bbox as Bbox,
        result: null,
        phase: state.phase === "done" ? "detected" : state.phase,
      };
    }
    case "set_bbox":
      return { ...state, currentBbox: action.bbox };
    case "identify_start":
      return { ...state, phase: "identifying", result: null, errorMessage: null };
    case "identify_success":
      return { ...state, phase: "done", result: action.result };
    case "error":
      return { ...state, phase: "error", errorMessage: action.message };
  }
}

const MAX_BYTES = 10 * 1024 * 1024;
const ACCEPT = "image/jpeg,image/jpg,image/png,image/webp";

export function SingleTab() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const [isDragOver, setDragOver] = useState(false);
  const imageRef = useRef<HTMLImageElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const onSelectFile = useCallback(async (file: File) => {
    if (!file.type.startsWith("image/")) {
      toast.error("이미지 파일만 업로드 가능합니다");
      return;
    }
    if (file.size > MAX_BYTES) {
      toast.error("파일 크기가 10MB를 초과합니다");
      return;
    }
    const url = URL.createObjectURL(file);
    dispatch({ type: "file_loaded", file, previewUrl: url });

    try {
      const result = await postDetect(file);
      dispatch({ type: "detect_success", payload: result });
      if (result.detections.length === 0) {
        toast.info("차량이 감지되지 않았습니다. 이미지 전체로 판별합니다.");
      }
    } catch (e) {
      const msg = extractErrorMessage(e);
      dispatch({ type: "error", message: msg });
      toast.error(`감지 실패: ${msg}`);
    }
  }, []);

  const onIdentify = useCallback(async () => {
    if (!state.file) return;
    dispatch({ type: "identify_start" });
    try {
      const result = await postIdentify(state.file, state.currentBbox);
      dispatch({ type: "identify_success", result });
    } catch (e) {
      const msg = extractErrorMessage(e);
      dispatch({ type: "error", message: msg });
      toast.error(`판별 실패: ${msg}`);
    }
  }, [state.file, state.currentBbox]);

  const onReset = useCallback(() => {
    dispatch({ type: "reset" });
    if (fileInputRef.current) fileInputRef.current.value = "";
  }, []);

  const statusPhaseLabel = (() => {
    switch (state.phase) {
      case "detecting":
        return { label: "감지 중", variant: "secondary" as const };
      case "detected":
        return state.detections.length > 0
          ? { label: `${state.detections.length}대 감지`, variant: "default" as const }
          : { label: "감지 완료", variant: "secondary" as const };
      case "identifying":
        return { label: "판별 중", variant: "default" as const };
      case "done":
        return { label: "분석 완료", variant: "default" as const };
      case "error":
        return { label: "오류", variant: "destructive" as const };
      default:
        return { label: "준비", variant: "outline" as const };
    }
  })();

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="p-6">
          <h2 className="mb-3 flex items-center gap-2 text-base font-semibold">
            <Upload className="h-4 w-4" /> 이미지 업로드
          </h2>
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              const f = e.dataTransfer.files?.[0];
              if (f) void onSelectFile(f);
            }}
            className={`flex w-full flex-col items-center justify-center rounded-lg border-2 border-dashed p-10 text-center transition ${
              isDragOver
                ? "border-primary bg-primary/5"
                : "border-muted-foreground/30 hover:border-primary hover:bg-muted/40"
            }`}
          >
            <ImagePlus className="h-8 w-8 text-muted-foreground" />
            <div className="mt-2 text-sm font-medium">이미지를 드래그하거나 클릭하여 선택</div>
            <div className="mt-1 text-xs text-muted-foreground">JPG, PNG, WebP 지원 · 최대 10MB</div>
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPT}
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void onSelectFile(f);
            }}
          />
        </CardContent>
      </Card>

      {state.previewUrl ? (
        <Card>
          <CardContent className="p-6">
            <div className="mb-3 flex items-center gap-2">
              <h2 className="text-base font-semibold">업로드된 이미지</h2>
              <Badge variant={statusPhaseLabel.variant}>{statusPhaseLabel.label}</Badge>
              <div className="ml-auto text-xs text-muted-foreground">{state.file?.name}</div>
            </div>

            <div className="relative mx-auto max-w-full overflow-hidden rounded-md bg-black/5">
              <img
                ref={imageRef}
                src={state.previewUrl}
                alt="업로드된 이미지"
                className="block h-auto max-h-[60vh] w-full object-contain"
              />
              {state.currentBbox && state.imageWidth > 0 ? (
                <BboxOverlay
                  imageRef={imageRef}
                  imageWidth={state.imageWidth}
                  imageHeight={state.imageHeight}
                  bbox={state.currentBbox}
                  editable
                  label="드래그하여 조정 가능"
                  onChange={(bbox) => dispatch({ type: "set_bbox", bbox })}
                />
              ) : null}
            </div>

            {state.phase === "detecting" ? (
              <div className="mt-4 flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" /> 차량을 감지하고 있습니다...
              </div>
            ) : null}

            {state.detections.length > 0 ? (
              <div className="mt-4 space-y-2">
                <div className="text-sm font-medium">감지된 차량</div>
                <div className="flex flex-wrap gap-2">
                  {state.detections.map((det, idx) => (
                    <button
                      key={idx}
                      type="button"
                      onClick={() => dispatch({ type: "select_detection", index: idx })}
                      className={`rounded-md border px-3 py-1.5 text-xs transition ${
                        state.selectedIndex === idx
                          ? "border-primary bg-primary/10"
                          : "border-border hover:border-primary/60"
                      }`}
                    >
                      <span className="font-semibold">{det.class_name}</span>{" "}
                      <span className="text-muted-foreground">
                        {(det.confidence * 100).toFixed(1)}% · {det.area.toLocaleString()} px²
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            ) : null}

            {state.result ? <ResultCard result={state.result} /> : null}

            <div className="mt-4 flex gap-2">
              <Button
                onClick={onIdentify}
                disabled={
                  !state.file ||
                  state.phase === "detecting" ||
                  state.phase === "identifying"
                }
              >
                {state.phase === "identifying" ? (
                  <>
                    <Loader2 className="mr-1 h-4 w-4 animate-spin" /> 판별 중
                  </>
                ) : state.phase === "done" ? (
                  "재분석"
                ) : (
                  "판별하기"
                )}
              </Button>
              <Button variant="outline" onClick={onReset}>
                <CircleX className="mr-1 h-4 w-4" /> 초기화
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

function ResultCard({ result }: { result: IdentificationResult }) {
  const status = resolveResultStatus(result);
  return (
    <div className="mt-4 rounded-md border bg-muted/40 p-4">
      <div className="mb-2 flex items-center justify-between">
        <div className="text-sm font-semibold">판별 결과</div>
        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${status.className}`}>
          {status.label}
        </span>
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
        <dt className="text-muted-foreground">제조사</dt>
        <dd>{result.manufacturer_korean ?? "-"}</dd>
        <dt className="text-muted-foreground">모델</dt>
        <dd>{result.model_korean ?? "-"}</dd>
        <dt className="text-muted-foreground">신뢰도</dt>
        <dd>{result.confidence > 0 ? `${(result.confidence * 100).toFixed(1)}%` : "-"}</dd>
      </dl>
      {result.message ? (
        <div className="mt-2 text-xs text-muted-foreground">{result.message}</div>
      ) : null}
    </div>
  );
}
