import { useQueries } from "@tanstack/react-query";
import { Skeleton } from "@reeve/ui";
import { getTrainRun, type TrainRunDetail } from "../../lib/api";
import { MetricsChart, type ChartSeries } from "./MetricsChart";

const PALETTE = ["#667eea", "#22c55e", "#ef4444", "#f59e0b", "#06b6d4", "#a855f7"];

interface Props {
  runIds: string[];
}

function makeAccSeries(detail: TrainRunDetail, color: string): ChartSeries {
  const pts: Array<[number, number | null]> = [];
  for (const e of detail.logs) {
    if (e.val_acc != null && e.epoch != null) pts.push([Number(e.epoch), e.val_acc as number]);
  }
  return { label: detail.run_id, color, points: pts };
}

function makeLossSeries(detail: TrainRunDetail, color: string): ChartSeries {
  const pts: Array<[number, number | null]> = [];
  // step → (epoch 진행도) 로 변환해서 비교가 한 화면에 들어오게
  // 단순히 epoch 축으로 통일 (epoch 부동소수 사용)
  for (const e of detail.logs) {
    if (e.loss != null && e.epoch != null) pts.push([Number(e.epoch), e.loss as number]);
  }
  return { label: detail.run_id, color, points: pts };
}

export function RunCompareView({ runIds }: Props) {
  const queries = useQueries({
    queries: runIds.map((id) => ({
      queryKey: ["train-run", id],
      queryFn: () => getTrainRun(id),
    })),
  });

  const isLoading = queries.some((q) => q.isLoading);
  const details = queries.map((q) => q.data).filter((d): d is TrainRunDetail => !!d);

  if (isLoading) return <Skeleton className="h-64 w-full" />;
  if (details.length < 2) return <p className="text-sm text-muted-foreground">비교하려면 2개 이상의 run을 선택하세요.</p>;

  const accSeries = details.map((d, i) => makeAccSeries(d, PALETTE[i % PALETTE.length]!));
  const lossSeries = details.map((d, i) => makeLossSeries(d, PALETTE[i % PALETTE.length]!));

  // 파라미터 diff 표 — 모든 키 합집합 후 값 차이만 강조
  const paramKeys = new Set<string>();
  for (const d of details) {
    Object.keys(d.meta.params ?? {}).forEach((k) => paramKeys.add(k));
  }
  const sortedKeys = Array.from(paramKeys).sort();

  return (
    <div className="space-y-4">
      <div className="rounded-lg border p-3">
        <h3 className="mb-2 text-sm font-semibold">val_acc 비교 (epoch축, %)</h3>
        <MetricsChart series={accSeries} yLabel="val_acc (%)" xLabel="epoch" yMin={0} yMax={100} height={240} />
      </div>

      <div className="rounded-lg border p-3">
        <h3 className="mb-2 text-sm font-semibold">loss 비교 (epoch축)</h3>
        <MetricsChart series={lossSeries} yLabel="loss" xLabel="epoch" height={240} />
      </div>

      <div className="rounded-lg border">
        <div className="border-b px-3 py-2">
          <h3 className="text-sm font-semibold">파라미터 diff</h3>
          <p className="text-xs text-muted-foreground">값이 다른 행은 노란 배경으로 표시</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-muted/30">
              <tr>
                <th className="px-3 py-2 text-left text-xs font-semibold">param</th>
                {details.map((d, i) => (
                  <th
                    key={d.run_id}
                    className="px-3 py-2 text-left text-xs font-semibold"
                    style={{ color: PALETTE[i % PALETTE.length] }}
                  >
                    {d.run_id}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sortedKeys.map((k) => {
                const values = details.map((d) => (d.meta.params as Record<string, unknown> | undefined)?.[k]);
                const diff = new Set(values.map((v) => JSON.stringify(v))).size > 1;
                return (
                  <tr key={k} className={diff ? "bg-amber-50/40 dark:bg-amber-900/10" : ""}>
                    <td className="border-t px-3 py-1.5 font-mono text-xs">{k}</td>
                    {values.map((v, i) => (
                      <td key={i} className="border-t px-3 py-1.5 text-xs">
                        {v == null ? "-" : typeof v === "boolean" ? (v ? "ON" : "OFF") : String(v)}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="rounded-lg border">
        <div className="border-b px-3 py-2">
          <h3 className="text-sm font-semibold">결과 비교</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-muted/30">
              <tr>
                <th className="px-3 py-2 text-left text-xs font-semibold">run</th>
                <th className="px-3 py-2 text-left text-xs font-semibold">best_val_acc</th>
                <th className="px-3 py-2 text-left text-xs font-semibold">best_epoch</th>
                <th className="px-3 py-2 text-left text-xs font-semibold">last/total</th>
                <th className="px-3 py-2 text-left text-xs font-semibold">early_stopped</th>
                <th className="px-3 py-2 text-left text-xs font-semibold">elapsed</th>
                <th className="px-3 py-2 text-left text-xs font-semibold">classes</th>
              </tr>
            </thead>
            <tbody>
              {details.map((d, i) => {
                const r = d.meta.result ?? {};
                return (
                  <tr key={d.run_id} className="border-t">
                    <td className="px-3 py-1.5 font-mono text-xs" style={{ color: PALETTE[i % PALETTE.length] }}>
                      {d.run_id}
                    </td>
                    <td className="px-3 py-1.5">{r.best_val_acc != null ? `${r.best_val_acc.toFixed(2)}%` : "-"}</td>
                    <td className="px-3 py-1.5">{r.best_epoch ?? "-"}</td>
                    <td className="px-3 py-1.5">{r.last_epoch ?? "-"}/{r.total_epochs ?? "-"}</td>
                    <td className="px-3 py-1.5">{r.early_stopped ? "예" : "아니오"}</td>
                    <td className="px-3 py-1.5">
                      {r.elapsed_sec != null ? `${Math.floor(r.elapsed_sec / 60)}m ${r.elapsed_sec % 60}s` : "-"}
                    </td>
                    <td className="px-3 py-1.5">{d.meta.data?.num_classes ?? "-"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
