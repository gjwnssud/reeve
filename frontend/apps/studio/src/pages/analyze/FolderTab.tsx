import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@reeve/ui";
import { FolderOpen, Play, Square, Trash2, AlertCircle } from "lucide-react";
import { useFileSystemAccess, useFolderWatch, useClientUUID, Semaphore } from "@reeve/shared";
import type { WatchedFile } from "@reeve/shared";
import { useAnalyzeStore } from "../../stores/analyze-store";
import { uploadFile, detectVehicle, streamAnalyze } from "../../lib/analyzeApi";
import type { Bbox } from "../../lib/analyzeApi";
import { saveToTraining, extractErrorMessage } from "../../lib/api";
import { ImageGrid } from "./ImageGrid";
import { BulkApproveButton } from "./BulkApproveButton";
import type { ImageState } from "../../stores/analyze-store";

const MAX_DISPLAY = 50;

interface Props {
  onSelectImage: (img: ImageState) => void;
  onRunningChange?: (running: boolean) => void;
}

export function FolderTab({ onSelectImage, onRunningChange }: Props) {
  const clientUUID = useClientUUID();
  const { supported, pickDirectory } = useFileSystemAccess();
  const [dirHandle, setDirHandle] = useState<FileSystemDirectoryHandle | null>(null);
  const [skipYolo, setSkipYolo] = useState(false);
  const { addImage, updateImage, clearImages, incrementStat, setFolderWatchRunning } = useAnalyzeStore();
  const abortRef = useRef<AbortController>(new AbortController());
  const detectSema = useRef(new Semaphore(4));
  const analyzeSema = useRef(new Semaphore(8));
  const dirHandleRef = useRef<FileSystemDirectoryHandle | null>(null);

  useEffect(() => {
    fetch("/api/config")
      .then((r) => r.json())
      .then((d) => setSkipYolo(d.vision_backend === "local_inference"))
      .catch(() => {});
  }, []);

  const folderImages = Object.values(useAnalyzeStore((s) => s.images)).filter(
    (i) => i.source === "folder",
  );
  const displayImages = folderImages.slice(-MAX_DISPLAY);

  useEffect(() => { dirHandleRef.current = dirHandle; }, [dirHandle]);

  // Stage 2+3: 업로드 + 탐지 (업로드 동시 무제한, 탐지 최대 4개)
  // skipYolo=true(local_inference 모드)이면 YOLO 탐지 건너뛰고 바로 분석 단계로 진행
  const uploadAndDetect = useCallback(
    async (wf: WatchedFile): Promise<string | null> => {
      const { name, file } = wf;
      const signal = abortRef.current.signal;
      if (signal.aborted) return null;

      const id = crypto.randomUUID();
      const preview = URL.createObjectURL(file);
      addImage({ id, source: "folder", file, preview, status: "queued" });
      incrementStat("folder", "total");

      try {
        updateImage(id, { status: "uploading" });
        const result = await uploadFile(file, "folder", clientUUID);
        updateImage(id, { analyzedId: result.analyzed_id, originalImagePath: result.original_image_path });

        try { await dirHandleRef.current?.removeEntry(name); } catch { /* ignore */ }

        if (signal.aborted) return null;

        if (skipYolo) {
          // local_inference 모드: 자체 API가 YOLO를 수행하므로 Studio YOLO 건너뜀
          // bbox는 분석 후 백엔드가 채워주므로 dummy 값 사용
          incrementStat("folder", "detected");
          updateImage(id, { selectedBbox: [0, 0, 0, 0] as Bbox, status: "queued" });
          return id;
        }

        // 탐지 세마포어(4) 획득 후 즉시 탐지
        const releaseDetect = await detectSema.current.acquire();
        try {
          if (signal.aborted) return null;
          updateImage(id, { status: "detecting" });
          const detectResult = await detectVehicle(result.analyzed_id);
          const detections = detectResult.detections;

          if (detections.length === 0) {
            incrementStat("folder", "detectionFailed");
            updateImage(id, { status: "done", detections: [] });
            return null; // 탐지 실패 — 분석 대상 아님
          }

          incrementStat("folder", "detected");
          const bbox = detections[0]!.bbox;
          updateImage(id, { detections, selectedBbox: bbox, status: "queued" });
          return id;
        } finally {
          releaseDetect();
        }
      } catch (err) {
        if (!abortRef.current.signal.aborted) {
          updateImage(id, { status: "failed", error: String(err) });
          incrementStat("folder", "analysisError");
        }
        return null;
      }
    },
    [clientUUID, addImage, updateImage, incrementStat, skipYolo],
  );

  // Stage 4+5: 분석 + 저장 (최대 8개 동시)
  const analyzeAndSave = useCallback(
    async (id: string) => {
      const signal = abortRef.current.signal;
      const releaseAnalyze = await analyzeSema.current.acquire();
      try {
        if (signal.aborted) return;
        const img = useAnalyzeStore.getState().images[id];
        if (!img?.analyzedId || !img.selectedBbox) return;

        updateImage(id, { status: "analyzing" });
        for await (const ev of streamAnalyze(img.analyzedId, img.selectedBbox)) {
          if (signal.aborted) break;
          useAnalyzeStore.getState().applySSEEvent(id, ev);
        }

        if (signal.aborted) return;
        const finalImg = useAnalyzeStore.getState().images[id];
        if (finalImg?.status === "done") {
          incrementStat("folder", "analyzed");
          const res = finalImg.result;
          if (res?.matched_manufacturer_id != null && res?.matched_model_id != null) {
            try {
              await saveToTraining(res.id);
              useAnalyzeStore.getState().removeImage(id);
            } catch (e) {
              console.error("auto-approve failed", id, extractErrorMessage(e));
            }
          }
        } else {
          incrementStat("folder", "analysisError");
        }
      } catch (err) {
        if (!abortRef.current.signal.aborted) {
          updateImage(id, { status: "failed", error: String(err) });
          incrementStat("folder", "analysisError");
        }
      } finally {
        releaseAnalyze();
      }
    },
    [updateImage, incrementStat],
  );

  // 배치 처리: 업로드+탐지 전부 완료 → 분석+저장 전부 완료
  const processBatch = useCallback(
    async (batch: WatchedFile[]) => {
      clearImages("folder");
      // Stage 2+3: 배치 내 전체 동시 업로드+탐지, 완료 대기
      const detectedIds = (await Promise.all(batch.map(uploadAndDetect))).filter(Boolean) as string[];
      if (detectedIds.length === 0) return;
      // Stage 4+5: 탐지된 것 전체 동시 분석+저장, 완료 대기
      await Promise.all(detectedIds.map(analyzeAndSave));
    },
    [uploadAndDetect, analyzeAndSave, clearImages],
  );

  const { running, start, stop } = useFolderWatch({
    dirHandle,
    onBatch: processBatch,
  });

  const handleStop = useCallback(() => {
    abortRef.current.abort();
    abortRef.current = new AbortController();
    stop();
  }, [stop]);

  useEffect(() => {
    return () => { abortRef.current.abort(); };
  }, []);

  useEffect(() => {
    setFolderWatchRunning(running);
    onRunningChange?.(running);
  }, [running, onRunningChange, setFolderWatchRunning]);

  useEffect(() => {
    if (!running) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [running]);

  const handlePickFolder = async () => {
    const handle = await pickDirectory();
    if (handle) setDirHandle(handle);
  };

  const stats = useAnalyzeStore((s) => s.folderStats);

  return (
    <div className="space-y-4">
      {!supported && (
        <div className="flex items-start gap-2 rounded-md border border-yellow-500/40 bg-yellow-500/10 p-3 text-sm text-yellow-700 dark:text-yellow-400">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            이 브라우저는 폴더 감시(File System Access API)를 지원하지 않습니다. Chrome 또는 Edge를 사용해 주세요.
          </span>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" onClick={handlePickFolder} disabled={!supported || running}>
          <FolderOpen className="mr-1 h-4 w-4" />
          {dirHandle ? dirHandle.name : "폴더 선택"}
        </Button>

        {dirHandle && !running && (
          <Button onClick={start} disabled={!supported}>
            <Play className="mr-1 h-4 w-4" /> 감시 시작
          </Button>
        )}
        {running && (
          <Button variant="destructive" onClick={handleStop}>
            <Square className="mr-1 h-4 w-4" /> 감시 중지
          </Button>
        )}

        <div className="ml-auto flex gap-2">
          {folderImages.length > 0 && <BulkApproveButton source="folder" />}
          {stats.total > 0 && !running && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                clearImages("folder");
                useAnalyzeStore.getState().resetStats("folder");
              }}
            >
              <Trash2 className="mr-1 h-4 w-4" /> 초기화
            </Button>
          )}
        </div>
      </div>

      {running && (
        <p className="text-sm text-muted-foreground">
          <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-green-500 mr-1.5" />
          폴더 감시 중 — <span className="font-medium">{dirHandle?.name}</span>에 새 이미지가 추가되면 자동으로 처리됩니다.
        </p>
      )}

      {stats.total > 0 && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
          {[
            { label: "전체", value: stats.total },
            { label: "감지", value: stats.detected },
            { label: "감지 실패", value: stats.detectionFailed },
            { label: "분석 완료", value: stats.analyzed },
            { label: "분석 오류", value: stats.analysisError },
          ].map(({ label, value }) => (
            <div key={label} className="rounded border bg-muted/30 p-2 text-center">
              <div className="text-lg font-bold text-primary">{value}</div>
              <div className="text-xs text-muted-foreground">{label}</div>
            </div>
          ))}
        </div>
      )}

      <ImageGrid images={displayImages} onSelect={onSelectImage} />

      {folderImages.length === 0 && (
        <div className="flex flex-col items-center py-8 text-muted-foreground">
          <FolderOpen className="mb-2 h-10 w-10 opacity-40" />
          <p className="text-sm">감시 중인 이미지가 없습니다</p>
        </div>
      )}
    </div>
  );
}
