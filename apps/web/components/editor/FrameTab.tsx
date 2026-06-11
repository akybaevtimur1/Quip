"use client";

import { Loader2 } from "lucide-react";
import { useState } from "react";
import type { ClipEdit } from "@/lib/types";

// ── Таб «Кадр»: режим кадрирования клипа вручную ──
// Auto = решает ИИ (per-shot: лицо→тайт, пейзаж→широко, 2 спикера→split).
// Вручную: широко (fit, блюр-рамки) / тайт (fill, кроп на центре) /
// split (два человека: верх/низ, как в OpusClip). Применяется на ВЕСЬ клип
// (override на интервал) → POST /edit/crop. Превью-кроп приблизительный
// (Approach A) — точный кадр виден после рендера.

type FrameMode = "auto" | "fill" | "fit" | "split";

const MODES: { value: FrameMode; title: string; desc: string }[] = [
  { value: "auto", title: "Авто (ИИ)", desc: "Сам решает по шотам: тайт / широко / split" },
  { value: "fill", title: "Тайт", desc: "Вертикальный кроп на человеке, full-bleed" },
  { value: "fit", title: "Широко", desc: "Весь кадр + блюр-рамки (горизонтальный вид)" },
  { value: "split", title: "Split 2 спикера", desc: "Экран пополам: один сверху, другой снизу" },
];

export function FrameTab({
  edit,
  outerStart,
  outerEnd,
  busy,
  onApply,
}: {
  edit: ClipEdit;
  outerStart: number;
  outerEnd: number;
  busy: boolean;
  onApply: (
    mode: FrameMode,
    center: number | null,
    centerB: number | null,
  ) => Promise<void>;
}) {
  // текущий override на интервал (последний пересекающий) → стартовое состояние
  const current = (edit.reframe_overrides ?? [])
    .filter((ov) => ov.source_start < outerEnd && ov.source_end > outerStart)
    .at(-1);
  const [mode, setMode] = useState<FrameMode>((current?.mode as FrameMode) ?? "auto");
  const [center, setCenter] = useState(current?.center ?? 0.3);
  const [centerB, setCenterB] = useState(current?.center_b ?? 0.7);
  const [applying, setApplying] = useState(false);
  const [applied, setApplied] = useState(false);

  const apply = async () => {
    setApplying(true);
    setApplied(false);
    try {
      await onApply(
        mode,
        mode === "fill" || mode === "split" ? center : null,
        mode === "split" ? centerB : null,
      );
      setApplied(true);
      setTimeout(() => setApplied(false), 3000);
    } finally {
      setApplying(false);
    }
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto pr-1">
      <section className="space-y-2">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">
          Режим кадра
        </p>
        <div className="space-y-1.5">
          {MODES.map((m) => (
            <label
              key={m.value}
              className={`flex cursor-pointer items-start gap-2.5 rounded-xl border p-3 transition ${
                mode === m.value
                  ? "border-accent/60 bg-accent/10"
                  : "border-line bg-surface-2 hover:border-accent/30"
              }`}
            >
              <input
                type="radio"
                name="frame-mode"
                checked={mode === m.value}
                disabled={busy || applying}
                onChange={() => setMode(m.value)}
                className="mt-0.5 size-3.5 accent-accent"
              />
              <span>
                <span className="block text-sm font-semibold text-ink">{m.title}</span>
                <span className="block text-xs leading-snug text-muted">{m.desc}</span>
              </span>
            </label>
          ))}
        </div>
      </section>

      {(mode === "fill" || mode === "split") && (
        <section className="space-y-3">
          <CenterSlider
            label={mode === "split" ? "Спикер сверху (позиция в кадре)" : "Центр кропа"}
            value={center}
            disabled={busy || applying}
            onChange={setCenter}
          />
          {mode === "split" && (
            <CenterSlider
              label="Спикер снизу (позиция в кадре)"
              value={centerB}
              disabled={busy || applying}
              onChange={setCenterB}
            />
          )}
        </section>
      )}

      <button
        type="button"
        disabled={busy || applying}
        onClick={apply}
        className="flex w-full items-center justify-center gap-2 rounded-xl bg-accent py-2.5 text-sm font-semibold text-white transition hover:bg-accent-2 disabled:opacity-40"
      >
        {applying ? (
          <>
            <Loader2 className="size-4 animate-spin" /> Применяю…
          </>
        ) : (
          "Применить к клипу"
        )}
      </button>

      {applied && (
        <p className="rounded-lg border border-amber-700/40 bg-amber-900/20 px-3 py-2 text-xs text-amber-300">
          Режим сохранён. Точный кадр — после рендера (превью показывает приблизительный кроп).
        </p>
      )}
      <p className="text-[11px] leading-snug text-muted">
        Кадрирование применяется на весь клип. «Авто» возвращает решение ИИ по шотам.
      </p>
    </div>
  );
}

function CenterSlider({
  label,
  value,
  disabled,
  onChange,
}: {
  label: string;
  value: number;
  disabled: boolean;
  onChange: (v: number) => void;
}) {
  return (
    <label className="flex flex-col gap-1 text-xs text-muted">
      <span className="flex items-center justify-between">
        {label}
        <span className="font-mono text-[11px] text-ink">
          {value <= 0.35 ? "лево" : value >= 0.65 ? "право" : "центр"} · {value.toFixed(2)}
        </span>
      </span>
      <input
        type="range"
        min={0}
        max={100}
        value={Math.round(value * 100)}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value) / 100)}
        className="h-1.5 cursor-pointer appearance-none rounded-full bg-surface-2 accent-accent"
      />
    </label>
  );
}
