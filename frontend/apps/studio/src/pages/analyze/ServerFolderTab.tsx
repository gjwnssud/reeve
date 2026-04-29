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
import type { ServerFileInfo, Bbox } from "../../lib/analyzeApi";
import { saveToTraining, extractErrorMessage } from "../../lib/api";
import { ImageGrid } from "./ImageGrid";
import type { ImageState } from "../../stores/analyze-store";

const MAX_DISPLAY = 50;
const POLL_INTERVAL_MS = 3000;
const BATCH_SIZE = 50;
const STORAGE_PREFIX = "reeve_offset_";

function storageKey(path: string, uuid: string) {
  return `${STORAGE_PREFIX}${uuid}_${path}`;
}

function loadOffset(path: string, uuid: string): number {
  try {
    return parseInt(localStorage.getItem(storageKey(path, uuid)) ?? "0", 10) || 0;
  } catch {
    return 0;
  }
}

function saveOffset(path: string, uuid: string, count: number) {
  try {
    localStorage.setItem(storageKey(path, uuid), String(count));
  } catch {}
}

function clearAllOffsets(uuid: string) {
  try {
    const prefix = `${STORAGE_PREFIX}${uuid}_`;
    Object.keys(localStorage)
      .filter((k) => k.startsWith(prefix))
      .forEach((k) => localStorage.removeItem(k));
  } catch {}
}

interface Props {
  onSelectImage: (img: ImageState) => void;
  onRunningChange?: (running: boolean) => void;
}

export function ServerFolderTab({ onSelectImage, onRunningChange }: Props) {
  const clientUUID = useClientUUID();
  const [serverPath, setServerPath] = useState("");
  const [running, setRunning] = useState(false);
  const [resumedFrom, setResumedFrom] = useState(0);
  const skipYoloRef = useRef(false);
  const { addImage, updateImage, clearImages, setFolderWatchRunning, incrementStat, resetStats } = useAnalyzeStore();
  const abortRef = useRef(new AbortController());
  const detectSema = useRef(new Semaphore(4));
  const analyzeSema = useRef(new Semaphore(3));
  const processedCount = useRef(0);

  useEffect(() => {
    fetch("/api/config")
      .then((r) => r.json())
      .then((d) => { skipYoloRef.current = d.vision_backend === "local_inference"; })
      .catch(() => {});
  }, []);

  const stats = useAnalyzeStore((s) => s.serverStats);
  const serverImages = Object.values(useAnalyzeStore((s) => s.images)).filter(
    (i) => i.source === "server",
  );
  const displayImages = serverImages.slice(-MAX_DISPLAY).reverse();

  // Stage 2+3: 복사·등록 + 탐지 (복사 동시 무제한, 탐지 최대 4개)
  // skipYolo=true(local_inference 모드)이면 YOLO 탐지 건너뛰고 바로 분석 단계로 진행
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

        if (skipYoloRef.current) {
          // local_inference 모드: 자체 API가 YOLO를 수행하므로 Studio YOLO 건너뜀
          incrementStat("server", "detected");
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

  // Stage 4+5: 분석 + 저장 (최대 3개 동시)
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
      clearImages("server");
      const detectedIds = (await Promise.all(batch.map(registerAndDetect))).filter(Boolean) as string[];
      if (detectedIds.length === 0) return;
      await Promise.all(detectedIds.map(analyzeAndSave));
    },
    [registerAndDetect, analyzeAndSave, clearImages],
  );

  // 순차 루프: poll → 배치 처리 완료 → poll (처리 중 추가 poll 없음)
  useEffect(() => {
    if (!running || !serverPath.trim()) return;

    const signal = abortRef.current.signal;
    const path = serverPath.trim();

    const runLoop = async () => {
      while (!signal.aborted) {
        try {
          const { files } = await listServerFiles(path);
          const newFiles = files.slice(processedCount.current);

          if (newFiles.length === 0 || signal.aborted) {
            await new Promise<void>((resolve) => {
              const t = setTimeout(resolve, POLL_INTERVAL_MS);
              signal.addEventListener("abort", () => { clearTimeout(t); resolve(); }, { once: true });
            });
            continue;
          }

          const batch = newFiles.slice(0, BATCH_SIZE);
          processedCount.current += batch.length;
          saveOffset(path, clientUUID, processedCount.current);
          await processBatch(batch);
        } catch {
          if (!signal.aborted) {
            await new Promise<void>((resolve) => {
              const t = setTimeout(resolve, POLL_INTERVAL_MS);
              signal.addEventListener("abort", () => { clearTimeout(t); resolve(); }, { once: true });
            });
          }
        }
      }
    };

    void runLoop();
  }, [running, serverPath, clientUUID, processBatch]);

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
    const saved = loadOffset(serverPath.trim(), clientUUID);
    abortRef.current = new AbortController();
    detectSema.current = new Semaphore(4);
    analyzeSema.current = new Semaphore(3);
    processedCount.current = saved;
    setResumedFrom(saved);
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
          {stats.total > 0 && !running && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                clearImages("server");
                resetStats("server");
                clearAllOffsets(clientUUID);
                setResumedFrom(0);
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
          {resumedFrom > 0 && (
            <span className="ml-2 text-xs">({resumedFrom.toLocaleString()}개 건너뜀)</span>
          )}
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
