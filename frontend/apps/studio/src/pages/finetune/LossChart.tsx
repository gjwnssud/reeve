import { useEffect, useRef } from "react";
import type { LogEntry } from "../../lib/api";

interface Props {
  logs: LogEntry[];
}

export function LossChart({ logs }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const losses = logs.filter((l) => l.loss != null && typeof l.loss === "number");
    const W = canvas.width;
    const H = canvas.height;

    ctx.clearRect(0, 0, W, H);

    const isDark = document.documentElement.dataset["theme"] === "dark";
    const bgColor = isDark ? "#1a1a1a" : "#f8f9fa";
    const gridColor = isDark ? "#333" : "#e5e7eb";
    const textColor = isDark ? "#9ca3af" : "#6b7280";
    const lossColor = "#667eea";
    const accColor = "#22c55e";

    ctx.fillStyle = bgColor;
    ctx.fillRect(0, 0, W, H);

    if (losses.length < 2) {
      ctx.fillStyle = textColor;
      ctx.font = "12px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("학습 데이터 대기 중...", W / 2, H / 2);
      return;
    }

    const PAD = { top: 20, right: 20, bottom: 35, left: 50 };
    const chartW = W - PAD.left - PAD.right;
    const chartH = H - PAD.top - PAD.bottom;

    // Grid lines (5 horizontal)
    const lossVals = losses.map((l) => l.loss as number);
    const minLoss = Math.min(...lossVals) * 0.9;
    const maxLoss = Math.max(...lossVals) * 1.1;

    ctx.strokeStyle = gridColor;
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const y = PAD.top + (i / 4) * chartH;
      ctx.beginPath(); ctx.moveTo(PAD.left, y); ctx.lineTo(PAD.left + chartW, y); ctx.stroke();
      const v = maxLoss - (i / 4) * (maxLoss - minLoss);
      ctx.fillStyle = textColor;
      ctx.font = "10px monospace";
      ctx.textAlign = "right";
      ctx.fillText(v.toFixed(3), PAD.left - 4, y + 3);
    }

    // Loss line
    const toX = (i: number) => PAD.left + (i / (losses.length - 1)) * chartW;
    const toY = (v: number) => PAD.top + ((maxLoss - v) / (maxLoss - minLoss)) * chartH;

    ctx.beginPath();
    ctx.strokeStyle = lossColor;
    ctx.lineWidth = 2;
    ctx.lineJoin = "round";
    losses.forEach((l, i) => {
      const x = toX(i), y = toY(l.loss as number);
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // Val acc line (if available)
    const accLogs = logs.filter((l) => l.val_acc != null && typeof l.val_acc === "number");
    if (accLogs.length > 1) {
      const accVals = accLogs.map((l) => l.val_acc as number);
      const minAcc = 0;
      const maxAcc = 1;
      const toYAcc = (v: number) => PAD.top + ((maxAcc - v) / (maxAcc - minAcc)) * chartH;

      ctx.beginPath();
      ctx.strokeStyle = accColor;
      ctx.lineWidth = 2;
      ctx.setLineDash([4, 2]);
      accLogs.forEach((l, i) => {
        const ratio = i / (accLogs.length - 1);
        const x = PAD.left + ratio * chartW;
        const y = toYAcc(l.val_acc as number);
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      });
      ctx.stroke();
      ctx.setLineDash([]);

      // Val acc right axis label
      ctx.fillStyle = accColor;
      ctx.font = "10px sans-serif";
      ctx.textAlign = "left";
      const lastAcc = accLogs[accLogs.length - 1]?.val_acc as number;
      ctx.fillText(`acc ${(lastAcc * 100).toFixed(1)}%`, PAD.left + chartW + 2, toYAcc(lastAcc) + 3);
    }

    // X-axis labels
    ctx.fillStyle = textColor;
    ctx.font = "10px sans-serif";
    ctx.textAlign = "center";
    const steps = [0, Math.floor(losses.length / 2), losses.length - 1];
    for (const i of steps) {
      const l = losses[i];
      if (!l) continue;
      const label = l.step != null ? `s${l.step}` : l.epoch != null ? `e${l.epoch}` : String(i);
      ctx.fillText(label, toX(i), PAD.top + chartH + 18);
    }

    // Legend
    ctx.font = "10px sans-serif";
    ctx.fillStyle = lossColor;
    ctx.fillRect(PAD.left, PAD.top + chartH + 24, 10, 2);
    ctx.fillStyle = textColor;
    ctx.textAlign = "left";
    ctx.fillText("loss", PAD.left + 12, PAD.top + chartH + 27);
  }, [logs]);

  return (
    <canvas
      ref={canvasRef}
      width={500}
      height={200}
      className="w-full h-auto rounded-md"
    />
  );
}
