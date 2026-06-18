"use client";

import { useRef, useState } from "react";
import { cn } from "@/lib/cn";

// ── Переиспользуемые контролы стиля (общие для таба «Стиль» субтитров и «Хук») ──
// Оба — оптимистично-локальные: высокочастотные input-события (пипетка цвета,
// тяга слайдера) НЕ шлют PATCH на каждый тик; коммит — на change/blur (debounce).
// Синк с пропом — паттерн adjust-during-render (без эффекта).
//
// ВЫРАВНИВАНИЕ: ColorField и DebouncedSlider встают рядом в одной grid-строке
// (например «Цвет плашки | Прозрачность»). Чтобы строки не «кривились», оба
// используют ОДИН wrapper <Field>: одинаковый gap метки и общую высоту контрола
// (h-10) — слайдер вертикально центрируется в той же высоте, что и цветовой
// свотч / Select. Раньше ColorField был flex-col gap-1.5 + h-10, а слайдер —
// flex-col gap-1 + тонкий h-1.5 без своей высоты → колонки разъезжались.

/** Общая обёртка метка+контрол: единый отступ метки и высота строки контрола.
 *  meta — необязательное значение справа в метке (моноширинное число слайдера). */
function Field({
  label,
  meta,
  children,
}: {
  label: string;
  meta?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.5 text-xs text-muted">
      <span className="flex min-h-[16px] items-center justify-between gap-2">
        {label}
        {meta != null && <span className="font-mono text-[11px] text-ink">{meta}</span>}
      </span>
      {children}
    </label>
  );
}

export function ColorField({
  label,
  value,
  disabled,
  onChange,
}: {
  label: string;
  value: string;
  disabled: boolean;
  onChange: (v: string) => void;
}) {
  const [local, setLocal] = useState(value);
  const [prevValue, setPrevValue] = useState(value);
  if (prevValue !== value) {
    setPrevValue(value);
    setLocal(value);
  }
  return (
    <Field label={label}>
      {/* h-10 matches Select/Input/slider-row so grid rows line up. */}
      <span
        className={cn(
          "flex h-10 items-center gap-2.5 rounded-sm border border-line bg-surface-2 px-2.5",
          "transition-colors focus-within:border-accent/60",
          disabled ? "opacity-50" : "hover:border-line-strong",
        )}
      >
        {/* ring keeps a dark swatch (e.g. #000000) visible against the dark field */}
        <input
          type="color"
          value={local}
          disabled={disabled}
          onInput={(e) => setLocal((e.target as HTMLInputElement).value)}
          onChange={(e) => onChange(e.target.value.toUpperCase())}
          aria-label={label}
          className="size-9 shrink-0 cursor-pointer rounded bg-transparent p-0 outline outline-1 -outline-offset-1 outline-line-strong disabled:cursor-not-allowed sm:size-6 [&::-webkit-color-swatch-wrapper]:p-0.5 [&::-webkit-color-swatch]:rounded-[3px] [&::-webkit-color-swatch]:border-0"
        />
        <span className="font-mono text-xs uppercase tracking-wide text-ink">{local}</span>
      </span>
    </Field>
  );
}

export function DebouncedSlider({
  label,
  min,
  max,
  value,
  disabled,
  hint,
  onCommit,
}: {
  label: string;
  min: number;
  max: number;
  value: number;
  disabled: boolean;
  hint?: string;
  onCommit: (v: number) => void;
}) {
  const [local, setLocal] = useState(value);
  const [prevValue, setPrevValue] = useState(value);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  if (prevValue !== value) {
    setPrevValue(value);
    setLocal(value);
  }

  const handle = (v: number) => {
    setLocal(v);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => onCommit(v), 300);
  };

  return (
    <Field label={label} meta={local}>
      {/* h-10 wrapper centers the thin track at the same row height as ColorField/Select,
          so a slider next to a color/select in a 2-col grid lines up cleanly. */}
      <span className="flex h-10 items-center">
        <input
          type="range"
          min={min}
          max={max}
          value={local}
          disabled={disabled}
          onChange={(e) => handle(Number(e.target.value))}
          className="range-touch h-1.5 w-full cursor-pointer appearance-none rounded-full bg-surface-2 accent-accent disabled:opacity-50"
        />
      </span>
      {hint && <span className="text-[10px] text-muted/70">{hint}</span>}
    </Field>
  );
}
