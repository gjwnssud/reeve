import { useCallback, useRef } from "react";
import { Button } from "@reeve/ui";
import { Upload, FolderOpen, Trash2 } from "lucide-react";
import { Semaphore } from "@reeve/shared";
import { useClientUUID } from "@reeve/shared";
import { useAnalyzeStore } from "../../stores/analyze-store";
import { uploadFile, detectVehicle, streamAnalyze } from "../../lib/analyzeApi";
import { ImageGrid } from "./ImageGrid";
import { BulkApproveButton } from "./BulkApproveButton";
import type { ImageState } from "../../stores/analyze-store";

const detectSema = new Semaphore(4);
const analyzeSema = new Semaphore(8);

interface Props {
  onSelectImage: (img: ImageState) => void;
}

export function FileTab({ onSelectImage }: Props) {
  const clientUUID = useClientUUID();
  const { images, addImage, updateImage, clearImages, incrementStat } = useAnalyzeStore();
  const inputRef = useRef<HTMLInputElement>(null);

  const fileImages = Object.values(images).filter((i) => i.source === "file");

  const processFile = useCallback(async (file: File) => {
    const id = crypto.randomUUID();
    const preview = URL.createObjectURL(file);

    addImage({ id, source: "file", file, preview, status: "queued" });

    try {
      // Upload
      updateImage(id, { status: "uploading" });
      const { analyzed_id, original_image_path } = await uploadFile(file, "file", clientUUID);
      updateImage(id, { analyzedId: analyzed_id, originalImagePath: original_image_path });

      // Detect
      updateImage(id, { status: "detecting" });
      const releaseDetect = await detectSema.acquire();
      let detections;
      try {
        const result = await detectVehicle(analyzed_id);
        detections = result.detections;
      } finally {
        releaseDetect();
      }
      updateImage(id, { detections, status: "analyzing" });

      const bbox = detections[0]?.bbox ?? [0, 0, 1, 1] as [number, number, number, number];
      updateImage(id, { selectedBbox: bbox });
      incrementStat("file", "detected");

      // Analyze SSE
      const releaseAnalyze = await analyzeSema.acquire();
      try {
        for await (const ev of streamAnalyze(analyzed_id, bbox)) {
          useAnalyzeStore.getState().applySSEEvent(id, ev);
        }
      } finally {
        releaseAnalyze();
      }

      const finalImg = useAnalyzeStore.getState().images[id];
      if (finalImg?.status === "done") {
        incrementStat("file", "analyzed");
      } else {
        incrementStat("file", "analysisError");
      }
    } catch (err) {
      updateImage(id, { status: "failed", error: String(err) });
      incrementStat("file", "analysisError");
    }
  }, [clientUUID, addImage, updateImage, incrementStat]);

  const handleFiles = useCallback((files: FileList | File[]) => {
    const arr = Array.from(files).filter((f) => f.type.startsWith("image/"));
    for (const file of arr) {
      void processFile(file);
    }
  }, [processFile]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files.length > 0) handleFiles(e.dataTransfer.files);
  }, [handleFiles]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
  }, []);

  const stats = useAnalyzeStore((s) => s.fileStats);

  return (
    <div className="space-y-4">
      {/* Drop zone */}
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        className="flex flex-col items-center justify-center rounded-lg border-2 border-dashed border-muted-foreground/30 p-10 text-center transition hover:border-primary/50 cursor-pointer"
        onClick={() => inputRef.current?.click()}
      >
        <Upload className="mb-2 h-8 w-8 text-muted-foreground" />
        <p className="text-sm font-medium">이미지를 드래그하거나 클릭하여 선택</p>
        <p className="text-xs text-muted-foreground mt-1">JPG, PNG, WEBP 등 지원</p>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept="image/*"
          className="hidden"
          onChange={(e) => { if (e.target.files) handleFiles(e.target.files); e.target.value = ""; }}
        />
      </div>

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

      {/* Actions */}
      {fileImages.length > 0 && (
        <div className="flex justify-end gap-2">
          <BulkApproveButton source="file" />
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              clearImages("file");
              useAnalyzeStore.getState().resetStats("file");
            }}
          >
            <Trash2 className="mr-1 h-4 w-4" /> 목록 초기화
          </Button>
        </div>
      )}

      <ImageGrid images={fileImages} onSelect={onSelectImage} />

      {fileImages.length === 0 && (
        <div className="flex flex-col items-center py-8 text-muted-foreground">
          <FolderOpen className="mb-2 h-10 w-10 opacity-40" />
          <p className="text-sm">업로드된 이미지가 없습니다</p>
        </div>
      )}
    </div>
  );
}
