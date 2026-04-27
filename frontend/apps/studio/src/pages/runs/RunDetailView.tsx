import { useQuery } from "@tanstack/react-query";
import { Skeleton, Badge } from "@reeve/ui";
import { getTrainRun, type TrainRunDetail, type LogEntry } from "../../lib/api";
import { MetricsChart, type ChartSeries } from "./MetricsChart";

interface Props {
  runId: string;
}

interface KvProps { label: string; value: React.ReactNode }
function Kv({ label, value }: KvProps) {
  return (
    <div className="flex justify-between gap-3 border-b py-1.5 text-sm last:border-b-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium text-right break-all">{value ?? "-"}</span>
    </div>
  );
}

function buildSeries(logs: LogEntry[]): { loss: ChartSeries; valAcc: ChartSeries; freezeMarker: number | null } {
  // step별 loss
  const lossPoints: Array<[number, number | null]> = [];
  // epoch별 val_acc
  const accPoints: Array<[number, number | null]> = [];

  for (const e of logs) {
    if (e.loss != null && e.current_steps != null) {
      lossPoints.push([e.current_steps as number, e.loss as number]);
    }
    if (e.val_acc != null && e.epoch != null) {
      // val_acc은 0~100 범위로 기록되어 있음 (efficientnet_trainer)
      accPoints.push([Number(e.epoch), e.val_acc as number]);
    }
  }

  return {
    loss: { label: "loss", color: "#667eea", points: lossPoints },
    valAcc: { label: "val_acc(%)", color: "#22c55e", points: accPoints, dashed: true },
    freezeMarker: null,
  };
}

function findWorstAtLastEpoch(logs: LogEntry[]) {
  for (let i = logs.length - 1; i >= 0; i--) {
    const w = logs[i]?.["worst_classes"];
    if (Array.isArray(w) && w.length > 0) return w as Array<{ class: number | string; acc: number }>;
  }
  return [];
}

export function RunDetailView({ runId }: Props) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["train-run", runId],
    queryFn: () => getTrainRun(runId),
  });

  if (isLoading) return <Skeleton className="h-64 w-full" />;
  if (error || !data) return <p className="text-sm text-destructive">상세 정보를 불러올 수 없습니다.</p>;

  const detail: TrainRunDetail = data;
  const meta = detail.meta;
  const params = meta.params ?? {};
  const env = meta.env ?? null;
  const dataInfo = meta.data ?? null;
  const result = meta.result ?? null;
  const cm = detail.class_mapping?.classes ?? {};

  const series = buildSeries(detail.logs);
  const worstLast = findWorstAtLastEpoch(detail.logs);

  return (
    <div className="space-y-4">
      {/* 헤더 */}
      <div className="rounded-lg border p-4">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="text-lg font-semibold">Run {runId}</h2>
          <Badge>{meta.status ?? "-"}</Badge>
          {result?.best_val_acc != null && (
            <Badge variant="outline" className="border-emerald-500 text-emerald-600">
              Best {result.best_val_acc.toFixed(1)}% @ ep {result.best_epoch}
            </Badge>
          )}
        </div>
        <p className="mt-1 text-xs text-muted-foreground">
          시작 {meta.started_at?.replace("T", " ")} · 종료 {meta.ended_at?.replace("T", " ") ?? "-"}
        </p>
      </div>

      {/* loss + val_acc 차트 */}
      <div className="rounded-lg border p-3">
        <h3 className="mb-2 text-sm font-semibold">학습 곡선</h3>
        <p className="mb-2 text-xs text-muted-foreground">
          loss(파란색, x=step), val_acc(초록 점선, x=epoch%, 0~100)
        </p>
        <MetricsChart
          series={[series.loss]}
          yLabel="loss"
          xLabel="step"
          height={200}
        />
        <div className="mt-2">
          <MetricsChart
            series={[series.valAcc]}
            yLabel="val_acc (%)"
            xLabel="epoch"
            yMin={0}
            yMax={100}
            height={200}
          />
        </div>
      </div>

      {/* 좌: 파라미터 / 환경 / 데이터 / 결과, 우: 마지막 epoch worst classes */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="space-y-3">
          <div className="rounded-lg border p-3">
            <h3 className="mb-2 text-sm font-semibold">파라미터</h3>
            <Kv label="learning_rate" value={params.learning_rate} />
            <Kv label="num_epochs" value={params.num_epochs} />
            <Kv label="batch_size" value={params.batch_size} />
            <Kv label="freeze_epochs" value={params.freeze_epochs} />
            <Kv label="grad_accum" value={params.gradient_accumulation} />
            <Kv label="num_workers" value={params.num_workers ?? "auto"} />
            <Kv label="use_ema" value={params.use_ema ? "ON" : "OFF"} />
            <Kv label="use_mixup" value={params.use_mixup ? "ON" : "OFF"} />
            <Kv label="min_per_class" value={params.min_per_class ?? "-"} />
            <Kv label="max_per_class" value={params.max_per_class ?? "-"} />
            <Kv label="early_stopping" value={params.early_stopping_patience} />
          </div>

          <div className="rounded-lg border p-3">
            <h3 className="mb-2 text-sm font-semibold">환경</h3>
            <Kv label="device" value={env?.device_name ?? env?.device} />
            {env?.vram_gb != null && <Kv label="VRAM" value={`${env.vram_gb} GB`} />}
            {env?.sm && <Kv label="sm" value={env.sm} />}
            <Kv label="precision" value={env?.precision} />
            <Kv label="torch" value={env?.torch_version} />
          </div>

          <div className="rounded-lg border p-3">
            <h3 className="mb-2 text-sm font-semibold">데이터</h3>
            <Kv label="num_classes" value={dataInfo?.num_classes} />
            <Kv label="train" value={dataInfo?.train_count?.toLocaleString()} />
            <Kv label="val" value={dataInfo?.val_count?.toLocaleString()} />
            <Kv label="split" value={dataInfo?.split_ratio} />
          </div>

          <div className="rounded-lg border p-3">
            <h3 className="mb-2 text-sm font-semibold">결과</h3>
            <Kv label="best_val_acc" value={result?.best_val_acc != null ? `${result.best_val_acc.toFixed(2)}%` : "-"} />
            <Kv label="best_epoch" value={result?.best_epoch} />
            <Kv label="last_epoch" value={`${result?.last_epoch ?? "-"}/${result?.total_epochs ?? "-"}`} />
            <Kv label="early_stopped" value={result?.early_stopped ? "예" : "아니오"} />
            <Kv label="elapsed" value={result?.elapsed_sec != null ? `${Math.floor(result.elapsed_sec / 60)}m ${result.elapsed_sec % 60}s` : "-"} />
          </div>
        </div>

        <div className="rounded-lg border p-3">
          <h3 className="mb-2 text-sm font-semibold">마지막 epoch — worst 5 클래스</h3>
          {worstLast.length === 0 ? (
            <p className="text-sm text-muted-foreground">데이터 없음</p>
          ) : (
            <div className="space-y-1">
              {worstLast.map((w, i) => {
                const cls = String(w.class);
                const meta = cm[cls];
                return (
                  <div key={i} className="flex items-center justify-between border-b py-1.5 text-sm last:border-b-0">
                    <div>
                      <span className="font-mono text-xs text-muted-foreground">#{cls}</span>
                      {meta && (
                        <span className="ml-2">
                          {meta.manufacturer_korean} {meta.model_korean}
                        </span>
                      )}
                    </div>
                    <span className={w.acc === 0 ? "font-semibold text-destructive" : "font-semibold"}>
                      {w.acc.toFixed(1)}%
                    </span>
                  </div>
                );
              })}
            </div>
          )}
          <p className="mt-3 text-xs text-muted-foreground">
            * jsonl에는 worst 5만 기록됨. 전체 클래스 정확도는 향후 확장 시 추가 가능.
          </p>
        </div>
      </div>
    </div>
  );
}
