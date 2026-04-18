import { useState, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@reeve/ui";
import { Loader2, CheckCircle2, XCircle } from "lucide-react";

interface Progress {
  current: number;
  total: number;
  succeeded: number;
  failed: number;
}

type Phase = "idle" | "running" | "done" | "error";

export function BatchSaveButton() {
  const qc = useQueryClient();
  const [phase, setPhase] = useState<Phase>("idle");
  const [progress, setProgress] = useState<Progress | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const start = async () => {
    if (phase === "running") {
      abortRef.current?.abort();
      setPhase("idle");
      setProgress(null);
      return;
    }

    setPhase("running");
    setProgress(null);
    const controller = new AbortController();
    abortRef.current = controller;

    const connect = async (retries = 0): Promise<void> => {
      try {
        const res = await fetch("/admin/review/batch-save-all", {
          method: "POST",
          signal: controller.signal,
        });
        if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          const lines = buf.split("\n");
          buf = lines.pop() ?? "";
          for (const line of lines) {
            if (!line.startsWith("data:")) continue;
            try {
              const ev = JSON.parse(line.slice(5).trim()) as {
                type: string;
                current?: number;
                total?: number;
                succeeded?: number;
                failed?: number;
              };
              if (ev.type === "start") {
                setProgress({ current: 0, total: ev.total ?? 0, succeeded: 0, failed: 0 });
              } else if (ev.type === "progress") {
                setProgress({
                  current: ev.current ?? 0,
                  total: ev.total ?? 0,
                  succeeded: ev.succeeded ?? 0,
                  failed: ev.failed ?? 0,
                });
              } else if (ev.type === "done") {
                setPhase("done");
                void qc.invalidateQueries({ queryKey: ["analyzed-vehicles"] });
                void qc.invalidateQueries({ queryKey: ["vehicle-counts"] });
                toast.success(`일괄 저장 완료: ${ev.succeeded ?? 0}건 성공`);
                return;
              }
            } catch {}
          }
        }
        setPhase("done");
      } catch (e) {
        if ((e as Error).name === "AbortError") return;
        if (retries < 3) {
          await new Promise((r) => setTimeout(r, 1500 * (retries + 1)));
          return connect(retries + 1);
        }
        setPhase("error");
        toast.error("일괄 저장 실패: 연결 오류");
      }
    };

    await connect();
    setPhase((p) => (p === "running" ? "idle" : p));
  };

  const pct = progress && progress.total > 0
    ? Math.round((progress.current / progress.total) * 100)
    : 0;

  return (
    <div className="flex flex-col gap-1.5">
      <Button
        variant={phase === "running" ? "destructive" : "secondary"}
        size="sm"
        onClick={() => void start()}
      >
        {phase === "running" ? (
          <><Loader2 className="mr-1 h-4 w-4 animate-spin" /> 중지</>
        ) : (
          "전체 일괄 저장"
        )}
      </Button>

      {phase === "running" && progress && (
        <div className="w-full space-y-1">
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
            <div className="h-full bg-primary transition-all" style={{ width: `${pct}%` }} />
          </div>
          <p className="text-xs text-muted-foreground">
            {progress.current}/{progress.total} ({pct}%) · 성공 {progress.succeeded} · 실패 {progress.failed}
          </p>
        </div>
      )}

      {phase === "done" && progress && (
        <p className="flex items-center gap-1 text-xs text-green-600 dark:text-green-400">
          <CheckCircle2 className="h-3 w-3" /> 완료 ({progress.succeeded}건)
        </p>
      )}
      {phase === "error" && (
        <p className="flex items-center gap-1 text-xs text-destructive">
          <XCircle className="h-3 w-3" /> 연결 오류
        </p>
      )}
    </div>
  );
}
