"use client";

import { Checkbox } from "@/components/ui/Checkbox";
import { Select } from "@/components/ui/Select";
import type { CaptionStyle, ClipEdit, HighlightStyle } from "@/lib/types";
import { PresetStrip } from "../PresetStrip";
import { ColorField, DebouncedSlider } from "./StyleControls";

// ── Таб «Стиль»: галерея пресетов + кастомизация ПОВЕРХ пресета ──
// Любая правка → PATCH captions.style/highlight → refetch ASS → libass
// перерисовывает мгновенно (WYSIWYG: превью = экспорт).

// Шрифты, доступные ОДНОВРЕМЕННО в libass-превью (public/libass/fonts) и в
// ffmpeg-экспорте (services/worker/fonts, subtitles=:fontsdir=). Добавляя
// шрифт — положи TTF в ОБА места, иначе превью разойдётся с экспортом.
export const CAPTION_FONTS = [
  "Montserrat",
  "Unbounded",
  "Rubik",
  "Anton",
  "Poppins",
  "Bebas Neue",
  "Archivo Black",
  "Russo One",
  "Luckiest Guy",
];

const ANIMATIONS: { value: NonNullable<HighlightStyle["animation"]>; label: string }[] = [
  { value: "karaoke_fill", label: "Karaoke (fill)" },
  { value: "color_sweep", label: "Color sweep (word by word)" },
  { value: "blur_in", label: "Focus (from blur)" },
  { value: "spring", label: "Spring (overshoot)" },
  { value: "pop", label: "Pop (word flash)" },
  { value: "punch", label: "Punch (hard hit)" },
  { value: "bounce", label: "Bounce" },
  { value: "fade", label: "Fade (words appear)" },
  { value: "drop_in", label: "Drop in (from above)" },
  { value: "glow_pulse", label: "Glow pulse" },
  { value: "shake", label: "Shake" },
  { value: "slide_up", label: "Slide up" },
  { value: "flash", label: "Flash (white to accent)" },
  { value: "none", label: "No animation" },
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
          Presets
        </p>
        <PresetStrip activePresetId={activePresetId} onApply={onPresetApply} onError={onError} />
      </section>

      {/* ── кастомизация ── */}
      <section className="space-y-3">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">
          Customize
        </p>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <ColorField
            label="Text color"
            value={st.color ?? "#FFFFFF"}
            disabled={busy}
            onChange={(v) => onStyleChange({ color: v })}
          />
          <ColorField
            label="Highlight color"
            value={hl?.color ?? "#FF5A3D"}
            disabled={busy || hl === null}
            onChange={(v) => onHighlightChange({ color: v })}
          />
          <ColorField
            label="Outline"
            value={st.outline_color ?? "#000000"}
            disabled={busy}
            onChange={(v) => onStyleChange({ outline_color: v })}
          />
          <label className="flex flex-col gap-1.5 text-xs text-muted">
            Font
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
          label="Size"
          min={40}
          max={140}
          value={st.size ?? 90}
          disabled={busy}
          onCommit={(v) => onStyleChange({ size: v })}
        />

        <DebouncedSlider
          label="Position (from bottom)"
          min={40}
          max={1200}
          value={st.margin_v ?? 260}
          disabled={busy}
          onCommit={(v) => onStyleChange({ margin_v: v })}
          hint="Or just drag the captions on the video"
        />

        <label className="flex flex-col gap-1.5 text-xs text-muted">
          Active-word animation
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
            <option value="off">Highlight off</option>
          </Select>
        </label>

        <Checkbox
          checked={st.uppercase ?? true}
          disabled={busy}
          onChange={(e) => onStyleChange({ uppercase: e.target.checked })}
          label="UPPERCASE"
          className="text-xs"
        />

        {/* T3: авто-подсветка ключевых слов (числа + длинные контентные) */}
        <div className="space-y-2 border-t border-line pt-3">
          <Checkbox
            checked={!!st.emphasis_color}
            disabled={busy}
            onChange={(e) => onStyleChange({ emphasis_color: e.target.checked ? "#FF5A3D" : null })}
            label="Highlight keywords"
            className="text-xs"
          />
          {st.emphasis_color && (
            <ColorField
              label="Keyword color"
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
