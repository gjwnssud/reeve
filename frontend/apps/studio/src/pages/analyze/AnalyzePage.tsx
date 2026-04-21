import { useState, useCallback } from "react";
import { cn } from "@reeve/ui";
import { FileTab } from "./FileTab";
import { FolderTab } from "./FolderTab";
import { ServerFolderTab } from "./ServerFolderTab";
import { ImageDetailDialog } from "./ImageDetailDialog";
import { useAnalyzeStore } from "../../stores/analyze-store";
import type { ImageState } from "../../stores/analyze-store";

type Tab = "file" | "folder" | "server";

const TAB_LABELS: Record<Tab, string> = {
  file: "파일 업로드",
  folder: "로컬 폴더 감시",
  server: "서버 폴더 감시",
};

const LEAVE_MSG = "폴더 감시가 진행 중입니다. 이동하면 감시가 중지됩니다. 계속하시겠습니까?";

export function AnalyzePage() {
  const [tab, setTab] = useState<Tab>("file");
  const [selected, setSelected] = useState<ImageState | null>(null);
  const folderRunning = useAnalyzeStore((s) => s.folderWatchRunning);

  const handleTabChange = useCallback(
    (t: Tab) => {
      if (t === tab) return;
      if (folderRunning && (tab === "folder" || tab === "server")) {
        if (!confirm(LEAVE_MSG)) return;
      }
      setTab(t);
    },
    [tab, folderRunning],
  );

  return (
    <div className="mx-auto max-w-6xl p-6 space-y-4">
      <div>
        <h1 className="text-xl font-semibold">차량 분석</h1>
        <p className="text-sm text-muted-foreground mt-1">이미지를 업로드하거나 폴더를 감시하여 차량을 자동 식별합니다.</p>
      </div>

      {/* Tab buttons */}
      <div className="flex border-b">
        {(["file", "folder", "server"] as Tab[]).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => handleTabChange(t)}
            className={cn(
              "px-4 py-2 text-sm font-medium border-b-2 transition",
              tab === t
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {TAB_LABELS[t]}
          </button>
        ))}
      </div>

      {tab === "file" && <FileTab onSelectImage={setSelected} />}
      {tab === "folder" && <FolderTab onSelectImage={setSelected} />}
      {tab === "server" && <ServerFolderTab onSelectImage={setSelected} />}

      <ImageDetailDialog image={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
