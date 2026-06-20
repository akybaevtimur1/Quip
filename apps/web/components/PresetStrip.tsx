"use client";

import { useEffect, useState } from "react";
import { getPresets } from "@/lib/api";
import type { CaptionPreset } from "@/lib/types";

// ────────────────────────────────────────────────────────────────────────────
// PresetStrip — wrapping grid gallery of caption presets (A–L). Each preset is
// a mini-preview (how a word looks in that style). Click → onApply (parent
// executes via mutation queue: no 409s from concurrent edits). Default = preset_a.
//
// Changed from horizontal-scroll strip to a wrapping grid so all presets are
// visible without any horizontal-scroll fight in the ~360 px inspector.
// ────────────────────────────────────────────────────────────────────────────

const DEFAULT_PRESET_ID = "preset_a";

export interface PresetStripProps {
  /** id of the currently active preset (for highlight). */
  activePresetId?: string | null;
  /** Apply a preset; parent updates edit-state/ASS (via mutation queue). */
  onApply: (presetId: string) => Promise<void>;
  onError?: (message: string) => void;
}

export function PresetStrip({ activePresetId, onApply, onError }: PresetStripProps) {
  const [presets, setPresets] = useState<CaptionPreset[]>([]);
  const [loading, setLoading] = useState(true);
  const [applyingId, setApplyingId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getPresets()
      .then((p) => {
        if (!cancelled) setPresets(p);
      })
      .catch((e) => {
        if (!cancelled) onError?.(String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // getPresets/onError are stable for the component lifetime
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const active = activePresetId ?? DEFAULT_PRESET_ID;

  const handleApply = async (presetId: string) => {
    if (applyingId) return;
    setApplyingId(presetId);
    try {
      await onApply(presetId);
    } catch (e) {
      onError?.(String(e));
    } finally {
      setApplyingId(null);
    }
  };

  if (loading) {
    return (
      <div className="grid grid-cols-3 gap-2 py-1">
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <div
            key={i}
            className="h-16 animate-pulse rounded-xl border border-line bg-surface-2"
          />
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-3 gap-2 py-1">
      {presets.map((preset) => {
        const isActive = preset.id === active;
        const isApplying = applyingId === preset.id;
        return (
          <button
            key={preset.id}
            type="button"
            disabled={!!applyingId}
            onClick={() => handleApply(preset.id)}
            aria-pressed={isActive}
            className={`flex flex-col items-stretch gap-1 rounded-lg border p-1.5 transition focus:outline-none focus:ring-2 focus:ring-accent/50 ${
              isActive
                ? "border-accent bg-surface-3"
                : "border-line bg-surface-2 hover:border-line-strong"
            } ${applyingId && !isApplying ? "opacity-50" : ""}`}
          >
            <PresetThumb preset={preset} />
            <span
              className={`text-center text-[10px] font-semibold ${
                isActive ? "text-accent" : "text-muted"
              }`}
            >
              {isApplying ? "…" : preset.name}
            </span>
          </button>
        );
      })}
    </div>
  );
}

/** Mini-preview of a preset: word "АА" in the base color + active "ББ" with highlight. */
function PresetThumb({ preset }: { preset: CaptionPreset }) {
  const s = preset.style;
  const hl = preset.highlight;
  const color = s.color ?? "#FFFFFF";
  const outline = s.outline_color ?? "#000000";
  const ow = Math.max(1, Math.min(3, (s.outline_w ?? 6) / 3));
  const shadow = buildThumbShadow(outline, ow);

  // active word in the preview
  const hlColor = hl?.color ?? color;
  const box = hl?.box ?? false;

  return (
    <div className="flex h-12 w-full items-center justify-center gap-1 overflow-hidden rounded-lg bg-black px-1">
      <span
        style={{
          fontFamily: "var(--font-display), system-ui, sans-serif",
          fontWeight: 900,
          fontSize: "13px",
          color,
          textShadow: shadow,
        }}
      >
        Аа
      </span>
      {hl ? (
        box ? (
          <span
            style={{
              fontFamily: "var(--font-display), system-ui, sans-serif",
              fontWeight: 900,
              fontSize: "13px",
              color: "#000",
              background: hlColor,
              borderRadius: "3px",
              padding: "0 3px",
            }}
          >
            Бб
          </span>
        ) : (
          <span
            style={{
              fontFamily: "var(--font-display), system-ui, sans-serif",
              fontWeight: 900,
              fontSize: "13px",
              color: hlColor,
              textShadow: shadow,
            }}
          >
            Бб
          </span>
        )
      ) : (
        <span
          style={{
            fontFamily: "var(--font-display), system-ui, sans-serif",
            fontWeight: 900,
            fontSize: "13px",
            color,
            textShadow: shadow,
          }}
        >
          Бб
        </span>
      )}
    </div>
  );
}

function buildThumbShadow(outlineColor: string, r: number): string {
  const layers: string[] = [];
  for (let k = 0; k < 8; k++) {
    const ang = (k / 8) * Math.PI * 2;
    layers.push(
      `${(Math.cos(ang) * r).toFixed(1)}px ${(Math.sin(ang) * r).toFixed(1)}px 0 ${outlineColor}`,
    );
  }
  return layers.join(", ");
}
