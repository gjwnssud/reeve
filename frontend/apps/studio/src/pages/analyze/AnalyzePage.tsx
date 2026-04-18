import { useState } from "react";
import { cn } from "@reeve/ui";
import { FileTab } from "./FileTab";
import { FolderTab } from "./FolderTab";
import { ImageDetailDialog } from "./ImageDetailDialog";
import type { ImageState } from "../../stores/analyze-store";

type Tab = "file" | "folder";

export function AnalyzePage() {
  const [tab, setTab] = useState<Tab>("file");
  const [selected, setSelected] = useState<ImageState | null>(null);

  return (
    <div className="mx-auto max-w-6xl p-6 space-y-4">
      <div>
        <h1 className="text-xl font-semibold">차량 분석</h1>
        <p className="text-sm text-muted-foreground mt-1">이미지를 업로드하거나 폴더를 감시하여 차량을 자동 식별합니다.</p>
      </div>

      {/* Tab buttons */}
      <div className="flex border-b">
        {(["file", "folder"] as Tab[]).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={cn(
              "px-4 py-2 text-sm font-medium border-b-2 transition",
              tab === t
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {t === "file" ? "파일 업로드" : "폴더 감시"}
          </button>
        ))}
      </div>

      {tab === "file" && <FileTab onSelectImage={setSelected} />}
      {tab === "folder" && <FolderTab onSelectImage={setSelected} />}

      <ImageDetailDialog image={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
