import { useEffect, useRef } from "react";

export interface ChartSeries {
  label: string;
  color: string;
  /** [x, y] 페어. y가 null이면 그 점은 건너뜀. */
  points: Array<[number, number | null]>;
  dashed?: boolean;
}

interface Props {
  series: ChartSeries[];
  yLabel?: string;
  xLabel?: string;
  yMin?: number;
  yMax?: number;
  height?: number;
}

export function MetricsChart({ series, yLabel, xLabel, yMin, yMax, height = 220 }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // DPR scale
    const dpr = window.devicePixelRatio || 1;
    const cssW = canvas.clientWidth || 600;
    const cssH = height;
    if (canvas.width !== cssW * dpr || canvas.height !== cssH * dpr) {
      canvas.width = cssW * dpr;
      canvas.height = cssH * dpr;
    }
    canvas.style.height = `${cssH}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const W = cssW;
    const H = cssH;
    const isDark = document.documentElement.dataset["theme"] === "dark";
    const bg = isDark ? "#1a1a1a" : "#f8f9fa";
    const grid = isDark ? "#333" : "#e5e7eb";
    const text = isDark ? "#9ca3af" : "#6b7280";

    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, W, H);

    // 유효 포인트 수집
    const allYs: number[] = [];
    const allXs: number[] = [];
    for (const s of series) {
      for (const [x, y] of s.points) {
        if (y == null || Number.isNaN(y)) continue;
        allYs.push(y);
        allXs.push(x);
      }
    }
    if (allYs.length === 0) {
      ctx.fillStyle = text;
      ctx.font = "12px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("데이터 없음", W / 2, H / 2);
      return;
    }

    const xMin = Math.min(...allXs);
    const xMax = Math.max(...allXs);
    const yLo = yMin != null ? yMin : Math.min(...allYs);
    const yHi = yMax != null ? yMax : Math.max(...allYs);
    const ySpan = yHi - yLo || 1;
    const xSpan = xMax - xMin || 1;

    const PAD = { top: 16, right: 16, bottom: 32, left: 50 };
    const cw = W - PAD.left - PAD.right;
    const ch = H - PAD.top - PAD.bottom;

    // 격자 + Y 레이블
    ctx.strokeStyle = grid;
    ctx.lineWidth = 1;
    ctx.fillStyle = text;
    ctx.font = "10px monospace";
    ctx.textAlign = "right";
    for (let i = 0; i <= 4; i++) {
      const y = PAD.top + (i / 4) * ch;
      ctx.beginPath();
      ctx.moveTo(PAD.left, y);
      ctx.lineTo(PAD.left + cw, y);
      ctx.stroke();
      const v = yHi - (i / 4) * ySpan;
      ctx.fillText(v.toFixed(2), PAD.left - 4, y + 3);
    }

    // X 레이블
    ctx.textAlign = "center";
    const xTicks = [0, 0.5, 1];
    for (const t of xTicks) {
      const x = PAD.left + t * cw;
      const v = xMin + t * xSpan;
      ctx.fillText(v.toFixed(0), x, PAD.top + ch + 16);
    }

    // 시리즈 그리기
    const toX = (v: number) => PAD.left + ((v - xMin) / xSpan) * cw;
    const toY = (v: number) => PAD.top + ((yHi - v) / ySpan) * ch;

    for (const s of series) {
      ctx.strokeStyle = s.color;
      ctx.lineWidth = 2;
      ctx.lineJoin = "round";
      ctx.setLineDash(s.dashed ? [4, 3] : []);
      ctx.beginPath();
      let started = false;
      for (const [px, py] of s.points) {
        if (py == null || Number.isNaN(py)) {
          started = false;
          continue;
        }
        const cx = toX(px);
        const cy = toY(py);
        if (!started) {
          ctx.moveTo(cx, cy);
          started = true;
        } else {
          ctx.lineTo(cx, cy);
        }
      }
      ctx.stroke();
    }
    ctx.setLineDash([]);

    // 범례
    ctx.font = "10px sans-serif";
    ctx.textAlign = "left";
    let lx = PAD.left;
    const ly = H - 4;
    for (const s of series) {
      ctx.strokeStyle = s.color;
      ctx.lineWidth = 2;
      ctx.setLineDash(s.dashed ? [4, 3] : []);
      ctx.beginPath();
      ctx.moveTo(lx, ly - 3);
      ctx.lineTo(lx + 14, ly - 3);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = text;
      ctx.fillText(s.label, lx + 18, ly);
      lx += ctx.measureText(s.label).width + 36;
    }

    // Y/X 축 레이블
    if (yLabel) {
      ctx.save();
      ctx.translate(12, PAD.top + ch / 2);
      ctx.rotate(-Math.PI / 2);
      ctx.fillStyle = text;
      ctx.textAlign = "center";
      ctx.fillText(yLabel, 0, 0);
      ctx.restore();
    }
    if (xLabel) {
      ctx.fillStyle = text;
      ctx.textAlign = "center";
      ctx.fillText(xLabel, PAD.left + cw / 2, H - 18);
    }
  }, [series, yLabel, xLabel, yMin, yMax, height]);

  return <canvas ref={canvasRef} className="w-full" style={{ height }} />;
}
