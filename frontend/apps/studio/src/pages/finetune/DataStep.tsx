import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button, Badge, Skeleton } from "@reeve/ui";
import { Download, AlertTriangle, ArrowRight, Loader2 } from "lucide-react";

import {
  getFinetuneStats, getFinetuneMode, exportEfficientNet,
  extractErrorMessage, type FinetuneModelStatsEntry,
} from "../../lib/api";

interface Props {
  onNext: () => void;
}

export function DataStep({ onNext }: Props) {
  const [exportResult, setExportResult] = useState<string | null>(null);

  const { data: mode } = useQuery({ queryKey: ["finetune-mode"], queryFn: getFinetuneMode });
  const { data: stats, isLoading } = useQuery({ queryKey: ["finetune-stats"], queryFn: getFinetuneStats });

  const { mutateAsync: doExport, isPending: isExporting } = useMutation({
    mutationFn: () => exportEfficientNet({ split: 0.9 }),
    onSuccess: (res) => {
      setExportResult(`완료: train ${res.counts.train_count}건 / val ${res.counts.val_count}건 / ${res.num_classes}종`);
      toast.success("데이터 내보내기 완료");
    },
    onError: (e) => toast.error(extractErrorMessage(e)),
  });

  const isEfficientNet = mode?.identifier_mode !== "vlm_only";
  const total = stats?.total ?? 0;
  const numClasses = stats?.num_classes ?? 0;
  const maxMfCount = Math.max(...(stats?.by_manufacturer.map((m) => m.count) ?? [1]));
  const maxModelCount = Math.max(...(stats?.by_model.map((m) => m.count) ?? [1]));

  return (
    <div className="space-y-4">
      <div className="rounded-lg border">
        <div className="border-b bg-muted/30 px-4 py-3">
          <h2 className="text-base font-semibold">1. 학습 데이터 현황</h2>
        </div>
        <div className="p-4 space-y-4">
          <div className="flex items-center gap-2">
            <Badge variant={isEfficientNet ? "default" : "secondary"}>
              {isEfficientNet ? "EfficientNet 모드" : "VLM Only 모드"}
            </Badge>
          </div>

          <div className="grid grid-cols-2 gap-3">
            {isLoading ? (
              <>
                <Skeleton className="h-20 rounded-lg" />
                <Skeleton className="h-20 rounded-lg" />
              </>
            ) : (
              <>
                <div className="rounded-lg border p-4 text-center">
                  <div className="text-3xl font-bold text-primary">{total.toLocaleString()}</div>
                  <div className="mt-1 text-xs text-muted-foreground">총 학습 이미지</div>
                </div>
                <div className="rounded-lg border p-4 text-center">
                  <div className="text-3xl font-bold text-primary">{numClasses}</div>
                  <div className="mt-1 text-xs text-muted-foreground">차종 수 (제조사×모델)</div>
                </div>
              </>
            )}
          </div>

          {!isLoading && total < 100 && (
            <div className="flex items-start gap-2 rounded-md border border-yellow-200 bg-yellow-50 p-3 text-sm text-yellow-800 dark:border-yellow-900 dark:bg-yellow-950/30 dark:text-yellow-400">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              학습 데이터가 100건 미만입니다. 더 많은 데이터를 추가한 후 학습을 시작하세요.
            </div>
          )}

          {stats && (stats.by_manufacturer.length > 0 || stats.by_model.length > 0) && (
            <div className="grid grid-cols-2 gap-4">
              {stats.by_manufacturer.length > 0 && (
                <div className="space-y-2">
                  <div className="text-xs font-medium text-muted-foreground">제조사별 분포</div>
                  <div className="max-h-96 overflow-y-auto rounded-md border">
                    <table className="w-full text-sm">
                      <thead className="sticky top-0 border-b bg-muted">
                        <tr>
                          <th className="px-3 py-2 text-left font-medium text-muted-foreground">제조사</th>
                          <th className="px-3 py-2 text-right font-medium text-muted-foreground">이미지</th>
                          <th className="px-3 py-2 text-left font-medium text-muted-foreground w-28">비율</th>
                        </tr>
                      </thead>
                      <tbody>
                        {stats.by_manufacturer.map((m) => (
                          <tr key={m.manufacturer_id} className="border-b last:border-0">
                            <td className="px-3 py-2">{m.korean_name}</td>
                            <td className="px-3 py-2 text-right tabular-nums">{m.count.toLocaleString()}</td>
                            <td className="px-3 py-2">
                              <div className="flex items-center gap-2">
                                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                                  <div
                                    className="h-full rounded-full bg-primary"
                                    style={{ width: `${(m.count / maxMfCount) * 100}%` }}
                                  />
                                </div>
                                <span className="text-xs text-muted-foreground w-8 text-right">
                                  {Math.round((m.count / total) * 100)}%
                                </span>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {stats.by_model.length > 0 && (
                <div className="space-y-2">
                  <div className="text-xs font-medium text-muted-foreground">
                    모델별 분포 <span className="text-muted-foreground/60">({stats.by_model.length}종)</span>
                  </div>
                  <div className="max-h-96 overflow-y-auto rounded-md border">
                    <table className="w-full text-sm">
                      <thead className="sticky top-0 border-b bg-muted">
                        <tr>
                          <th className="px-3 py-2 text-left font-medium text-muted-foreground">모델</th>
                          <th className="px-3 py-2 text-right font-medium text-muted-foreground">이미지</th>
                          <th className="px-3 py-2 text-left font-medium text-muted-foreground w-28">비율</th>
                        </tr>
                      </thead>
                      <tbody>
                        {stats.by_model.map((m: FinetuneModelStatsEntry) => (
                          <tr key={m.model_id} className="border-b last:border-0">
                            <td className="px-3 py-2">
                              <div className="font-medium leading-tight">{m.korean_name}</div>
                              <div className="text-xs text-muted-foreground">{m.manufacturer_korean}</div>
                            </td>
                            <td className="px-3 py-2 text-right tabular-nums">{m.count.toLocaleString()}</td>
                            <td className="px-3 py-2">
                              <div className="flex items-center gap-2">
                                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                                  <div
                                    className="h-full rounded-full bg-primary"
                                    style={{ width: `${(m.count / maxModelCount) * 100}%` }}
                                  />
                                </div>
                                <span className="text-xs text-muted-foreground w-8 text-right">
                                  {((m.count / total) * 100).toFixed(1)}%
                                </span>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}

          {isEfficientNet && (
            <div className="space-y-2">
              {exportResult && (
                <p className="text-xs text-green-600 dark:text-green-400">{exportResult}</p>
              )}
              <Button
                variant="outline"
                size="sm"
                disabled={isExporting || total === 0}
                onClick={() => void doExport()}
              >
                {isExporting ? (
                  <><Loader2 className="mr-1 h-4 w-4 animate-spin" /> 내보내는 중...</>
                ) : (
                  <><Download className="mr-1 h-4 w-4" /> 데이터 내보내기 (CSV)</>
                )}
              </Button>
            </div>
          )}
        </div>
      </div>

      <div className="flex justify-end">
        <Button onClick={onNext}>
          다음: 모델 학습 <ArrowRight className="ml-1 h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
