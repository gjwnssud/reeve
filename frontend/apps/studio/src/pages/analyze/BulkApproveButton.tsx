import { useState } from "react";
import { Button } from "@reeve/ui";
import { CheckCheck, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { useAnalyzeStore, type ImageState, type ImageSource } from "../../stores/analyze-store";
import { saveToTraining, extractErrorMessage } from "../../lib/api";

interface Props {
  source: ImageSource;
}

function isApprovable(img: ImageState): boolean {
  return (
    img.status === "done" &&
    !!img.result &&
    img.result.matched_manufacturer_id != null &&
    img.result.matched_model_id != null
  );
}

export function BulkApproveButton({ source }: Props) {
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);

  const targets = Object.values(useAnalyzeStore((s) => s.images)).filter(
    (i) => i.source === source && isApprovable(i),
  );

  const handleApprove = async () => {
    if (targets.length === 0) return;
    if (!confirm(`분석 완료된 ${targets.length}건을 일괄 검수 승인합니다. 진행할까요?`)) return;

    setRunning(true);
    setProgress({ done: 0, total: targets.length });
    let ok = 0;
    let fail = 0;
    const removeImage = useAnalyzeStore.getState().removeImage;

    let i = 0;
    for (const img of targets) {
      i++;
      const resultId = img.result?.id;
      if (resultId == null) {
        fail++;
        setProgress({ done: i, total: targets.length });
        continue;
      }
      try {
        await saveToTraining(resultId);
        removeImage(img.id);
        ok++;
      } catch (e) {
        fail++;
        console.error("approve failed", img.id, extractErrorMessage(e));
      }
      setProgress({ done: i, total: targets.length });
    }

    setRunning(false);
    setProgress(null);
    if (fail === 0) {
      toast.success(`${ok}건 승인 완료`);
    } else {
      toast.error(`${ok}건 성공, ${fail}건 실패`);
    }
  };

  if (targets.length === 0 && !running) return null;

  return (
    <Button
      variant="default"
      size="sm"
      onClick={handleApprove}
      disabled={running || targets.length === 0}
    >
      {running ? (
        <>
          <Loader2 className="mr-1 h-4 w-4 animate-spin" />
          승인 중 {progress ? `(${progress.done}/${progress.total})` : ""}
        </>
      ) : (
        <>
          <CheckCheck className="mr-1 h-4 w-4" />
          분석 완료 일괄 승인 ({targets.length})
        </>
      )}
    </Button>
  );
}
