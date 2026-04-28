import { useCallback } from 'react';

import { cn } from '../lib/utils';

export interface RangeSliderProps {
  min?: number;
  max?: number;
  step?: number;
  values: [number, number];
  onChange: (values: [number, number]) => void;
  className?: string;
  ariaLabelMin?: string;
  ariaLabelMax?: string;
}

export function RangeSlider({
  min = 0,
  max = 100,
  step = 1,
  values,
  onChange,
  className,
  ariaLabelMin,
  ariaLabelMax,
}: RangeSliderProps) {
  const [low, high] = values;
  const span = max - min;
  const lowPct = span > 0 ? ((low - min) / span) * 100 : 0;
  const highPct = span > 0 ? ((high - min) / span) * 100 : 100;

  const handleLow = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const v = Math.min(Number(e.target.value), high);
      onChange([v, high]);
    },
    [high, onChange],
  );

  const handleHigh = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const v = Math.max(Number(e.target.value), low);
      onChange([low, v]);
    },
    [low, onChange],
  );

  return (
    <div className={cn('relative h-6 w-full select-none', className)}>
      <div className="absolute left-0 right-0 top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-muted" />
      <div
        className="absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-primary"
        style={{ left: `${lowPct}%`, right: `${100 - highPct}%` }}
      />
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={low}
        onChange={handleLow}
        aria-label={ariaLabelMin ?? '최소'}
        className="range-thumb absolute inset-0 h-full w-full appearance-none bg-transparent"
        style={{ zIndex: low > max - step ? 5 : 4 }}
      />
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={high}
        onChange={handleHigh}
        aria-label={ariaLabelMax ?? '최대'}
        className="range-thumb absolute inset-0 h-full w-full appearance-none bg-transparent"
        style={{ zIndex: 5 }}
      />
    </div>
  );
}
