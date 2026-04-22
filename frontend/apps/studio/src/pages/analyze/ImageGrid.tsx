import { Badge } from "@reeve/ui";
import { Loader2, CheckCircle2, XCircle, Search, Upload } from "lucide-react";
import type { ImageState } from "../../stores/analyze-store";

interface Props {
  images: ImageState[];
  onSelect: (img: ImageState) => void;
}

function statusLabel(s: ImageState): { label: string; variant: "default" | "secondary" | "destructive" | "outline" } {
  switch (s.status) {
    case "queued": return { label: "대기", variant: "secondary" };
    case "uploading": return { label: "업로드", variant: "secondary" };
    case "detecting": return { label: "감지 중", variant: "outline" };
    case "analyzing": return { label: s.progressMsg ?? "분석 중", variant: "outline" };
    case "done":
      return s.result?.manufacturer
        ? { label: `${s.result.manufacturer} ${s.result.model ?? ""}`, variant: "default" }
        : { label: "식별 실패", variant: "destructive" };
    case "failed": return { label: "오류", variant: "destructive" };
  }
}

function StatusIcon({ status }: { status: ImageState["status"] }) {
  if (status === "done") return <CheckCircle2 className="h-4 w-4 text-green-500" />;
  if (status === "failed") return <XCircle className="h-4 w-4 text-destructive" />;
  if (status === "analyzing" || status === "detecting" || status === "uploading")
    return <Loader2 className="h-4 w-4 animate-spin text-primary" />;
  if (status === "queued") return <Upload className="h-4 w-4 text-muted-foreground" />;
  return <Search className="h-4 w-4 text-muted-foreground" />;
}

export function ImageGrid({ images, onSelect }: Props) {
  if (images.length === 0) return null;

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
      {images.map((img) => {
        const { label, variant } = statusLabel(img);
        return (
          <button
            key={img.id}
            type="button"
            onClick={() => onSelect(img)}
            className="group relative overflow-hidden rounded-lg border bg-muted/30 text-left transition hover:border-primary/50 hover:shadow-sm"
          >
            <div className="relative aspect-[4/3] overflow-hidden bg-black/10">
              <img
                src={img.preview}
                alt={img.file.name}
                className="h-full w-full object-cover"
              />
              {(img.status === "analyzing" || img.status === "detecting") && img.progress != null && (
                <div className="absolute inset-x-0 bottom-0 h-1 bg-black/20">
                  <div
                    className="h-full bg-primary transition-all"
                    style={{ width: `${img.progress}%` }}
                  />
                </div>
              )}
            </div>
            <div className="p-2">
              <div className="flex items-start justify-between gap-1">
                <p className="truncate text-xs text-muted-foreground">{img.file.name}</p>
                <StatusIcon status={img.status} />
              </div>
              <Badge variant={variant} className="mt-1 max-w-full truncate text-xs">
                {label}
              </Badge>
              {img.result && img.result.confidence_score > 0 && (
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {img.result.confidence_score.toFixed(0)}%
                </p>
              )}
            </div>
          </button>
        );
      })}
    </div>
  );
}
