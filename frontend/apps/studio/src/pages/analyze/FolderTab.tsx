import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@reeve/ui";
import { FolderOpen, Play, Square, Trash2, AlertCircle } from "lucide-react";
import { useFileSystemAccess, useFolderWatch, useClientUUID, Semaphore } from "@reeve/shared";
import { useAnalyzeStore } from "../../stores/analyze-store";
import { uploadFile, detectVehicle, streamAnalyze } from "../../lib/analyzeApi";
import { saveToTraining, extractErrorMessage } from "../../lib/api";
import { ImageGrid } from "./ImageGrid";
import { BulkApproveButton } from "./BulkApproveButton";
import type { ImageState } from "../../stores/analyze-store";

const MAX_DISPLAY = 100;

interface Props {
  onSelectImage: (img: ImageState) => void;
  onRunningChange?: (running: boolean) => void;
}

export function FolderTab({ onSelectImage, onRunningChange }: Props) {
  const clientUUID = useClientUUID();
  const { supported, pickDirectory } = useFileSystemAccess();
  const [dirHandle, setDirHandle] = useState<FileSystemDirectoryHandle | null>(null);
  const { addImage, updateImage, clearImages, incrementStat, setFolderWatchRunning } = useAnalyzeStore();
  const abortRef = useRef<AbortController>(new AbortController());
  const analyzeSema = useRef(new Semaphore(8));

  const folderImages = Object.values(useAnalyzeStore((s) => s.images)).filter(
    (i) => i.source === "folder",
  );
  const displayImages = folderImages.slice(-MAX_DISPLAY);

  const processFile = useCallback(
    async (wf: { name: string; file: File }, release: () => void) => {
      const { name, file } = wf;
      const signal = abortRef.current.signal;
      const id = crypto.randomUUID();
      const preview = URL.createObjectURL(file);
      addImage({ id, source: "folder", file, preview, status: "queued" });
      incrementStat("folder", "total");

      let analyzed_id: number | undefined;
      try {
        // ── Phase 1: Upload (concurrency 50, release slot immediately after) ──
        if (signal.aborted) return;
        updateImage(id, { status: "uploading" });
        const result = await uploadFile(file, "folder", clientUUID);
        analyzed_id = result.analyzed_id;
        updateImage(id, { analyzedId: analyzed_id, originalImagePath: result.original_image_path });

        try {
          await dirHandle?.removeEntry(name);
        } catch (e) {
          console.warn("file delete failed", name, e);
        }
      } catch (err) {
        if (!signal.aborted) {
          updateImage(id, { status: "failed", error: String(err) });
          incrementStat("folder", "analysisError");
        }
        return;
      } finally {
        release(); // 업로드 슬롯 즉시 반환
      }

      // ── Phase 2: Detect + Analyze + Save (concurrency 8) ──
      const releaseAnalyze = await analyzeSema.current.acquire();
      try {
        if (signal.aborted) return;
        updateImage(id, { status: "detecting" });
        const detectResult = await detectVehicle(analyzed_id!);
        const detections = detectResult.detections;

        if (detections.length === 0) {
          incrementStat("folder", "detectionFailed");
          updateImage(id, { status: "done", detections: [] });
          return;
        }

        if (signal.aborted) return;
        incrementStat("folder", "detected");
        const bbox = detections[0]!.bbox;
        updateImage(id, { detections, selectedBbox: bbox, status: "analyzing" });

        for await (const ev of streamAnalyze(analyzed_id!, bbox)) {
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
        if (!signal.aborted) {
          updateImage(id, { status: "failed", error: String(err) });
          incrementStat("folder", "analysisError");
        }
      } finally {
        releaseAnalyze();
      }
    },
    [clientUUID, addImage, updateImage, incrementStat, dirHandle],
  );

  const { running, start, stop } = useFolderWatch({
    dirHandle,
    onNewFile: (wf, release) => processFile(wf, release),
    concurrency: 50,
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
    if (handle) {
      setDirHandle(handle);
    }
  };

  const stats = useAnalyzeStore((s) => s.folderStats);

  return (
    <div className="space-y-4">
      {/* FSA not supported banner */}
      {!supported && (
        <div className="flex items-start gap-2 rounded-md border border-yellow-500/40 bg-yellow-500/10 p-3 text-sm text-yellow-700 dark:text-yellow-400">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            이 브라우저는 폴더 감시(File System Access API)를 지원하지 않습니다. Chrome 또는 Edge를 사용해 주세요.
          </span>
        </div>
      )}

      {/* Controls */}
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

      {/* Stats */}
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

      {folderImages.length > MAX_DISPLAY && (
        <p className="text-xs text-muted-foreground text-right">
          최신 {MAX_DISPLAY}개만 표시 중 (전체 {folderImages.length}개)
        </p>
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
