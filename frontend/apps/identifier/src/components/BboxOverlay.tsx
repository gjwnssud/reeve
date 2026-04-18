import {
  memo,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type RefObject,
} from "react";

type Bbox = [number, number, number, number];
type Handle = "nw" | "ne" | "sw" | "se";

export type BboxOverlayProps = {
  imageRef: RefObject<HTMLImageElement | null>;
  imageWidth: number;
  imageHeight: number;
  bbox: Bbox;
  editable?: boolean;
  minSize?: number;
  label?: string;
  onChange?: (bbox: Bbox) => void;
};

const HANDLES: Handle[] = ["nw", "ne", "sw", "se"];

export const BboxOverlay = memo(function BboxOverlay({
  imageRef,
  imageWidth,
  imageHeight,
  bbox,
  editable = false,
  minSize = 50,
  label,
  onChange,
}: BboxOverlayProps) {
  const [displaySize, setDisplaySize] = useState({ w: 0, h: 0 });
  const boxRef = useRef<HTMLDivElement | null>(null);

  // 이미지 표시 크기를 추적. 리사이즈 옵저버로 브라우저 리사이즈/CSS 변경에 반응.
  useLayoutEffect(() => {
    const img = imageRef.current;
    if (!img) return;

    const update = () => {
      setDisplaySize({ w: img.clientWidth, h: img.clientHeight });
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(img);
    window.addEventListener("resize", update);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", update);
    };
  }, [imageRef]);

  const scaleX = imageWidth > 0 ? displaySize.w / imageWidth : 0;
  const scaleY = imageHeight > 0 ? displaySize.h / imageHeight : 0;

  const [x1, y1, x2, y2] = bbox;
  const left = x1 * scaleX;
  const top = y1 * scaleY;
  const width = (x2 - x1) * scaleX;
  const height = (y2 - y1) * scaleY;

  // 드래그 — 박스 이동
  const onBoxPointerDown = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      if (!editable || !onChange) return;
      if ((e.target as HTMLElement).dataset.handle) return; // 핸들은 따로 처리
      e.preventDefault();

      const boxEl = boxRef.current;
      const img = imageRef.current;
      if (!boxEl || !img) return;

      boxEl.setPointerCapture(e.pointerId);
      const startX = e.clientX;
      const startY = e.clientY;
      const [sx1, sy1, sx2, sy2] = bbox;
      const sW = sx2 - sx1;
      const sH = sy2 - sy1;

      const onMove = (me: PointerEvent) => {
        const dx = (me.clientX - startX) / scaleX;
        const dy = (me.clientY - startY) / scaleY;
        let nx1 = Math.round(sx1 + dx);
        let ny1 = Math.round(sy1 + dy);
        nx1 = Math.max(0, Math.min(imageWidth - sW, nx1));
        ny1 = Math.max(0, Math.min(imageHeight - sH, ny1));
        onChange([nx1, ny1, nx1 + sW, ny1 + sH]);
      };
      const onUp = () => {
        boxEl.removeEventListener("pointermove", onMove);
        boxEl.removeEventListener("pointerup", onUp);
        boxEl.removeEventListener("pointercancel", onUp);
      };
      boxEl.addEventListener("pointermove", onMove);
      boxEl.addEventListener("pointerup", onUp);
      boxEl.addEventListener("pointercancel", onUp);
    },
    [editable, onChange, bbox, scaleX, scaleY, imageRef, imageWidth, imageHeight],
  );

  // 리사이즈 — 각 핸들별
  const onHandlePointerDown = useCallback(
    (handle: Handle) => (e: React.PointerEvent<HTMLDivElement>) => {
      if (!editable || !onChange) return;
      e.preventDefault();
      e.stopPropagation();

      const target = e.currentTarget;
      target.setPointerCapture(e.pointerId);
      const startX = e.clientX;
      const startY = e.clientY;
      const [sx1, sy1, sx2, sy2] = bbox;

      const onMove = (me: PointerEvent) => {
        const dx = (me.clientX - startX) / scaleX;
        const dy = (me.clientY - startY) / scaleY;
        let nx1 = sx1;
        let ny1 = sy1;
        let nx2 = sx2;
        let ny2 = sy2;
        if (handle === "nw") {
          nx1 = sx1 + dx;
          ny1 = sy1 + dy;
        } else if (handle === "ne") {
          nx2 = sx2 + dx;
          ny1 = sy1 + dy;
        } else if (handle === "sw") {
          nx1 = sx1 + dx;
          ny2 = sy2 + dy;
        } else {
          nx2 = sx2 + dx;
          ny2 = sy2 + dy;
        }
        // 최소 크기 보장
        if (nx2 - nx1 < minSize) {
          if (handle === "nw" || handle === "sw") nx1 = nx2 - minSize;
          else nx2 = nx1 + minSize;
        }
        if (ny2 - ny1 < minSize) {
          if (handle === "nw" || handle === "ne") ny1 = ny2 - minSize;
          else ny2 = ny1 + minSize;
        }
        // 이미지 범위
        nx1 = Math.max(0, Math.min(imageWidth, nx1));
        ny1 = Math.max(0, Math.min(imageHeight, ny1));
        nx2 = Math.max(0, Math.min(imageWidth, nx2));
        ny2 = Math.max(0, Math.min(imageHeight, ny2));
        onChange([Math.round(nx1), Math.round(ny1), Math.round(nx2), Math.round(ny2)]);
      };
      const onUp = () => {
        target.removeEventListener("pointermove", onMove);
        target.removeEventListener("pointerup", onUp);
        target.removeEventListener("pointercancel", onUp);
      };
      target.addEventListener("pointermove", onMove);
      target.addEventListener("pointerup", onUp);
      target.addEventListener("pointercancel", onUp);
    },
    [editable, onChange, bbox, scaleX, scaleY, minSize, imageWidth, imageHeight],
  );

  // 이미지가 아직 로드되지 않았으면 그리지 않음
  useEffect(() => {
    if (!imageRef.current?.complete) return;
  }, [imageRef]);

  if (displaySize.w === 0 || imageWidth === 0) return null;

  return (
    <div
      ref={boxRef}
      className="pointer-events-auto absolute rounded border-2 border-emerald-400 bg-emerald-400/15"
      style={{
        left,
        top,
        width,
        height,
        cursor: editable ? "move" : "default",
        touchAction: "none",
      }}
      onPointerDown={onBoxPointerDown}
    >
      {label ? (
        <div className="absolute -top-6 left-0 rounded bg-emerald-500 px-2 py-0.5 text-xs font-medium text-white">
          {label}
        </div>
      ) : null}
      {editable
        ? HANDLES.map((h) => (
            <div
              key={h}
              data-handle={h}
              onPointerDown={onHandlePointerDown(h)}
              className="absolute h-3 w-3 rounded-sm border border-white bg-emerald-500"
              style={handleStyle(h)}
            />
          ))
        : null}
    </div>
  );
});

function handleStyle(h: Handle): React.CSSProperties {
  const base: React.CSSProperties = { touchAction: "none" };
  if (h === "nw") return { ...base, left: -6, top: -6, cursor: "nw-resize" };
  if (h === "ne") return { ...base, right: -6, top: -6, cursor: "ne-resize" };
  if (h === "sw") return { ...base, left: -6, bottom: -6, cursor: "sw-resize" };
  return { ...base, right: -6, bottom: -6, cursor: "se-resize" };
}
