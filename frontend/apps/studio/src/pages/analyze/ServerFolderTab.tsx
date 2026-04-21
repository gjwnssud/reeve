import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@reeve/ui";
import { Server, Play, Square, Trash2 } from "lucide-react";
import { useClientUUID, Semaphore } from "@reeve/shared";
import { useAnalyzeStore } from "../../stores/analyze-store";
import {
  listServerFiles,
  registerServerFile,
  detectVehicle,
  streamAnalyze,
} from "../../lib/analyzeApi";
import type { ServerFileInfo } from "../../lib/analyzeApi";
import { saveToTraining, extractErrorMessage } from "../../lib/api";
import { ImageGrid } from "./ImageGrid";
import { BulkApproveButton } from "./BulkApproveButton";
import type { ImageState } from "../../stores/analyze-store";

const MAX_DISPLAY = 100;
const POLL_INTERVAL_MS = 3000;
const BATCH_SIZE = 50;

interface Props {
  onSelectImage: (img: ImageState) => void;
  onRunningChange?: (running: boolean) => void;
}

export function ServerFolderTab({ onSelectImage, onRunningChange }: Props) {
  const clientUUID = useClientUUID();
  const [serverPath, setServerPath] = useState("");
  const [running, setRunning] = useState(false);
  const { addImage, updateImage, clearImages, setFolderWatchRunning, incrementStat, resetStats } = useAnalyzeStore();
  const abortRef = useRef(new AbortController());
  const detectSema = useRef(new Semaphore(4));
  const analyzeSema = useRef(new Semaphore(8));
  const processedPaths = useRef(new Set<string>());
  const fileQueue = useRef<ServerFileInfo[]>([]);
  const processingRef = useRef(false);

  const stats = useAnalyzeStore((s) => s.serverStats);
  const serverImages = Object.values(useAnalyzeStore((s) => s.images)).filter(
    (i) => i.source === "server",
  );
  const displayImages = serverImages.slice(-MAX_DISPLAY);

  // Stage 2+3: 복사·등록 + 탐지 (복사 동시 무제한, 탐지 최대 4개)
  const registerAndDetect = useCallback(
    async (f: ServerFileInfo): Promise<string | null> => {
      const signal = abortRef.current.signal;
      if (signal.aborted) return null;

      const id = crypto.randomUUID();
      const preview = `/api/server-files/image?path=${encodeURIComponent(f.path)}`;
      const placeholderFile = new File([], f.name, { type: "image/jpeg" });
      addImage({ id, source: "server", file: placeholderFile, preview, status: "queued" });
      incrementStat("server", "total");

      try {
        updateImage(id, { status: "uploading" });
        const result = await registerServerFile(f.path, clientUUID);
        updateImage(id, { analyzedId: result.analyzed_id, originalImagePath: result.original_image_path });

        if (signal.aborted) return null;

        // 탐지 세마포어(4) 획득 후 즉시 탐지
        const releaseDetect = await detectSema.current.acquire();
        try {
          if (signal.aborted) return null;
          updateImage(id, { status: "detecting" });
          const detectResult = await detectVehicle(result.analyzed_id);
          const detections = detectResult.detections;

          if (detections.length === 0) {
            incrementStat("server", "detectionFailed");
            updateImage(id, { status: "done", detections: [] });
            return null;
          }

          incrementStat("server", "detected");
          const bbox = detections[0]!.bbox;
          updateImage(id, { detections, selectedBbox: bbox, status: "queued" });
          return id;
        } finally {
          releaseDetect();
        }
      } catch (err) {
        if (!abortRef.current.signal.aborted) {
          updateImage(id, { status: "failed", error: String(err) });
          incrementStat("server", "analysisError");
        }
        return null;
      }
    },
    [clientUUID, addImage, updateImage, incrementStat],
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
          incrementStat("server", "analyzed");
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
          incrementStat("server", "analysisError");
        }
      } catch (err) {
        if (!abortRef.current.signal.aborted) {
          updateImage(id, { status: "failed", error: String(err) });
          incrementStat("server", "analysisError");
        }
      } finally {
        releaseAnalyze();
      }
    },
    [updateImage, incrementStat],
  );

  // 배치 처리: 복사+탐지 전부 완료 → 분석+저장 전부 완료
  const processBatch = useCallback(
    async (batch: ServerFileInfo[]) => {
      const detectedIds = (await Promise.all(batch.map(registerAndDetect))).filter(Boolean) as string[];
      if (detectedIds.length === 0) return;
      await Promise.all(detectedIds.map(analyzeAndSave));
    },
    [registerAndDetect, analyzeAndSave],
  );

  // 큐 워커: 배치 단위로 순차 소진
  const drainQueue = useCallback(async () => {
    if (processingRef.current) return;
    processingRef.current = true;
    try {
      while (fileQueue.current.length > 0 && !abortRef.current.signal.aborted) {
        const batch = fileQueue.current.splice(0, BATCH_SIZE);
        await processBatch(batch);
      }
    } finally {
      processingRef.current = false;
    }
  }, [processBatch]);

  useEffect(() => {
    if (!running || !serverPath.trim()) return;

    const poll = async () => {
      try {
        const { files } = await listServerFiles(serverPath.trim());
        let hasNew = false;
        for (const f of files) {
          if (!processedPaths.current.has(f.path) && !abortRef.current.signal.aborted) {
            processedPaths.current.add(f.path);
            fileQueue.current.push(f);
            hasNew = true;
          }
        }
        if (hasNew && !processingRef.current) void drainQueue();
      } catch {
        // 디렉토리가 아직 없거나 일시적 오류는 무시
      }
    };

    poll();
    const timerId = setInterval(poll, POLL_INTERVAL_MS);
    return () => clearInterval(timerId);
  }, [running, serverPath, drainQueue]);

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

  const handleStart = () => {
    if (!serverPath.trim()) return;
    abortRef.current = new AbortController();
    detectSema.current = new Semaphore(4);
    analyzeSema.current = new Semaphore(8);
    processedPaths.current.clear();
    fileQueue.current = [];
    processingRef.current = false;
    setRunning(true);
  };

  const handleStop = () => {
    abortRef.current.abort();
    abortRef.current = new AbortController();
    setRunning(false);
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="text"
          value={serverPath}
          onChange={(e) => setServerPath(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !running) handleStart(); }}
          placeholder="/mnt/nas/260421"
          disabled={running}
          className="flex-1 min-w-[240px] rounded-md border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
        />
        {!running ? (
          <Button onClick={handleStart} disabled={!serverPath.trim()}>
            <Play className="mr-1 h-4 w-4" /> 감시 시작
          </Button>
        ) : (
          <Button variant="destructive" onClick={handleStop}>
            <Square className="mr-1 h-4 w-4" /> 감시 중지
          </Button>
        )}

        <div className="ml-auto flex gap-2">
          {serverImages.length > 0 && <BulkApproveButton source="server" />}
          {stats.total > 0 && !running && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                clearImages("server");
                resetStats("server");
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
          서버 폴더 감시 중 —{" "}
          <span className="font-medium">{serverPath}</span>에 새 이미지가 추가되면 자동으로 처리됩니다.
        </p>
      )}

      {stats.total > 0 && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
          {(
            [
              { label: "전체", value: stats.total },
              { label: "감지", value: stats.detected },
              { label: "감지 실패", value: stats.detectionFailed },
              { label: "분석 완료", value: stats.analyzed },
              { label: "분석 오류", value: stats.analysisError },
            ] as const
          ).map(({ label, value }) => (
            <div key={label} className="rounded border bg-muted/30 p-2 text-center">
              <div className="text-lg font-bold text-primary">{value}</div>
              <div className="text-xs text-muted-foreground">{label}</div>
            </div>
          ))}
        </div>
      )}

      {serverImages.length > MAX_DISPLAY && (
        <p className="text-xs text-muted-foreground text-right">
          최신 {MAX_DISPLAY}개만 표시 중 (전체 {serverImages.length}개)
        </p>
      )}
      <ImageGrid images={displayImages} onSelect={onSelectImage} />

      {serverImages.length === 0 && (
        <div className="flex flex-col items-center py-8 text-muted-foreground">
          <Server className="mb-2 h-10 w-10 opacity-40" />
          <p className="text-sm">감시 중인 이미지가 없습니다</p>
        </div>
      )}
    </div>
  );
}
