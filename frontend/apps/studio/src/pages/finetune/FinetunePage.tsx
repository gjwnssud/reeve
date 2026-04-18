import { useState } from "react";
import { cn } from "@reeve/ui";
import { DataStep } from "./DataStep";
import { TrainStep } from "./TrainStep";
import { DeployStep } from "./DeployStep";

type Step = 0 | 1 | 2;

const STEPS = [
  { label: "데이터 준비", sub: "데이터 확인" },
  { label: "모델 학습", sub: "학습 실행 및 모니터링" },
  { label: "배포", sub: "Identifier 적용" },
];

export function FinetunePage() {
  const [step, setStep] = useState<Step>(0);

  return (
    <div className="mx-auto max-w-5xl p-6">
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold">파인튜닝 관리</h1>
          <p className="text-sm text-muted-foreground mt-1">모델을 파인튜닝하고 식별 서비스에 배포합니다.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[200px_1fr]">
        {/* Step nav */}
        <aside>
          <div className="sticky top-6 rounded-lg border overflow-hidden">
            <div className="px-3 py-2.5 text-sm font-semibold text-white" style={{ background: "linear-gradient(135deg,#667eea,#764ba2)" }}>
              파인튜닝 단계
            </div>
            <div className="divide-y">
              {STEPS.map(({ label, sub }, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => setStep(i as Step)}
                  className={cn(
                    "flex w-full items-center gap-3 px-3 py-3 text-left transition hover:bg-muted/50",
                    step === i && "bg-muted"
                  )}
                >
                  <span className={cn(
                    "flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold",
                    step === i ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"
                  )}>
                    {i + 1}
                  </span>
                  <div>
                    <div className="text-sm font-medium">{label}</div>
                    <div className="text-xs text-muted-foreground">{sub}</div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </aside>

        {/* Content */}
        <main>
          {step === 0 && <DataStep onNext={() => setStep(1)} />}
          {step === 1 && <TrainStep onBack={() => setStep(0)} onNext={() => setStep(2)} />}
          {step === 2 && <DeployStep onBack={() => setStep(1)} />}
        </main>
      </div>
    </div>
  );
}
