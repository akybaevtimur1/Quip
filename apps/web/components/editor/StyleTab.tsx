"use client";

import { useRef, useState } from "react";
import { Checkbox } from "@/components/ui/Checkbox";
import { Select } from "@/components/ui/Select";
import type { CaptionStyle, ClipEdit, HighlightStyle } from "@/lib/types";
import { PresetStrip } from "../PresetStrip";

// ── Таб «Стиль»: галерея пресетов + кастомизация ПОВЕРХ пресета ──
// Любая правка → PATCH captions.style/highlight → refetch ASS → libass
// перерисовывает мгновенно (WYSIWYG: превью = экспорт).

// Шрифты, доступные ОДНОВРЕМЕННО в libass-превью (public/libass/fonts) и в
// ffmpeg-экспорте (services/worker/fonts, subtitles=:fontsdir=). Добавляя
// шрифт — положи TTF в ОБА места, иначе превью разойдётся с экспортом.
export const CAPTION_FONTS = ["Montserrat", "Unbounded", "Rubik"];

const ANIMATIONS: { value: NonNullable<HighlightStyle["animation"]>; label: string }[] = [
  { value: "karaoke_fill", label: "Караоке (заливка)" },
  { value: "color_sweep", label: "Цвет-волна (по словам)" },
  { value: "blur_in", label: "Фокус (из размытия)" },
  { value: "spring", label: "Пружина (овершут)" },
  { value: "pop", label: "Pop (вспышка слова)" },
  { value: "punch", label: "Punch (сильный удар)" },
  { value: "bounce", label: "Bounce (подскок)" },
  { value: "fade", label: "Fade (проявление слов)" },
  { value: "none", label: "Без анимации" },
];

export function StyleTab({
  edit,
  activePresetId,
  busy,
  onPresetApply,
  onError,
  onStyleChange,
  onHighlightChange,
}: {
  edit: ClipEdit;
  activePresetId: string | null;
  busy: boolean;
  onPresetApply: (presetId: string) => Promise<void>;
  onError: (msg: string) => void;
  onStyleChange: (patch: Partial<CaptionStyle>) => void;
  onHighlightChange: (patch: Partial<HighlightStyle> | null) => void;
}) {
  const st = edit.captions.style;
  const hl = edit.captions.highlight ?? null;

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto pr-1">
      {/* ── пресеты ── */}
      <section className="space-y-2">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">
          Готовые стили
        </p>
        <PresetStrip activePresetId={activePresetId} onApply={onPresetApply} onError={onError} />
      </section>

      {/* ── кастомизация ── */}
      <section className="space-y-3">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">
          Настроить под себя
        </p>

        <div className="grid grid-cols-2 gap-3">
          <ColorField
            label="Цвет текста"
            value={st.color ?? "#FFFFFF"}
            disabled={busy}
            onChange={(v) => onStyleChange({ color: v })}
          />
          <ColorField
            label="Цвет подсветки"
            value={hl?.color ?? "#FF5A3D"}
            disabled={busy || hl === null}
            onChange={(v) => onHighlightChange({ color: v })}
          />
          <ColorField
            label="Контур"
            value={st.outline_color ?? "#000000"}
            disabled={busy}
            onChange={(v) => onStyleChange({ outline_color: v })}
          />
          <label className="flex flex-col gap-1 text-xs text-muted">
            Шрифт
            <Select
              value={st.font ?? "Montserrat"}
              disabled={busy}
              onChange={(e) => onStyleChange({ font: e.target.value })}
            >
              {CAPTION_FONTS.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </Select>
          </label>
        </div>

        <DebouncedSlider
          label="Размер"
          min={40}
          max={140}
          value={st.size ?? 90}
          disabled={busy}
          onCommit={(v) => onStyleChange({ size: v })}
        />

        <DebouncedSlider
          label="Позиция (от низа)"
          min={40}
          max={1200}
          value={st.margin_v ?? 260}
          disabled={busy}
          onCommit={(v) => onStyleChange({ margin_v: v })}
          hint="Или просто перетащи субтитры на видео"
        />

        <label className="flex flex-col gap-1 text-xs text-muted">
          Анимация активного слова
          <Select
            value={hl === null ? "off" : (hl.animation ?? "karaoke_fill")}
            disabled={busy}
            onChange={(e) => {
              const v = e.target.value;
              if (v === "off") onHighlightChange(null);
              else onHighlightChange({ animation: v as HighlightStyle["animation"] });
            }}
          >
            {ANIMATIONS.map((a) => (
              <option key={a.value} value={a.value}>
                {a.label}
              </option>
            ))}
            <option value="off">Подсветка выключена</option>
          </Select>
        </label>

        <Checkbox
          checked={st.uppercase ?? true}
          disabled={busy}
          onChange={(e) => onStyleChange({ uppercase: e.target.checked })}
          label="ЗАГЛАВНЫМИ БУКВАМИ"
          className="text-xs"
        />

        {/* T3: авто-подсветка ключевых слов (числа + длинные контентные) */}
        <div className="space-y-2 border-t border-line pt-3">
          <Checkbox
            checked={!!st.emphasis_color}
            disabled={busy}
            onChange={(e) => onStyleChange({ emphasis_color: e.target.checked ? "#FF5A3D" : null })}
            label="Подсвечивать ключевые слова"
            className="text-xs"
          />
          {st.emphasis_color && (
            <ColorField
              label="Цвет ключевых слов"
              value={st.emphasis_color}
              disabled={busy}
              onChange={(v) => onStyleChange({ emphasis_color: v })}
            />
          )}
        </div>
      </section>
    </div>
  );
}

function ColorField({
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
  // локальный стейт: color-input шлёт input-события на каждый пиксель пипетки —
  // PATCH только на change (отпускание). Синк с пропом — adjust-during-render.
  const [local, setLocal] = useState(value);
  const [prevValue, setPrevValue] = useState(value);
  if (prevValue !== value) {
    setPrevValue(value);
    setLocal(value);
  }
  return (
    <label className="flex flex-col gap-1 text-xs text-muted">
      {label}
      <span className="flex items-center gap-2 rounded-sm border border-line bg-surface-2 px-2 py-1 transition-colors hover:border-line-strong">
        <input
          type="color"
          value={local}
          disabled={disabled}
          onInput={(e) => setLocal((e.target as HTMLInputElement).value)}
          onChange={(e) => onChange(e.target.value.toUpperCase())}
          className="size-6 cursor-pointer rounded-sm border-0 bg-transparent p-0 disabled:cursor-not-allowed"
        />
        <span className="font-mono text-[11px] uppercase text-ink">{local}</span>
      </span>
    </label>
  );
}

function DebouncedSlider({
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
    <label className="flex flex-col gap-1 text-xs text-muted">
      <span className="flex items-center justify-between">
        {label}
        <span className="font-mono text-[11px] text-ink">{local}</span>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        value={local}
        disabled={disabled}
        onChange={(e) => handle(Number(e.target.value))}
        className="h-1.5 cursor-pointer appearance-none rounded-full bg-surface-2 accent-accent"
      />
      {hint && <span className="text-[10px] text-muted/70">{hint}</span>}
    </label>
  );
}
