"use client";

import { Loader2, RefreshCw, Sparkles, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Checkbox } from "@/components/ui/Checkbox";
import { Select } from "@/components/ui/Select";
import { HOOK_PRESETS } from "@/lib/hookPresets";
import type { ClipEdit, HookOverlay } from "@/lib/types";
import { useWheelHscroll } from "@/lib/useWheelHscroll";
import { CAPTION_FONTS } from "./StyleTab";
import { ColorField, DebouncedSlider } from "./StyleControls";

// ── Таб «Хук»: топ-текст клипа (T1, наш отличитель — объяснимый цепляющий заголовок) ──
// Хук = ASS-событие с верхним якорем В ТОМ ЖЕ файле, что субтитры → libass-превью
// показывает его пиксель-в-пиксель как экспорт. Правки идут через onHookChange
// (PATCH captions.hook через очередь мутаций + instant-превью). Паритет со стилем
// субтитров: галерея пресетов + цвет/плашка/контур/шрифт/размер/позиция/анимация.
// Поля HookOverlay все опциональны → создавая хук с нуля, шлём только нужное,
// pydantic дольёт дефолты.

const HOOK_ANIMATIONS: { value: NonNullable<HookOverlay["animation"]>; label: string }[] = [
  { value: "none", label: "None" },
  { value: "pop", label: "Pop (scale-in)" },
  { value: "fade", label: "Fade in" },
  { value: "bounce", label: "Bounce" },
];

const HOOK_DEFAULTS = {
  color: "#FFFFFF",
  box_color: "#FF5A3D" as string | null,
  box_opacity: 1,
  outline_color: "#000000",
  outline_w: 4,
  font: "Unbounded",
  size: 66,
  margin_v: 150,
  uppercase: true,
  animation: "none" as NonNullable<HookOverlay["animation"]>,
};

export function HookTab({
  edit,
  busy,
  onHookChange,
  onRegenerate,
  regenerating = false,
}: {
  edit: ClipEdit;
  busy: boolean;
  onHookChange: (patch: Partial<HookOverlay> | null) => void;
  // W4: перегенерировать текст хука под текущий интервал клипа (узкий Gemini-вызов).
  onRegenerate?: () => void;
  regenerating?: boolean;
}) {
  const hook = edit.captions.hook ?? null;
  const enabled = hook?.enabled ?? false;
  const fullClip = hook?.full_clip ?? true;
  // box_color: undefined в патче ≠ null. Модельный дефолт = коралл-плашка.
  const boxColor = hook?.box_color === undefined ? HOOK_DEFAULTS.box_color : hook.box_color;
  const hasPlaque = boxColor !== null;
  const presetScrollRef = useWheelHscroll<HTMLDivElement>(); // #6: колесо мыши → горизонталь

  // локальный текст: печать не должна слать PATCH на каждый символ (как ColorField).
  // Коммит — на blur / Enter-pause (debounce). Синк с пропом — adjust-during-render.
  const [text, setText] = useState(hook?.text ?? "");
  const [prevText, setPrevText] = useState(hook?.text ?? "");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  if ((hook?.text ?? "") !== prevText) {
    setPrevText(hook?.text ?? "");
    setText(hook?.text ?? "");
  }
  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  const commitText = (value: string) => {
    setText(value);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => onHookChange({ text: value, enabled: true }), 350);
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto pr-1">
      {/* ── текст + показ ── */}
      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">
            Top text (hook)
          </p>
          <Checkbox
            label="Show"
            className="text-xs"
            checked={enabled}
            disabled={busy}
            onChange={(e) =>
              onHookChange(e.target.checked ? { enabled: true } : { enabled: false })
            }
          />
        </div>

        <textarea
          value={text}
          disabled={busy}
          rows={2}
          maxLength={80}
          placeholder="Catchy headline at the top of the clip…"
          onChange={(e) => commitText(e.target.value)}
          onBlur={() => {
            if (timer.current) clearTimeout(timer.current);
            onHookChange({ text, enabled: text.trim() ? true : enabled });
          }}
          className="w-full resize-none rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm font-semibold text-ink outline-none transition-colors focus:border-accent/60"
        />
        <p className="flex items-center gap-1.5 text-[11px] leading-snug text-muted">
          <Sparkles className="size-3 shrink-0 text-accent" />
          A short headline (≤6 words) tied to the moment. Stops the scroll.
        </p>

        {/* W4: хук НЕ обновляется сам при сдвиге клипа — явная регенерация под новый интервал */}
        {onRegenerate && (
          <div className="space-y-1.5 pt-1">
            <Button
              type="button"
              variant="secondary"
              size="sm"
              disabled={busy || regenerating}
              onClick={onRegenerate}
              className="w-full"
            >
              {regenerating ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <RefreshCw className="size-3.5" />
              )}
              {regenerating ? "Writing a new hook…" : "Regenerate for current clip"}
            </Button>
            <p className="text-[11px] leading-snug text-muted">
              The hook doesn’t auto-update when you move or trim the clip. Regenerate it for the
              new moment, or just edit the text above.
            </p>
          </div>
        )}
      </section>

      {/* ── пресеты хука (галерея look'ов) ── */}
      <section className="space-y-2">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">Presets</p>
        <div
          ref={presetScrollRef}
          className="no-scrollbar flex snap-x snap-mandatory gap-2 overflow-x-auto py-1"
        >
          {HOOK_PRESETS.map((preset) => (
            <button
              key={preset.id}
              type="button"
              disabled={busy}
              onClick={() => onHookChange({ ...preset.values, enabled: true })}
              className="flex shrink-0 snap-start flex-col items-stretch gap-1 rounded-lg border border-line bg-surface-2 p-1.5 transition hover:border-line-strong focus:outline-none focus:ring-2 focus:ring-accent/50 disabled:opacity-50"
            >
              <HookPresetThumb preset={preset.values} />
              <span className="text-center text-[10px] font-semibold text-muted">{preset.name}</span>
            </button>
          ))}
        </div>
      </section>

      {/* ── когда показывать ── */}
      <section className="space-y-2">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">
          When to show
        </p>
        <div className="grid grid-cols-2 gap-1.5">
          <button
            type="button"
            disabled={busy}
            onClick={() => onHookChange({ full_clip: true })}
            className={`rounded-lg border px-3 py-2.5 text-sm font-semibold transition ${
              fullClip
                ? "border-accent bg-surface-3 text-accent"
                : "border-line bg-surface-2 text-muted hover:border-line-strong hover:text-ink"
            }`}
          >
            Whole clip
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => onHookChange({ full_clip: false })}
            className={`rounded-lg border px-3 py-2.5 text-sm font-semibold transition ${
              !fullClip
                ? "border-accent bg-surface-3 text-accent"
                : "border-line bg-surface-2 text-muted hover:border-line-strong hover:text-ink"
            }`}
          >
            First seconds
          </button>
        </div>
        {!fullClip && (
          <label className="flex flex-col gap-1 pt-1 text-xs text-muted">
            <span className="flex items-center justify-between">
              Show duration
              <span className="font-mono text-[11px] text-ink">
                {(hook?.duration_sec ?? 4).toFixed(0)} s
              </span>
            </span>
            <input
              type="range"
              min={1}
              max={15}
              value={Math.round(hook?.duration_sec ?? 4)}
              disabled={busy}
              onChange={(e) => onHookChange({ duration_sec: Number(e.target.value) })}
              className="range-touch h-1.5 cursor-pointer appearance-none rounded-full bg-surface-2 accent-accent"
            />
          </label>
        )}
      </section>

      {/* ── стиль (паритет с субтитрами) ── */}
      <section className="space-y-3">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">Style</p>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <ColorField
            label="Text color"
            value={hook?.color ?? HOOK_DEFAULTS.color}
            disabled={busy}
            onChange={(v) => onHookChange({ color: v })}
          />
          <label className="flex flex-col gap-1.5 text-xs text-muted">
            Font
            <Select
              value={hook?.font ?? HOOK_DEFAULTS.font}
              disabled={busy}
              onChange={(e) => onHookChange({ font: e.target.value })}
            >
              {CAPTION_FONTS.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </Select>
          </label>
        </div>

        {/* плашка vs контур */}
        <Checkbox
          checked={hasPlaque}
          disabled={busy}
          onChange={(e) =>
            onHookChange({ box_color: e.target.checked ? (boxColor ?? "#FF5A3D") : null })
          }
          label="Background plaque"
          className="text-xs"
        />
        {hasPlaque ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <ColorField
              label="Plaque color"
              value={boxColor ?? "#FF5A3D"}
              disabled={busy}
              onChange={(v) => onHookChange({ box_color: v })}
            />
            <DebouncedSlider
              label="Plaque opacity"
              min={0}
              max={100}
              value={Math.round((hook?.box_opacity ?? HOOK_DEFAULTS.box_opacity) * 100)}
              disabled={busy}
              onCommit={(v) => onHookChange({ box_opacity: v / 100 })}
            />
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <ColorField
              label="Outline"
              value={hook?.outline_color ?? HOOK_DEFAULTS.outline_color}
              disabled={busy}
              onChange={(v) => onHookChange({ outline_color: v })}
            />
            <DebouncedSlider
              label="Outline width"
              min={0}
              max={16}
              value={hook?.outline_w ?? HOOK_DEFAULTS.outline_w}
              disabled={busy}
              onCommit={(v) => onHookChange({ outline_w: v })}
            />
          </div>
        )}

        <DebouncedSlider
          label="Size"
          min={36}
          max={120}
          value={hook?.size ?? HOOK_DEFAULTS.size}
          disabled={busy}
          onCommit={(v) => onHookChange({ size: v })}
        />

        <DebouncedSlider
          label="Position (from top)"
          min={40}
          max={900}
          value={hook?.margin_v ?? HOOK_DEFAULTS.margin_v}
          disabled={busy}
          // clear pos_y so the slider regains vertical control after a free drag; keep pos_x.
          onCommit={(v) => onHookChange({ margin_v: v, pos_y: null })}
          hint="Or just drag the hook on the video"
        />

        <label className="flex flex-col gap-1.5 text-xs text-muted">
          Entrance animation
          <Select
            value={hook?.animation ?? HOOK_DEFAULTS.animation}
            disabled={busy}
            onChange={(e) =>
              onHookChange({ animation: e.target.value as HookOverlay["animation"] })
            }
          >
            {HOOK_ANIMATIONS.map((a) => (
              <option key={a.value} value={a.value}>
                {a.label}
              </option>
            ))}
          </Select>
        </label>

        <Checkbox
          checked={hook?.uppercase ?? HOOK_DEFAULTS.uppercase}
          disabled={busy}
          onChange={(e) => onHookChange({ uppercase: e.target.checked })}
          label="UPPERCASE"
          className="text-xs"
        />
      </section>

      {hook && (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={busy}
          onClick={() => onHookChange(null)}
          className="self-start text-bad hover:bg-bad/10 hover:text-bad"
        >
          <Trash2 className="size-3.5" />
          Remove hook
        </Button>
      )}
    </div>
  );
}

/** Мини-превью хук-пресета: слово в основном цвете на плашке/с контуром. */
function HookPresetThumb({ preset }: { preset: Partial<HookOverlay> }) {
  const color = preset.color ?? "#FFFFFF";
  const box = preset.box_color ?? null;
  const outline = preset.outline_color ?? "#000000";
  return (
    <div className="flex h-12 w-24 items-center justify-center rounded-lg bg-black px-1">
      <span
        style={{
          fontFamily: "var(--font-display), system-ui, sans-serif",
          fontWeight: 900,
          fontSize: "12px",
          color: box ? "#FFFFFF" : color,
          background: box ?? undefined,
          borderRadius: box ? "3px" : undefined,
          padding: box ? "1px 4px" : undefined,
          textShadow: box ? undefined : `0 0 2px ${outline}, 0 0 2px ${outline}`,
        }}
      >
        HOOK
      </span>
    </div>
  );
}
