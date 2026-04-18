import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@reeve/ui";
import { BboxCanvas } from "@reeve/ui/composites";
import type { ImageState } from "../../stores/analyze-store";

interface Props {
  image: ImageState | null;
  onClose: () => void;
}

export function ImageDetailDialog({ image, onClose }: Props) {
  if (!image) return null;

  const result = image.result;
  const bbox = image.selectedBbox ?? image.detections?.[0]?.bbox ?? null;

  return (
    <Dialog open={!!image} onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="truncate text-sm">{image.file.name}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <BboxCanvas
            imageSrc={image.preview}
            bbox={bbox}
            yoloDetections={image.detections?.map((d) => d.bbox)}
            editable={false}
            onChange={() => {}}
          />

          {result ? (
            <div className="rounded-md border bg-muted/30 p-4 space-y-3">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {[
                  { label: "제조사", value: result.manufacturer ?? "—" },
                  { label: "모델", value: result.model ?? "—" },
                  { label: "연도", value: result.year ?? "—" },
                  {
                    label: "신뢰도",
                    value: result.confidence_score > 0
                      ? `${(result.confidence_score * 100).toFixed(1)}%`
                      : "—",
                  },
                ].map(({ label, value }) => (
                  <div key={label} className="rounded border bg-background p-2 text-center">
                    <div className="text-sm font-semibold text-primary">{value}</div>
                    <div className="text-xs text-muted-foreground">{label}</div>
                  </div>
                ))}
              </div>
            </div>
          ) : image.status === "failed" ? (
            <p className="text-sm text-destructive">{image.error ?? "분석 오류"}</p>
          ) : (
            <p className="text-sm text-muted-foreground">분석 결과 없음</p>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
