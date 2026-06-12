"use client";

import { useEffect, useState } from "react";
import { getPresets } from "@/lib/api";
import type { CaptionPreset } from "@/lib/types";

// ────────────────────────────────────────────────────────────────────────────
// PresetStrip — горизонтальная галерея пресетов субтитров (A–L). Каждый пресет —
// мини-превью (как слово выглядит в этом стиле). Клик → onApply (родитель
// исполняет в ОЧЕРЕДИ мутаций: правки на ходу не плодят 409). Дефолт = preset_a.
// ────────────────────────────────────────────────────────────────────────────

const DEFAULT_PRESET_ID = "preset_a";

export interface PresetStripProps {
  /** id текущего активного пресета (для подсветки). */
  activePresetId?: string | null;
  /** Применить пресет; родитель сам обновляет edit-state/ASS (через очередь мутаций). */
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
    // getPresets/onError стабильны на время жизни компонента
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
      <div className="flex gap-2 overflow-x-auto py-2">
        {[0, 1, 2, 3].map((i) => (
          <div
            key={i}
            className="h-16 w-28 shrink-0 animate-pulse rounded-xl border border-line bg-surface-2"
          />
        ))}
      </div>
    );
  }

  return (
    <div className="flex gap-2 overflow-x-auto py-2">
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
            className={`flex shrink-0 flex-col items-stretch gap-1 rounded-xl border p-1.5 transition focus:outline-none focus:ring-2 focus:ring-accent/50 ${
              isActive
                ? "border-accent bg-accent/10"
                : "border-line bg-surface-2 hover:border-accent/50"
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

/** Мини-превью пресета: слово «АА» в основном цвете + активное «БB» по highlight. */
function PresetThumb({ preset }: { preset: CaptionPreset }) {
  const s = preset.style;
  const hl = preset.highlight;
  const color = s.color ?? "#FFFFFF";
  const outline = s.outline_color ?? "#000000";
  const ow = Math.max(1, Math.min(3, (s.outline_w ?? 6) / 3));
  const shadow = buildThumbShadow(outline, ow);

  // активное слово в превью
  const hlColor = hl?.color ?? color;
  const box = hl?.box ?? false;

  return (
    <div className="flex h-12 w-28 items-center justify-center gap-1 overflow-hidden rounded-lg bg-black px-1">
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
