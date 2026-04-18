import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { Badge, Button, Card, CardContent } from "@reeve/ui";
import { Semaphore } from "@reeve/shared";
import { Download, FolderOpen, Play, Square, Trash2 } from "lucide-react";

import {
  downloadCsv,
  filterImages,
  formatSeconds,
  streamIdentify,
  toCsv,
  type BatchRow,
} from "../lib/batch";
import { resolveStatus } from "../lib/status";

const CONCURRENCY = 20;
const FALLBACK_ROWS = 100;

type Phase = "idle" | "ready" | "running" | "stopping" | "finished";

export function BatchTab() {
  const folderInputRef = useRef<HTMLInputElement | null>(null);
  const [rows, setRows] = useState<BatchRow[]>([]);
  const [phase, setPhase] = useState<Phase>("idle");
  const [folderName, setFolderName] = useState<string>("");
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [processed, setProcessed] = useState(0);
  const abortRef = useRef<AbortController | null>(null);

  // 썸네일 URL cleanup — 컴포넌트 언마운트 또는 교체 시 revoke
  useEffect(() => {
    return () => {
      rows.forEach((r) => r.thumbnailUrl && URL.revokeObjectURL(r.thumbnailUrl));
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onSelectFolder = useCallback((list: FileList | null) => {
    if (!list || list.length === 0) return;
    const images = filterImages(list);
    if (images.length === 0) {
      toast.error("이미지 파일이 없습니다 (JPG, PNG, WebP)");
      return;
    }
    // 이전 rows의 thumbnailUrl 해제
    setRows((prev) => {
      prev.forEach((r) => r.thumbnailUrl && URL.revokeObjectURL(r.thumbnailUrl));
      return images.map((file, index) => ({
        index,
        file,
        thumbnailUrl: images.length <= FALLBACK_ROWS * 5 ? URL.createObjectURL(file) : null,
        stage: "queued",
      }));
    });
    const firstImage = images[0];
    const firstRel = firstImage
      ? (firstImage as File & { webkitRelativePath?: string }).webkitRelativePath ?? ""
      : "";
    setFolderName(firstRel.includes("/") ? firstRel.split("/")[0] ?? "" : "");
    setPhase("ready");
    setProcessed(0);
  }, []);

  const onClear = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    setRows((prev) => {
      prev.forEach((r) => r.thumbnailUrl && URL.revokeObjectURL(r.thumbnailUrl));
      return [];
    });
    setPhase("idle");
    setFolderName("");
    setProcessed(0);
    setStartedAt(null);
    if (folderInputRef.current) folderInputRef.current.value = "";
  }, []);

  const updateRow = useCallback((index: number, patch: Partial<BatchRow>) => {
    setRows((prev) => {
      const target = prev[index];
      if (!target) return prev;
      const next = prev.slice();
      next[index] = { ...target, ...patch };
      return next;
    });
  }, []);

  const onStart = useCallback(async () => {
    if (rows.length === 0) return;
    const abort = new AbortController();
    abortRef.current = abort;
    setPhase("running");
    setStartedAt(Date.now());
    setProcessed(0);

    const sem = new Semaphore(CONCURRENCY);
    let processedCount = 0;

    const tasks = rows.map(async (row) => {
      if (abort.signal.aborted) return;
      const release = await sem.acquire();
      if (abort.signal.aborted) {
        release();
        return;
      }
      try {
        updateRow(row.index, { stage: "detecting" });
        await streamIdentify(
          row.file,
          (event) => {
            if (event.stage === "detecting") {
              updateRow(row.index, { stage: "detecting" });
            } else if (event.stage === "classifying") {
              updateRow(row.index, { stage: "classifying", detection: event.detection });
            } else if (event.stage === "done") {
              updateRow(row.index, {
                stage: "done",
                status: event.status,
                manufacturer_korean: event.manufacturer_korean,
                model_korean: event.model_korean,
                confidence: event.confidence,
                message: event.message,
                detection: event.detection,
              });
            } else if (event.stage === "error") {
              updateRow(row.index, { stage: "error", error: event.message });
            }
          },
          abort.signal,
        );
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        updateRow(row.index, { stage: "error", error: msg });
      } finally {
        processedCount += 1;
        setProcessed(processedCount);
        release();
      }
    });

    await Promise.all(tasks);
    abortRef.current = null;
    setPhase((p) => (p === "stopping" ? "idle" : "finished"));
  }, [rows, updateRow]);

  const onStop = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    setPhase("stopping");
  }, []);

  const stats = useMemo(() => {
    let success = 0;
    let error = 0;
    for (const r of rows) {
      if (r.stage === "done" && !r.error) success += 1;
      else if (r.stage === "error" || r.error) error += 1;
    }
    return { success, error };
  }, [rows]);

  const progressPct = rows.length > 0 ? Math.round((processed / rows.length) * 100) : 0;
  const elapsed = startedAt ? Math.round((Date.now() - startedAt) / 1000) : 0;
  const eta =
    processed > 0 && processed < rows.length
      ? Math.round((elapsed / processed) * (rows.length - processed))
      : null;

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="p-6">
          <h2 className="mb-3 flex items-center gap-2 text-base font-semibold">
            <FolderOpen className="h-4 w-4" /> 폴더 선택
          </h2>
          <button
            type="button"
            onClick={() => folderInputRef.current?.click()}
            className="flex w-full flex-col items-center justify-center rounded-lg border-2 border-dashed border-muted-foreground/30 p-8 text-center transition hover:border-primary hover:bg-muted/40"
          >
            <FolderOpen className="h-7 w-7 text-muted-foreground" />
            <div className="mt-2 text-sm font-medium">폴더를 클릭하여 선택</div>
            <div className="mt-1 text-xs text-muted-foreground">
              폴더 내 JPG, PNG, WebP 이미지를 동시 {CONCURRENCY}개씩 스트리밍으로 처리합니다
            </div>
          </button>
          <input
            ref={folderInputRef}
            type="file"
            // @ts-expect-error webkitdirectory는 React 타입에 없음
            webkitdirectory=""
            multiple
            accept="image/jpeg,image/jpg,image/png,image/webp"
            className="hidden"
            onChange={(e) => onSelectFolder(e.target.files)}
          />

          {rows.length > 0 ? (
            <div className="mt-4 flex flex-wrap items-center justify-between gap-2 text-sm">
              <div>
                <span className="font-semibold">이미지 {rows.length.toLocaleString()}개</span>
                {folderName ? (
                  <span className="ml-2 text-muted-foreground">· {folderName}</span>
                ) : null}
              </div>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  onClick={onStart}
                  disabled={phase === "running" || phase === "stopping"}
                >
                  <Play className="mr-1 h-4 w-4" /> 배치 시작
                </Button>
                <Button size="sm" variant="outline" onClick={onClear} disabled={phase === "running"}>
                  <Trash2 className="mr-1 h-4 w-4" /> 초기화
                </Button>
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>

      {phase !== "idle" && rows.length > 0 ? (
        <Card>
          <CardContent className="p-6">
            <div className="mb-2 flex items-center justify-between text-sm">
              <span className="font-medium">
                {phase === "running"
                  ? "처리 중..."
                  : phase === "stopping"
                    ? "중지 중..."
                    : phase === "finished"
                      ? "완료"
                      : "대기"}
              </span>
              <span className="text-muted-foreground">
                {processed.toLocaleString()} / {rows.length.toLocaleString()}
              </span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full bg-primary transition-all"
                style={{ width: `${progressPct}%` }}
              />
            </div>
            <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground">
              <span>
                {eta != null
                  ? `예상 남은 시간: ${formatSeconds(eta)}`
                  : phase === "finished"
                    ? `총 소요: ${formatSeconds(elapsed)}`
                    : ""}
              </span>
              {phase === "running" ? (
                <Button size="sm" variant="outline" onClick={onStop}>
                  <Square className="mr-1 h-4 w-4" /> 중지
                </Button>
              ) : null}
            </div>
          </CardContent>
        </Card>
      ) : null}

      {rows.length > 0 ? (
        <Card>
          <CardContent className="p-6">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-base font-semibold">판별 결과</h2>
              <div className="flex items-center gap-2">
                <Badge className="bg-emerald-600 text-white hover:bg-emerald-600">
                  성공 {stats.success.toLocaleString()}
                </Badge>
                <Badge className="bg-red-600 text-white hover:bg-red-600">
                  실패 {stats.error.toLocaleString()}
                </Badge>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => downloadCsv(toCsv(rows))}
                  disabled={stats.success + stats.error === 0}
                >
                  <Download className="mr-1 h-4 w-4" /> CSV 다운로드
                </Button>
              </div>
            </div>
            <div className="overflow-x-auto rounded-md border">
              <table className="w-full text-sm">
                <thead className="bg-muted/60 text-xs uppercase text-muted-foreground">
                  <tr>
                    <th className="px-2 py-2 text-left">#</th>
                    <th className="px-2 py-2 text-left">이미지</th>
                    <th className="px-2 py-2 text-left">파일명</th>
                    <th className="px-2 py-2 text-left">제조사</th>
                    <th className="px-2 py-2 text-left">모델</th>
                    <th className="px-2 py-2 text-left">신뢰도</th>
                    <th className="px-2 py-2 text-left">상태</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, i) => (
                    <BatchRowView key={i} row={row} index={i} />
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

function BatchRowView({ row, index }: { row: BatchRow; index: number }) {
  const status = resolveStatus({
    status: row.status,
    error: row.error,
    yolo_detected: row.detection != null,
    message: row.message,
  });

  const statusLabel = (() => {
    if (row.stage === "queued") return { label: "대기중", className: "bg-slate-400 text-white" };
    if (row.stage === "detecting") return { label: "감지 중", className: "bg-sky-500 text-white" };
    if (row.stage === "classifying")
      return { label: "분류 중", className: "bg-violet-600 text-white" };
    return status;
  })();

  const confLabel =
    row.confidence != null && !row.error ? `${(row.confidence * 100).toFixed(1)}%` : "-";

  return (
    <tr className="border-t">
      <td className="px-2 py-2 text-xs text-muted-foreground">{index + 1}</td>
      <td className="px-2 py-2">
        {row.thumbnailUrl ? (
          <img
            src={row.thumbnailUrl}
            alt={row.file.name}
            className="h-12 w-16 rounded object-cover"
          />
        ) : (
          <div className="h-12 w-16 rounded bg-muted" />
        )}
      </td>
      <td className="max-w-[220px] truncate px-2 py-2" title={row.file.name}>
        {row.file.name}
      </td>
      <td className="px-2 py-2">{row.manufacturer_korean ?? "-"}</td>
      <td className="px-2 py-2">{row.model_korean ?? "-"}</td>
      <td className="px-2 py-2">{confLabel}</td>
      <td className="px-2 py-2">
        <span
          className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${statusLabel.className}`}
          title={"title" in statusLabel ? statusLabel.title : undefined}
        >
          {statusLabel.label}
        </span>
      </td>
    </tr>
  );
}
