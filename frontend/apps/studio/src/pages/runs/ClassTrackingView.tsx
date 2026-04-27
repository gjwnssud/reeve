import { useMemo, useState } from "react";
import { useQueries } from "@tanstack/react-query";
import { Skeleton, Badge } from "@reeve/ui";
import { getTrainRunClassHistory, type TrainRunClassHistory } from "../../lib/api";

interface Props {
  runIds: string[];
}

interface ClassRow {
  classId: string;
  label: string;
  /** runId → epoch별 acc 시퀀스 */
  perRun: Record<string, (number | null)[]>;
  /** runId → 최종 acc */
  finalAcc: Record<string, number | null>;
}

export function ClassTrackingView({ runIds }: Props) {
  const queries = useQueries({
    queries: runIds.map((id) => ({
      queryKey: ["train-run-class-history", id],
      queryFn: () => getTrainRunClassHistory(id),
    })),
  });

  const isLoading = queries.some((q) => q.isLoading);
  const histories = queries.map((q) => q.data).filter((d): d is TrainRunClassHistory => !!d);

  const [showOnlyZero, setShowOnlyZero] = useState(false);
  const [search, setSearch] = useState("");

  const rows = useMemo<ClassRow[]>(() => {
    const allClasses = new Set<string>();
    for (const h of histories) {
      Object.keys(h.class_acc).forEach((c) => allClasses.add(c));
    }

    const result: ClassRow[] = [];
    for (const cls of allClasses) {
      const perRun: Record<string, (number | null)[]> = {};
      const finalAcc: Record<string, number | null> = {};
      let label = `#${cls}`;
      for (const h of histories) {
        const seq = h.class_acc[cls] ?? [];
        perRun[h.run_id] = seq;
        const last = seq.length > 0 ? seq[seq.length - 1] : null;
        finalAcc[h.run_id] = last ?? null;
        const meta = h.class_meta[cls];
        if (meta?.manufacturer_korean || meta?.model_korean) {
          label = `${meta.manufacturer_korean ?? ""} ${meta.model_korean ?? ""}`.trim() || label;
        }
      }
      result.push({ classId: cls, label, perRun, finalAcc });
    }
    // 정렬: 최신 run 기준 acc 오름차순 (낮은 클래스 먼저)
    const latestRunId = histories[0]?.run_id;
    result.sort((a, b) => {
      const av = latestRunId ? (a.finalAcc[latestRunId] ?? -1) : -1;
      const bv = latestRunId ? (b.finalAcc[latestRunId] ?? -1) : -1;
      return av - bv;
    });
    return result;
  }, [histories]);

  const filteredRows = useMemo(() => {
    return rows.filter((r) => {
      if (search && !r.label.toLowerCase().includes(search.toLowerCase()) && !r.classId.includes(search)) return false;
      if (showOnlyZero) {
        const someZero = Object.values(r.finalAcc).some((v) => v === 0);
        if (!someZero) return false;
      }
      return true;
    });
  }, [rows, search, showOnlyZero]);

  if (isLoading) return <Skeleton className="h-64 w-full" />;
  if (histories.length === 0) return <p className="text-sm text-muted-foreground">선택된 run이 없습니다.</p>;

  return (
    <div className="space-y-3">
      <div className="rounded-lg border bg-muted/20 p-3 text-xs">
        <p className="text-muted-foreground">
          ※ <span className="font-semibold">jsonl 로그 한계</span>: 매 epoch마다 worst 5 클래스만 기록되므로,
          여기 표시되는 클래스는 어느 epoch에서든 worst 5에 포함된 적 있는 클래스입니다.
          전체 226 클래스의 정확도를 추적하려면 향후 학습 스크립트에서 per-class accuracy 전량을 기록하도록 확장 필요.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <input
          type="text"
          placeholder="클래스 ID 또는 모델명 검색..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="h-8 flex-1 min-w-[200px] rounded border bg-background px-2 text-sm"
        />
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            className="h-4 w-4 accent-primary"
            checked={showOnlyZero}
            onChange={(e) => setShowOnlyZero(e.target.checked)}
          />
          0% 클래스만 표시
        </label>
        <Badge variant="outline">{filteredRows.length} 클래스</Badge>
      </div>

      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full text-sm">
          <thead className="bg-muted/40">
            <tr>
              <th className="px-3 py-2 text-left text-xs font-semibold">클래스</th>
              <th className="px-3 py-2 text-left text-xs font-semibold">제조사·모델</th>
              {histories.map((h) => (
                <th key={h.run_id} className="px-3 py-2 text-left text-xs font-semibold whitespace-nowrap">
                  {h.run_id}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filteredRows.length === 0 ? (
              <tr>
                <td colSpan={2 + histories.length} className="px-3 py-6 text-center text-muted-foreground">
                  표시할 클래스가 없습니다.
                </td>
              </tr>
            ) : (
              filteredRows.map((r) => (
                <tr key={r.classId} className="border-t">
                  <td className="px-3 py-1.5 font-mono text-xs">#{r.classId}</td>
                  <td className="px-3 py-1.5 text-xs">{r.label}</td>
                  {histories.map((h) => {
                    const acc = r.finalAcc[h.run_id];
                    const cls =
                      acc == null ? "text-muted-foreground"
                      : acc === 0 ? "font-semibold text-destructive"
                      : acc < 50 ? "font-semibold text-amber-600"
                      : "font-semibold text-emerald-600";
                    return (
                      <td key={h.run_id} className="px-3 py-1.5">
                        <div className={`text-sm ${cls}`}>{acc == null ? "-" : `${acc.toFixed(1)}%`}</div>
                        <div className="mt-0.5 flex h-1.5 w-24 overflow-hidden rounded bg-muted">
                          <div
                            className={
                              acc == null ? "bg-muted-foreground/30"
                              : acc === 0 ? "bg-destructive"
                              : acc < 50 ? "bg-amber-500"
                              : "bg-emerald-500"
                            }
                            style={{ width: `${(acc ?? 0)}%` }}
                          />
                        </div>
                      </td>
                    );
                  })}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
