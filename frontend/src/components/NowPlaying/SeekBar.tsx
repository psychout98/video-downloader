import { useState, useRef, useCallback, useEffect } from 'react';
import { formatMs } from '../../utils/format';

interface Props {
  positionMs: number;
  durationMs: number;
  onSeek: (positionMs: number) => void;
  /** When true, the parent should skip updating positionMs from SSE. */
  onDraggingChange?: (dragging: boolean) => void;
}

function SeekBar({ positionMs, durationMs, onSeek, onDraggingChange }: Props) {
  const barRef = useRef<HTMLDivElement>(null);
  const [dragging, setDragging] = useState(false);
  const [hoverX, setHoverX] = useState<number | null>(null);
  const [dragFraction, setDragFraction] = useState(0);

  const progress = durationMs > 0 ? positionMs / durationMs : 0;
  const displayFraction = dragging ? dragFraction : progress;

  const clamp = (v: number, min: number, max: number) =>
    Math.min(Math.max(v, min), max);

  const getFraction = useCallback(
    (clientX: number): number => {
      if (!barRef.current) return 0;
      const rect = barRef.current.getBoundingClientRect();
      return clamp((clientX - rect.left) / rect.width, 0, 1);
    },
    [],
  );

  // Notify parent when drag state changes
  useEffect(() => {
    onDraggingChange?.(dragging);
  }, [dragging, onDraggingChange]);

  // Mouse / touch handlers
  const handlePointerDown = useCallback(
    (clientX: number) => {
      const frac = getFraction(clientX);
      setDragging(true);
      setDragFraction(frac);
    },
    [getFraction],
  );

  const handlePointerMove = useCallback(
    (clientX: number) => {
      if (!dragging) {
        setHoverX(clientX);
        return;
      }
      setDragFraction(getFraction(clientX));
    },
    [dragging, getFraction],
  );

  const handlePointerUp = useCallback(() => {
    if (!dragging) return;
    setDragging(false);
    onSeek(Math.round(dragFraction * durationMs));
  }, [dragging, dragFraction, durationMs, onSeek]);

  // Attach window-level listeners while dragging so the user can
  // release the mouse outside the bar.
  useEffect(() => {
    if (!dragging) return;
    const onMove = (e: MouseEvent) => handlePointerMove(e.clientX);
    const onUp = () => handlePointerUp();
    const onTouchMove = (e: TouchEvent) => handlePointerMove(e.touches[0].clientX);
    const onTouchEnd = () => handlePointerUp();

    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    window.addEventListener('touchmove', onTouchMove);
    window.addEventListener('touchend', onTouchEnd);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      window.removeEventListener('touchmove', onTouchMove);
      window.removeEventListener('touchend', onTouchEnd);
    };
  }, [dragging, handlePointerMove, handlePointerUp]);

  // Tooltip position & time
  const hoverFraction =
    hoverX !== null && barRef.current
      ? getFraction(hoverX)
      : null;
  const tooltipTime =
    hoverFraction !== null ? formatMs(hoverFraction * durationMs) : null;
  const tooltipLeft =
    hoverFraction !== null ? `${hoverFraction * 100}%` : undefined;

  return (
    <div className="select-none">
      {/* Seek bar track */}
      <div
        ref={barRef}
        className="relative h-3 bg-dark-bg rounded-full cursor-pointer group"
        onMouseDown={(e) => handlePointerDown(e.clientX)}
        onTouchStart={(e) => handlePointerDown(e.touches[0].clientX)}
        onMouseMove={(e) => {
          if (!dragging) setHoverX(e.clientX);
        }}
        onMouseLeave={() => {
          if (!dragging) setHoverX(null);
        }}
      >
        {/* Filled portion */}
        <div
          className="absolute inset-y-0 left-0 bg-dark-accent rounded-full transition-[width] duration-75"
          style={{ width: `${displayFraction * 100}%` }}
        />

        {/* Thumb */}
        <div
          className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-4 h-4 bg-dark-accent rounded-full shadow-lg opacity-0 group-hover:opacity-100 transition-opacity"
          style={{ left: `${displayFraction * 100}%` }}
        />

        {/* Hover tooltip */}
        {tooltipTime && !dragging && (
          <div
            className="absolute -top-8 -translate-x-1/2 bg-dark-surface px-2 py-1 rounded text-xs text-dark-text pointer-events-none"
            style={{ left: tooltipLeft }}
          >
            {tooltipTime}
          </div>
        )}

        {/* Drag tooltip */}
        {dragging && (
          <div
            className="absolute -top-8 -translate-x-1/2 bg-dark-accent px-2 py-1 rounded text-xs text-dark-bg font-semibold pointer-events-none"
            style={{ left: `${dragFraction * 100}%` }}
          >
            {formatMs(dragFraction * durationMs)}
          </div>
        )}
      </div>

      {/* Time labels */}
      <div className="flex justify-between text-xs text-dark-text/60 mt-2">
        <span>{formatMs(dragging ? dragFraction * durationMs : positionMs)}</span>
        <span>{formatMs(durationMs)}</span>
      </div>
    </div>
  );
}

export default SeekBar;
