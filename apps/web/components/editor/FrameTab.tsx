"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { Numeral } from "@/components/ui/Numeral";
import type { Aspect } from "@/lib/api";
import type { ClipEdit, CropOverride, SourceInterval } from "@/lib/types";
import { FitTimeline, type FitRegion, type ForceMode } from "./FitTimeline";

const ASPECTS: { value: Aspect; label: string; hint: string }[] = [
  { value: "9:16", label: "9:16", hint: "Reels / TikTok / Shorts" },
  { value: "1:1", label: "1:1", hint: "Feed (square)" },
  { value: "4:5", label: "4:5", hint: "Instagram post" },
  { value: "16:9", label: "16:9", hint: "YouTube / landscape" },
];

// ── Таб «Кадр»: режим кадрирования клипа вручную ──
// Auto = решает ИИ (per-shot: одно лицо→тайт, иначе→широко). Вручную: широко (fit, блюр-рамки) /
// тайт (fill, кроп на центре). Применяется на ВЕСЬ клип (override на интервал) → POST /edit/crop.
// Изменения live с debounce 250ms. (Split удалён из MVP 2026-06-24.)

type FrameMode = "auto" | "fill" | "fit";

const MODES: { value: FrameMode; title: string; desc: string }[] = [
  { value: "auto", title: "Auto (AI)", desc: "Decides per shot: tight or wide" },
  { value: "fill", title: "Tight", desc: "Vertical crop on the person, full-bleed" },
  { value: "fit", title: "Wide", desc: "Full frame + blurred bars (landscape look)" },
];

const DEBOUNCE_MS = 250;

export function FrameTab({
  edit,
  outerStart,
  outerEnd,
  busy,
  onApply,
  onAspectChange,
  shotRegions,
  shotIntervals,
  shotOverrides,
  nowSec,
  shotVariant,
  shotLoading,
  onApplyShotRange,
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
  // ── per-shot framing (was the separate "Shots" tab; both write reframe_overrides) ──
  shotRegions: FitRegion[] | null;
  shotIntervals: SourceInterval[];
  shotOverrides?: CropOverride[];
  nowSec?: number;
  shotVariant?: "ai" | "manual";
  shotLoading?: boolean;
  onApplyShotRange: (sourceStart: number, sourceEnd: number, mode: ForceMode) => void;
}) {
  const aspect = (edit.aspect as Aspect) ?? "9:16";
  // текущий override на интервал (последний пересекающий) → стартовое состояние
  const current = (edit.reframe_overrides ?? [])
    .filter((ov) => ov.source_start < outerEnd && ov.source_end > outerStart)
    .at(-1);
  // legacy split override → показываем Auto (split удалён из MVP)
  const cm = current?.mode;
  const [mode, setMode] = useState<FrameMode>(cm === "fill" || cm === "fit" ? cm : "auto");
  const [center, setCenter] = useState(current?.center ?? 0.5);

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
    (m: FrameMode, c: number) => {
      if (debounceRef.current !== null) {
        clearTimeout(debounceRef.current);
      }
      debounceRef.current = setTimeout(() => {
        debounceRef.current = null;
        void onApply(m, m === "fill" ? c : null, null);
      }, DEBOUNCE_MS);
    },
    [onApply],
  );

  const handleModeChange = (m: FrameMode) => {
    setMode(m);
    touchedRef.current = true;
    scheduleApply(m, center);
  };

  const handleCenterChange = (v: number) => {
    setCenter(v);
    touchedRef.current = true;
    scheduleApply(mode, v);
  };

  const handleResetToAuto = () => {
    setMode("auto");
    touchedRef.current = true;
    scheduleApply("auto", center);
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto pr-1">
      {/* T5: соотношение сторон выхода */}
      <section className="space-y-2">
        <Eyebrow tone="muted">Aspect ratio</Eyebrow>
        <div className="grid grid-cols-4 gap-1.5">
          {ASPECTS.map((a) => (
            <button
              key={a.value}
              type="button"
              disabled={busy}
              onClick={() => onAspectChange(a.value)}
              title={a.hint}
              className={`flex flex-col items-center gap-1 rounded-lg border py-2 transition duration-150 ease-snappy ${
                aspect === a.value
                  ? "border-accent-line bg-surface-3 text-accent"
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
        <Eyebrow tone="muted">Frame mode</Eyebrow>
        {/* Compact labeled tiles (segmented) — replaces 4 stacked full-width radio cards.
            Selected tile uses the shared pattern (border-accent-line + bg-surface-3); the
            description is shown ONCE for the selected mode below, not on every card. */}
        <div className="grid grid-cols-2 gap-1.5" role="radiogroup" aria-label="Frame mode">
          {MODES.map((m) => {
            const selected = mode === m.value;
            return (
              <button
                key={m.value}
                type="button"
                role="radio"
                aria-checked={selected}
                disabled={busy}
                onClick={() => handleModeChange(m.value)}
                title={m.desc}
                className={`rounded-lg border px-3 py-2.5 text-left text-sm font-semibold transition duration-150 ease-snappy disabled:opacity-50 ${
                  selected
                    ? "border-accent-line bg-surface-3 text-accent"
                    : "border-line bg-surface-2 text-muted hover:border-line-strong hover:text-ink"
                }`}
              >
                {m.title}
              </button>
            );
          })}
        </div>
        <p className="text-xs leading-snug text-muted">
          {MODES.find((m) => m.value === mode)?.desc}
        </p>
      </section>

      {mode === "fill" && (
        <section className="space-y-3">
          <CenterSlider
            label="Crop center"
            value={center}
            disabled={busy}
            onChange={handleCenterChange}
          />
        </section>
      )}

      <div className="flex items-start justify-between gap-3">
        <p className="text-xs leading-snug text-muted">
          Framing updates live. Auto restores the AI&apos;s per-shot decision.
        </p>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={busy || mode === "auto"}
          onClick={handleResetToAuto}
          className="shrink-0 text-xs"
        >
          Reset to Auto
        </Button>
      </div>

      {/* ── per-shot framing (was its own "Shots" tab) ── */}
      <section className="space-y-1 border-t border-line pt-4">
        <h3 className="text-sm font-semibold text-ink">Per-shot framing</h3>
        <p className="text-xs leading-snug text-muted">
          The mode above applies to the whole clip. Below, override individual{" "}
          <span className="text-ink">shots</span> — the cuts between camera angles. Pick shots on
          the bar (the white line shows where you are) and force{" "}
          <span className="text-ink">Wide</span>, <span className="text-ink">Tight</span> or{" "}
          <span className="text-ink">Auto</span>. Need a boundary the detector merged away? Use{" "}
          <span className="text-ink">Split here</span> to cut a shot at the playhead, then force
          either half.
        </p>
        <FitTimeline
          regions={shotRegions}
          intervals={shotIntervals}
          overrides={shotOverrides}
          nowSec={nowSec}
          busy={busy}
          variant={shotVariant}
          loading={shotLoading}
          onApplyRange={onApplyShotRange}
        />
      </section>
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
        <span className="text-ink">
          {value <= 0.35 ? "left" : value >= 0.65 ? "right" : "center"} ·{" "}
          <Numeral className="text-xs">{value.toFixed(2)}</Numeral>
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
