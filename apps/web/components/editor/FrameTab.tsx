"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import type { Aspect } from "@/lib/api";
import type { ClipEdit } from "@/lib/types";

const ASPECTS: { value: Aspect; label: string; hint: string }[] = [
  { value: "9:16", label: "9:16", hint: "Reels / TikTok / Shorts" },
  { value: "1:1", label: "1:1", hint: "Feed (square)" },
  { value: "4:5", label: "4:5", hint: "Instagram post" },
  { value: "16:9", label: "16:9", hint: "YouTube / landscape" },
];

// ── Таб «Кадр»: режим кадрирования клипа вручную ──
// Auto = решает ИИ (per-shot: лицо→тайт, пейзаж→широко, 2 спикера→split).
// Вручную: широко (fit, блюр-рамки) / тайт (fill, кроп на центре) /
// split (два человека: верх/низ, как в OpusClip). Применяется на ВЕСЬ клип
// (override на интервал) → POST /edit/crop. Изменения применяются live с
// debounce 250ms — как остальные контролы редактора.

type FrameMode = "auto" | "fill" | "fit" | "split";

const MODES: { value: FrameMode; title: string; desc: string }[] = [
  { value: "auto", title: "Auto (AI)", desc: "Decides per shot: tight / wide / split" },
  { value: "fill", title: "Tight", desc: "Vertical crop on the person, full-bleed" },
  { value: "fit", title: "Wide", desc: "Full frame + blurred bars (landscape look)" },
  { value: "split", title: "Split (2 speakers)", desc: "Screen split: one on top, one below" },
];

const DEBOUNCE_MS = 250;

export function FrameTab({
  edit,
  outerStart,
  outerEnd,
  busy,
  onApply,
  onAspectChange,
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
  onAspectChange: (aspect: Aspect) => void;
}) {
  const aspect = (edit.aspect as Aspect) ?? "9:16";
  // текущий override на интервал (последний пересекающий) → стартовое состояние
  const current = (edit.reframe_overrides ?? [])
    .filter((ov) => ov.source_start < outerEnd && ov.source_end > outerStart)
    .at(-1);
  const [mode, setMode] = useState<FrameMode>((current?.mode as FrameMode) ?? "auto");
  const [center, setCenter] = useState(current?.center ?? 0.3);
  const [centerB, setCenterB] = useState(current?.center_b ?? 0.7);

  // touched guard — only apply on user-initiated changes, not initial mount
  const touchedRef = useRef(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Clear debounce on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current !== null) {
        clearTimeout(debounceRef.current);
      }
    };
  }, []);

  // Schedule a debounced apply with the given values (captured at call time from handlers)
  const scheduleApply = useCallback(
    (m: FrameMode, c: number, cb: number) => {
      if (debounceRef.current !== null) {
        clearTimeout(debounceRef.current);
      }
      debounceRef.current = setTimeout(() => {
        debounceRef.current = null;
        void onApply(
          m,
          m === "fill" || m === "split" ? c : null,
          m === "split" ? cb : null,
        );
      }, DEBOUNCE_MS);
    },
    [onApply],
  );

  const handleModeChange = (m: FrameMode) => {
    setMode(m);
    touchedRef.current = true;
    // Use current center/centerB state values alongside the new mode
    scheduleApply(m, center, centerB);
  };

  const handleCenterChange = (v: number) => {
    setCenter(v);
    touchedRef.current = true;
    scheduleApply(mode, v, centerB);
  };

  const handleCenterBChange = (v: number) => {
    setCenterB(v);
    touchedRef.current = true;
    scheduleApply(mode, center, v);
  };

  const handleResetToAuto = () => {
    setMode("auto");
    touchedRef.current = true;
    scheduleApply("auto", center, centerB);
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto pr-1">
      {/* T5: соотношение сторон выхода */}
      <section className="space-y-2">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">
          Aspect ratio
        </p>
        <div className="grid grid-cols-4 gap-1.5">
          {ASPECTS.map((a) => (
            <button
              key={a.value}
              type="button"
              disabled={busy}
              onClick={() => onAspectChange(a.value)}
              title={a.hint}
              className={`flex flex-col items-center gap-1 rounded-lg border py-2 transition ${
                aspect === a.value
                  ? "border-accent bg-surface-3 text-accent"
                  : "border-line bg-surface-2 text-muted hover:border-line-strong hover:text-ink"
              }`}
            >
              <AspectGlyph aspect={a.value} active={aspect === a.value} />
              <span className="text-[11px] font-semibold">{a.label}</span>
            </button>
          ))}
        </div>
      </section>

      <section className="space-y-2">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">
          Frame mode
        </p>
        <div className="space-y-1.5">
          {MODES.map((m) => (
            <label
              key={m.value}
              className={`flex cursor-pointer items-start gap-2.5 rounded-lg border p-3 transition ${
                mode === m.value
                  ? "border-accent bg-surface-3"
                  : "border-line bg-surface-2 hover:border-line-strong"
              }`}
            >
              <input
                type="radio"
                name="frame-mode"
                checked={mode === m.value}
                disabled={busy}
                onChange={() => handleModeChange(m.value)}
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
            label={mode === "split" ? "Top speaker (position in frame)" : "Crop center"}
            value={center}
            disabled={busy}
            onChange={handleCenterChange}
          />
          {mode === "split" && (
            <CenterSlider
              label="Bottom speaker (position in frame)"
              value={centerB}
              disabled={busy}
              onChange={handleCenterBChange}
            />
          )}
        </section>
      )}

      <div className="flex items-start justify-between gap-3">
        <p className="text-[11px] leading-snug text-muted">
          Framing updates live. Auto restores the AI&apos;s per-shot decision.
        </p>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={busy || mode === "auto"}
          onClick={handleResetToAuto}
          className="shrink-0 text-[11px]"
        >
          Reset to Auto
        </Button>
      </div>
    </div>
  );
}

const ASPECT_GLYPH: Record<Aspect, { w: number; h: number }> = {
  "9:16": { w: 9, h: 16 },
  "1:1": { w: 14, h: 14 },
  "4:5": { w: 12, h: 15 },
  "16:9": { w: 18, h: 10 },
};

function AspectGlyph({ aspect, active }: { aspect: Aspect; active: boolean }) {
  const g = ASPECT_GLYPH[aspect];
  return (
    <span
      aria-hidden
      className={`block rounded-[2px] border ${active ? "border-accent" : "border-muted"}`}
      style={{ width: g.w, height: g.h }}
    />
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
          {value <= 0.35 ? "left" : value >= 0.65 ? "right" : "center"} · {value.toFixed(2)}
        </span>
      </span>
      {/* h-9 row centers the 20px range-touch thumb so it can't overlap the label above. */}
      <span className="flex h-9 items-center">
        <input
          type="range"
          min={0}
          max={100}
          value={Math.round(value * 100)}
          disabled={disabled}
          onChange={(e) => onChange(Number(e.target.value) / 100)}
          className="range-touch h-1.5 w-full cursor-pointer appearance-none rounded-full bg-surface-2 accent-accent"
        />
      </span>
    </label>
  );
}
