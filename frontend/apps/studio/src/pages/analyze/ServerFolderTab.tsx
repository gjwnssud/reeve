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
import { saveToTraining, extractErrorMessage } from "../../lib/api";
import { ImageGrid } from "./ImageGrid";
import { BulkApproveButton } from "./BulkApproveButton";
import type { ImageState } from "../../stores/analyze-store";

const MAX_DISPLAY = 100;
const POLL_INTERVAL_MS = 3000;

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
  const uploadSema = useRef(new Semaphore(50));
  const analyzeSema = useRef(new Semaphore(8));
  const processedPaths = useRef(new Set<string>());

  const stats = useAnalyzeStore((s) => s.serverStats);

  const serverImages = Object.values(useAnalyzeStore((s) => s.images)).filter(
    (i) => i.source === "server",
  );
  const displayImages = serverImages.slice(-MAX_DISPLAY);

  const processFile = useCallback(
    async (filePath: string, fileName: string) => {
      const signal = abortRef.current.signal;
      const id = crypto.randomUUID();
      const preview = `/api/server-files/image?path=${encodeURIComponent(filePath)}`;
      const placeholderFile = new File([], fileName, { type: "image/jpeg" });

      addImage({ id, source: "server", file: placeholderFile, preview, status: "queued" });
      incrementStat("server", "total");

      let analyzed_id: number | undefined;
      const releaseUpload = await uploadSema.current.acquire();
      try {
        if (signal.aborted) { releaseUpload(); return; }
        updateImage(id, { status: "uploading" });
        const result = await registerServerFile(filePath, clientUUID);
        analyzed_id = result.analyzed_id;
        updateImage(id, { analyzedId: analyzed_id, originalImagePath: result.original_image_path });
      } catch (err) {
        releaseUpload();
        if (!signal.aborted) {
          updateImage(id, { status: "failed", error: String(err) });
          incrementStat("server", "analysisError");
        }
        return;
      }
      releaseUpload(); // 업로드 슬롯 즉시 반환 후 분석 슬롯 대기

      const releaseAnalyze = await analyzeSema.current.acquire();
      try {
        if (signal.aborted) return;
        updateImage(id, { status: "detecting" });
        const detectResult = await detectVehicle(analyzed_id!);
        const detections = detectResult.detections;

        if (detections.length === 0) {
          incrementStat("server", "detectionFailed");
          updateImage(id, { status: "done", detections: [] });
          return;
        }

        if (signal.aborted) return;
        incrementStat("server", "detected");
        const bbox = detections[0]!.bbox;
        updateImage(id, { detections, selectedBbox: bbox, status: "analyzing" });

        for await (const ev of streamAnalyze(analyzed_id!, bbox)) {
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
        if (!signal.aborted) {
          updateImage(id, { status: "failed", error: String(err) });
          incrementStat("server", "analysisError");
        }
      } finally {
        releaseAnalyze();
      }
    },
    [clientUUID, addImage, updateImage, incrementStat],
  );

  useEffect(() => {
    if (!running || !serverPath.trim()) return;

    const poll = async () => {
      try {
        const { files } = await listServerFiles(serverPath.trim());
        for (const f of files) {
          if (!processedPaths.current.has(f.path) && !abortRef.current.signal.aborted) {
            processedPaths.current.add(f.path);
            processFile(f.path, f.name);
          }
        }
      } catch {
        // 디렉토리가 아직 없거나 일시적 오류는 무시하고 다음 폴링에서 재시도
      }
    };

    poll();
    const timerId = setInterval(poll, POLL_INTERVAL_MS);
    return () => clearInterval(timerId);
  }, [running, serverPath, processFile]);

  useEffect(() => {
    return () => {
      abortRef.current.abort();
    };
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
    uploadSema.current = new Semaphore(50);
    analyzeSema.current = new Semaphore(8);
    processedPaths.current.clear();
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
