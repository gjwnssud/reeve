import { useState, useEffect } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import { cn } from "@reeve/ui";
import { Button, Badge, Input, Label, Skeleton } from "@reeve/ui";
import { ArrowLeft, ArrowRight, Play, Square, Loader2 } from "lucide-react";
import { usePolling } from "@reeve/shared";

import {
  getHwProfile, getFreezeEpochsInfo, getTrainStatus, getTrainLogs, getRawLog,
  startTraining, stopTraining, extractErrorMessage, type EfficientNetTrainConfig,
} from "../../lib/api";
import { LossChart } from "./LossChart";

const schema = z.object({
  learning_rate: z.coerce.number().positive().default(1e-4),
  num_epochs: z.coerce.number().min(1).max(200).default(20),
  batch_size: z.coerce.number().min(1).max(256).default(16),
  freeze_epochs: z.coerce.number().min(0).max(20).default(3),
  min_per_class: z.coerce.number().min(0).default(20),
  max_per_class: z.coerce.number().min(0).default(1000),
  gradient_accumulation: z.coerce.number().min(1).max(32).default(4),
  use_ema: z.boolean().default(false),
  use_mixup: z.boolean().default(false),
  num_workers: z.coerce.number().min(0).max(32).default(2),
  early_stopping_patience: z.coerce.number().min(0).max(30).default(7),
});
type FormData = z.infer<typeof schema>;

const FIELDS: { name: keyof FormData; label: string; hint?: string }[] = [
  { name: "learning_rate",          label: "학습률",              hint: "권장: 1e-4" },
  { name: "num_epochs",             label: "에폭 수",             hint: "권장: 20" },
  { name: "batch_size",             label: "배치 크기",           hint: "HW 프리셋 자동 적용" },
  { name: "freeze_epochs",          label: "Freeze 에폭",         hint: "head 재초기화 시 3 권장" },
  { name: "min_per_class",          label: "최소 샘플/클래스",    hint: "미만 클래스 제외, 권장: 20" },
  { name: "max_per_class",          label: "최대 샘플/클래스",    hint: "0 = 제한 없음, 권장: 1000" },
  { name: "gradient_accumulation",  label: "Gradient Accum.",     hint: "HW 프리셋 자동 적용" },
  { name: "num_workers",            label: "Workers",             hint: "HW 프리셋 자동 적용" },
  { name: "early_stopping_patience",label: "Early Stop Patience", hint: "권장: 7" },
];

interface Props {
  onBack: () => void;
  onNext: () => void;
}

export function TrainStep({ onBack, onNext }: Props) {
  const [pollingEnabled, setPollingEnabled] = useState(false);

  const { data: hw } = useQuery({ queryKey: ["hw-profile"], queryFn: getHwProfile });
  const { data: freezeInfo } = useQuery({ queryKey: ["freeze-epochs"], queryFn: getFreezeEpochsInfo });

  const { data: status } = usePolling({
    queryKey: ["train-status"],
    fetcher: getTrainStatus,
    intervalMs: 5000,
    enabled: pollingEnabled,
  });
  const { data: logsData } = usePolling({
    queryKey: ["train-logs"],
    fetcher: () => getTrainLogs(100),
    intervalMs: 5000,
    enabled: pollingEnabled,
  });
  const { data: rawLogData } = usePolling({
    queryKey: ["raw-log"],
    fetcher: () => getRawLog(100),
    intervalMs: 5000,
    enabled: pollingEnabled,
  });

  const isRunning = status?.status === "running" || status?.status === "stopping";

  useQuery({
    queryKey: ["train-status-init"],
    queryFn: async () => {
      const s = await getTrainStatus();
      if (s.status === "running" || s.status === "stopping") setPollingEnabled(true);
      return s;
    },
    staleTime: 0,
  });

  const { register, handleSubmit, formState: { errors }, reset } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: {
      learning_rate: 1e-4,
      num_epochs: 20,
      batch_size: 16,
      freeze_epochs: 3,
      min_per_class: 20,
      max_per_class: 1000,
      gradient_accumulation: 4,
      use_ema: false,
      use_mixup: false,
      num_workers: 2,
      early_stopping_patience: 7,
    },
  });

  useEffect(() => {
    if (!hw && !freezeInfo) return;
    const p = hw?.preset;
    reset((prev) => ({
      ...prev,
      batch_size:             p?.batch_size             ?? prev.batch_size,
      freeze_epochs:          freezeInfo?.freeze_epochs ?? prev.freeze_epochs,
      gradient_accumulation:  p?.gradient_accumulation  ?? prev.gradient_accumulation,
      use_ema:                p?.use_ema  != null ? Boolean(p.use_ema)  : prev.use_ema,
      use_mixup:              p?.use_mixup != null ? Boolean(p.use_mixup) : prev.use_mixup,
      num_workers:            p?.num_workers            ?? prev.num_workers,
    }));
  }, [hw, freezeInfo, reset]);

  const { mutateAsync: doStart, isPending: isStarting } = useMutation({
    mutationFn: (config: EfficientNetTrainConfig) => startTraining(config),
    onSuccess: () => {
      toast.success("학습이 시작되었습니다");
      setPollingEnabled(true);
    },
    onError: (e) => toast.error(extractErrorMessage(e)),
  });

  const { mutateAsync: doStop, isPending: isStopping } = useMutation({
    mutationFn: stopTraining,
    onSuccess: () => toast.info("학습 중지 요청이 전송되었습니다"),
    onError: (e) => toast.error(extractErrorMessage(e)),
  });

  const onSubmit = async (data: FormData) => {
    const config: EfficientNetTrainConfig = {
      ...data,
      max_per_class: data.max_per_class > 0 ? data.max_per_class : null,
      min_per_class: data.min_per_class > 0 ? data.min_per_class : null,
    };
    await doStart(config);
  };

  const pct = status?.total_steps && status.current_steps != null
    ? Math.round((status.current_steps / status.total_steps) * 100)
    : 0;

  const statusVariant: "default" | "secondary" | "destructive" | "outline" =
    status?.status === "running" ? "default"
    : status?.status === "done"  ? "default"
    : status?.status === "failed" ? "destructive"
    : "secondary";

  const logs      = logsData?.logs     ?? [];
  const rawLines  = rawLogData?.lines   ?? [];

  return (
    <div className="space-y-4">
      {/* Status card */}
      <div className="rounded-lg border">
        <div className="flex items-center gap-2 border-b bg-muted/30 px-4 py-3">
          <h2 className="text-base font-semibold">2. 모델 학습</h2>
          <Badge variant={statusVariant} className="ml-auto">
            {status?.status === "running"  ? "학습중"
              : status?.status === "done"  ? "완료"
              : status?.status === "failed" ? "실패"
              : status?.status === "stopping" ? "중지 중"
              : "대기중"}
          </Badge>
        </div>
        <div className="p-4 space-y-3">
          {status?.status === "running" && (
            <div className="space-y-2">
              <div className="grid grid-cols-4 gap-2">
                {[
                  { label: "Step",    value: `${status.current_steps ?? "-"}/${status.total_steps ?? "-"}` },
                  { label: "Epoch",   value: String(status.epoch ?? "-") },
                  { label: "Loss",    value: status.loss    != null ? status.loss.toFixed(4)               : "-" },
                  { label: "Val Acc", value: status.val_acc != null ? `${(status.val_acc * 100).toFixed(1)}%` : "-" },
                ].map(({ label, value }) => (
                  <div key={label} className="rounded border p-2 text-center">
                    <div className="text-sm font-semibold">{value}</div>
                    <div className="text-xs text-muted-foreground">{label}</div>
                  </div>
                ))}
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                <div className="h-full bg-primary transition-all" style={{ width: `${pct}%` }} />
              </div>
              <p className="text-xs text-muted-foreground text-right">{pct}%</p>
            </div>
          )}

          {logs.length > 0 && (
            <div className="rounded-md border p-2">
              <LossChart logs={logs} />
            </div>
          )}

          {rawLines.length > 0 && (
            <div className="rounded-md border bg-black/90">
              <div className="border-b px-3 py-1.5 text-xs text-muted-foreground">Raw Log</div>
              <div className="h-32 overflow-y-auto p-2">
                <pre className="text-xs text-green-400 leading-relaxed whitespace-pre-wrap break-all">
                  {rawLines.join("\n")}
                </pre>
              </div>
            </div>
          )}

          <div className="flex gap-2 flex-wrap">
            {isRunning ? (
              <>
                <Button variant="destructive" size="sm" disabled={isStopping} onClick={() => void doStop()}>
                  {isStopping ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Square className="mr-1 h-4 w-4" />}
                  학습 중지
                </Button>
                {(status?.current_steps ?? 0) === 0 && (
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={isStopping}
                    onClick={async () => { await doStop(); setPollingEnabled(false); }}
                  >
                    강제 초기화
                  </Button>
                )}
              </>
            ) : (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPollingEnabled(true)}
                disabled={pollingEnabled}
              >
                모니터링 시작
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* Config form */}
      <div className="rounded-lg border">
        <div className="border-b bg-muted/30 px-4 py-3">
          <h3 className="text-sm font-semibold">학습 설정</h3>
          {freezeInfo && (
            <p className="text-xs text-muted-foreground mt-0.5">
              freeze_epochs 권장: <span className="font-medium">{freezeInfo.freeze_epochs}</span> ({freezeInfo.reason})
            </p>
          )}
          {isRunning && (
            <p className="text-xs text-amber-500 mt-0.5">학습 중에는 설정을 변경할 수 없습니다.</p>
          )}
        </div>
        <form className="p-4 space-y-4" onSubmit={handleSubmit(onSubmit)}>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {FIELDS.map(({ name, label, hint }) => (
              <div key={name} className="space-y-1">
                <Label htmlFor={name} className="text-xs font-medium">{label}</Label>
                <Input
                  id={name}
                  {...register(name)}
                  disabled={isRunning}
                  className="h-8 text-sm"
                />
                {errors[name]
                  ? <p className="text-xs text-destructive">{errors[name]?.message}</p>
                  : hint && <p className="text-xs text-muted-foreground">{hint}</p>
                }
              </div>
            ))}
          </div>

          <div className="flex gap-4">
            {(["use_ema", "use_mixup"] as const).map((name) => (
              <label
                key={name}
                className={cn("flex items-center gap-2 text-sm", isRunning ? "cursor-not-allowed opacity-50" : "cursor-pointer")}
              >
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-input accent-primary"
                  disabled={isRunning}
                  {...register(name)}
                />
                {name === "use_ema" ? "EMA 사용" : "MixUp 사용"}
              </label>
            ))}
          </div>

          {!isRunning && (
            <Button type="submit" disabled={isStarting} className="w-full">
              {isStarting
                ? <><Loader2 className="mr-1 h-4 w-4 animate-spin" /> 시작 중...</>
                : <><Play   className="mr-1 h-4 w-4" /> 학습 시작</>}
            </Button>
          )}
        </form>
      </div>

      <div className="flex justify-between">
        <Button variant="outline" onClick={onBack}>
          <ArrowLeft className="mr-1 h-4 w-4" /> 이전
        </Button>
        <Button onClick={onNext}>
          다음: 배포 <ArrowRight className="ml-1 h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
