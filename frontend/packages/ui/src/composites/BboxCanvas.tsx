import { useEffect, useRef, useCallback } from "react";

type Bbox = [number, number, number, number];

interface Props {
  imageSrc: string;
  bbox: Bbox | null;
  yoloDetections?: Bbox[];
  editable?: boolean;
  onChange?: (bbox: Bbox) => void;
}

const HANDLE_PX = 8;

type DragMode = "draw" | "move" | "resize-tl" | "resize-tr" | "resize-bl" | "resize-br" | null;

function getHandleSize(canvas: HTMLCanvasElement): number {
  const r = canvas.getBoundingClientRect();
  return HANDLE_PX * (canvas.width / (r.width || 1));
}

function hitTest(
  pos: { x: number; y: number },
  bbox: Bbox | null,
  yoloBboxes: Bbox[],
  hs: number
): { type: DragMode | "select-yolo"; bbox?: Bbox } {
  if (bbox) {
    const [x1, y1, x2, y2] = bbox;
    const near = (a: number, v: number) => Math.abs(a - v) < hs;
    if (near(pos.x, x1) && near(pos.y, y1)) return { type: "resize-tl" };
    if (near(pos.x, x2) && near(pos.y, y1)) return { type: "resize-tr" };
    if (near(pos.x, x1) && near(pos.y, y2)) return { type: "resize-bl" };
    if (near(pos.x, x2) && near(pos.y, y2)) return { type: "resize-br" };
    if (pos.x > x1 && pos.x < x2 && pos.y > y1 && pos.y < y2) return { type: "move" };
  }
  for (const yb of yoloBboxes) {
    if (pos.x > yb[0] && pos.x < yb[2] && pos.y > yb[1] && pos.y < yb[3])
      return { type: "select-yolo", bbox: [...yb] as Bbox };
  }
  return { type: "draw" };
}

function cursorFor(type: string): string {
  if (type === "resize-tl" || type === "resize-br") return "nwse-resize";
  if (type === "resize-tr" || type === "resize-bl") return "nesw-resize";
  if (type === "move" || type === "select-yolo") return "move";
  return "crosshair";
}

function drawCanvas(
  canvas: HTMLCanvasElement,
  img: HTMLImageElement,
  currentBbox: Bbox | null,
  yoloBboxes: Bbox[]
) {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const lw = Math.max(2, canvas.width / 400);
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(img, 0, 0);

  // YOLO boxes (dashed, semi-transparent)
  for (const b of yoloBboxes) {
    if (
      currentBbox &&
      b[0] === currentBbox[0] && b[1] === currentBbox[1] &&
      b[2] === currentBbox[2] && b[3] === currentBbox[3]
    ) continue;
    ctx.save();
    ctx.strokeStyle = "rgba(34,197,94,0.5)";
    ctx.lineWidth = lw;
    ctx.setLineDash([6, 3]);
    ctx.strokeRect(b[0], b[1], b[2] - b[0], b[3] - b[1]);
    ctx.fillStyle = "rgba(34,197,94,0.04)";
    ctx.fillRect(b[0], b[1], b[2] - b[0], b[3] - b[1]);
    ctx.restore();
  }

  // Selected bbox with handles
  if (currentBbox) {
    const [x1, y1, x2, y2] = currentBbox;
    const hs = getHandleSize(canvas);
    ctx.save();
    ctx.fillStyle = "rgba(34,197,94,0.15)";
    ctx.fillRect(x1, y1, x2 - x1, y2 - y1);
    ctx.strokeStyle = "#22c55e";
    ctx.lineWidth = lw + 1;
    ctx.setLineDash([]);
    ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
    for (const [hx, hy] of [[x1, y1], [x2, y1], [x1, y2], [x2, y2]] as [number, number][]) {
      ctx.fillStyle = "#22c55e";
      ctx.fillRect(hx - hs / 2, hy - hs / 2, hs, hs);
      ctx.strokeStyle = "#fff";
      ctx.lineWidth = lw;
      ctx.strokeRect(hx - hs / 2, hy - hs / 2, hs, hs);
    }
    ctx.restore();
  }
}

export function BboxCanvas({ imageSrc, bbox, yoloDetections = [], editable = false, onChange }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);
  const bboxRef = useRef<Bbox | null>(bbox);
  const dragRef = useRef<{
    mode: DragMode;
    startPos: { x: number; y: number };
    startBbox: Bbox | null;
  } | null>(null);

  // Keep bbox ref in sync
  useEffect(() => { bboxRef.current = bbox; }, [bbox]);

  const redraw = useCallback(() => {
    const canvas = canvasRef.current;
    const img = imgRef.current;
    if (!canvas || !img) return;
    drawCanvas(canvas, img, bboxRef.current, yoloDetections);
  }, [yoloDetections]);

  // Load image
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    if (!imageSrc) {
      canvas.width = 400; canvas.height = 300;
      ctx.fillStyle = "#1a1a1a"; ctx.fillRect(0, 0, 400, 300);
      ctx.fillStyle = "#666"; ctx.font = "14px sans-serif";
      ctx.textAlign = "center"; ctx.fillText("이미지 없음", 200, 150);
      return;
    }

    const img = new Image();
    img.onload = () => {
      imgRef.current = img;
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
      redraw();
    };
    img.onerror = () => {
      canvas.width = 400; canvas.height = 300;
      ctx.fillStyle = "#1a1a1a"; ctx.fillRect(0, 0, 400, 300);
      ctx.fillStyle = "#ef4444"; ctx.font = "14px sans-serif";
      ctx.textAlign = "center"; ctx.fillText("이미지 로드 실패", 200, 150);
    };
    img.src = imageSrc;
  }, [imageSrc, redraw]);

  // Re-draw when bbox/yolo changes
  useEffect(() => { redraw(); }, [bbox, yoloDetections, redraw]);

  const getPos = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current!;
    const r = canvas.getBoundingClientRect();
    return {
      x: (e.clientX - r.left) * (canvas.width / r.width),
      y: (e.clientY - r.top) * (canvas.height / r.height),
    };
  };

  const clamp = (v: number, min: number, max: number) => Math.round(Math.max(min, Math.min(v, max)));

  const onPointerDown = useCallback((e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!editable || !imgRef.current) return;
    (e.currentTarget as HTMLCanvasElement).setPointerCapture(e.pointerId);
    const pos = getPos(e);
    const canvas = canvasRef.current!;
    const hs = getHandleSize(canvas);
    const hit = hitTest(pos, bboxRef.current, yoloDetections, hs);

    if (hit.type === "select-yolo" && hit.bbox) {
      bboxRef.current = hit.bbox;
      onChange?.(hit.bbox);
      dragRef.current = { mode: "move", startPos: pos, startBbox: [...hit.bbox] as Bbox };
      redraw();
    } else {
      dragRef.current = { mode: hit.type as DragMode, startPos: pos, startBbox: bboxRef.current ? [...bboxRef.current] as Bbox : null };
    }
  }, [editable, yoloDetections, onChange, redraw]);

  const onPointerMove = useCallback((e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!editable) return;
    const canvas = canvasRef.current!;
    const img = imgRef.current;
    if (!img) return;
    const pos = getPos(e);

    if (!dragRef.current?.mode) {
      const hs = getHandleSize(canvas);
      canvas.style.cursor = cursorFor(hitTest(pos, bboxRef.current, yoloDetections, hs).type ?? "draw");
      return;
    }

    const { mode, startPos, startBbox } = dragRef.current;
    const dx = pos.x - startPos.x;
    const dy = pos.y - startPos.y;
    const cx = (v: number) => clamp(v, 0, img.naturalWidth);
    const cy = (v: number) => clamp(v, 0, img.naturalHeight);

    let nb: Bbox;
    if (mode === "draw") {
      nb = [cx(Math.min(startPos.x, pos.x)), cy(Math.min(startPos.y, pos.y)),
            cx(Math.max(startPos.x, pos.x)), cy(Math.max(startPos.y, pos.y))];
    } else if (mode === "move" && startBbox) {
      const [x1, y1, x2, y2] = startBbox;
      const bw = x2 - x1, bh = y2 - y1;
      const nx1 = cx(x1 + dx);
      const ny1 = cy(y1 + dy);
      nb = [nx1, ny1, cx(nx1 + bw), cy(ny1 + bh)];
    } else if (startBbox) {
      let [x1, y1, x2, y2] = [...startBbox] as Bbox;
      if (mode === "resize-tl") { x1 = cx(x1 + dx); y1 = cy(y1 + dy); }
      else if (mode === "resize-tr") { x2 = cx(x2 + dx); y1 = cy(y1 + dy); }
      else if (mode === "resize-bl") { x1 = cx(x1 + dx); y2 = cy(y2 + dy); }
      else if (mode === "resize-br") { x2 = cx(x2 + dx); y2 = cy(y2 + dy); }
      nb = [Math.min(x1, x2), Math.min(y1, y2), Math.max(x1, x2), Math.max(y1, y2)];
    } else return;

    bboxRef.current = nb;
    redraw();
  }, [editable, yoloDetections, redraw]);

  const onPointerUp = useCallback((e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!editable || !dragRef.current?.mode) return;
    (e.currentTarget as HTMLCanvasElement).releasePointerCapture(e.pointerId);
    const { mode } = dragRef.current;
    const cur = bboxRef.current;
    if (mode === "draw" && cur) {
      const [x1, y1, x2, y2] = cur;
      if (x2 - x1 < 5 || y2 - y1 < 5) {
        bboxRef.current = dragRef.current.startBbox;
        redraw();
      } else {
        onChange?.(cur);
      }
    } else if (cur) {
      onChange?.(cur);
    }
    dragRef.current = null;
  }, [editable, onChange, redraw]);

  return (
    <div className="relative rounded-md overflow-hidden bg-black/80">
      <canvas
        ref={canvasRef}
        className="block w-full h-auto"
        style={{ cursor: editable ? "crosshair" : "default", touchAction: "none" }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
      />
    </div>
  );
}
