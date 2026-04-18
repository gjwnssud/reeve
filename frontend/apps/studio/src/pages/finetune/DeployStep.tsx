import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button, Skeleton } from "@reeve/ui";
import { ArrowLeft, Zap, BarChart2, Loader2 } from "lucide-react";

import { evaluateModel, extractErrorMessage, type EvaluateResult } from "../../lib/api";

interface Props {
  onBack: () => void;
}

export function DeployStep({ onBack }: Props) {
  const [evalResult, setEvalResult] = useState<EvaluateResult | null>(null);

  const { mutateAsync: doReload, isPending: isReloading } = useMutation({
    mutationFn: async () => {
      const res = await fetch("/admin/reload-efficientnet", { method: "POST" });
      if (!res.ok) {
        const body = await res.json().catch(() => ({})) as { detail?: string };
        throw new Error(body.detail ?? `HTTP ${res.status}`);
      }
      return res.json();
    },
    onSuccess: () => toast.success("모델 핫리로드 완료"),
    onError: (e) => toast.error(extractErrorMessage(e)),
  });

  const { mutateAsync: doEvaluate, isPending: isEvaluating } = useMutation({
    mutationFn: () => evaluateModel(50),
    onSuccess: (r) => {
      setEvalResult(r);
      toast.success(`평가 완료: 정확도 ${r.accuracy}%`);
    },
    onError: (e) => toast.error(extractErrorMessage(e)),
  });

  return (
    <div className="space-y-4">
      {/* Reload */}
      <div className="rounded-lg border">
        <div className="border-b bg-muted/30 px-4 py-3">
          <h2 className="text-base font-semibold">3. 배포</h2>
        </div>
        <div className="p-4 space-y-3">
          <p className="text-sm text-muted-foreground">
            학습 완료 후 EfficientNet 모델을 Identifier 서비스에 핫리로드합니다.<br />
            재시작 없이 즉시 반영됩니다.
          </p>
          <Button onClick={() => void doReload()} disabled={isReloading}>
            {isReloading
              ? <><Loader2 className="mr-1 h-4 w-4 animate-spin" /> 리로드 중...</>
              : <><Zap className="mr-1 h-4 w-4" /> EfficientNet 핫리로드</>}
          </Button>
        </div>
      </div>

      {/* Evaluate */}
      <div className="rounded-lg border">
        <div className="border-b bg-muted/30 px-4 py-3">
          <h3 className="text-sm font-semibold">정확도 평가</h3>
        </div>
        <div className="p-4 space-y-3">
          <p className="text-sm text-muted-foreground">
            학습 데이터 샘플 50건으로 Before/After 정확도를 비교합니다.
          </p>
          <Button variant="outline" size="sm" onClick={() => void doEvaluate()} disabled={isEvaluating}>
            {isEvaluating
              ? <><Loader2 className="mr-1 h-4 w-4 animate-spin" /> 평가 중...</>
              : <><BarChart2 className="mr-1 h-4 w-4" /> 평가 실행 (샘플 50건)</>}
          </Button>

          {isEvaluating && <Skeleton className="h-24 rounded-lg" />}

          {evalResult && (
            <div className="rounded-md border bg-muted/30 p-4 space-y-2">
              <div className="grid grid-cols-3 gap-3 text-center">
                {[
                  { label: "정확도", value: `${evalResult.accuracy}%` },
                  { label: "평균 신뢰도", value: `${(evalResult.avg_confidence * 100).toFixed(1)}%` },
                  { label: "평가 수", value: `${evalResult.evaluated}/${evalResult.total}` },
                ].map(({ label, value }) => (
                  <div key={label} className="rounded border bg-background p-2">
                    <div className="text-lg font-bold text-primary">{value}</div>
                    <div className="text-xs text-muted-foreground">{label}</div>
                  </div>
                ))}
              </div>
              {evalResult.incorrect_count > 0 && (
                <p className="text-xs text-muted-foreground">
                  오분류 {evalResult.incorrect_count}건 (상세는 콘솔 로그 확인)
                </p>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="flex justify-between">
        <Button variant="outline" onClick={onBack}>
          <ArrowLeft className="mr-1 h-4 w-4" /> 이전
        </Button>
      </div>
    </div>
  );
}
