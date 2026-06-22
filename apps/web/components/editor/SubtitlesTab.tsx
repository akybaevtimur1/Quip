"use client";

import { RotateCcw, Scissors } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { IconButton } from "@/components/ui/IconButton";
import { Checkbox } from "@/components/ui/Checkbox";
import { Select } from "@/components/ui/Select";
import { Switch } from "@/components/ui/Switch";
import type { CaptionReply, CaptionStyle, ClipEdit, HighlightStyle, Word } from "@/lib/types";
import { PresetStrip } from "../PresetStrip";
import { CAPTION_FONTS, ColorField, DebouncedSlider } from "./StyleControls";
import { originalReplyText } from "./replyUtils";

// ────────────────────────────────────────────────────────────────────────────
// SubtitlesTab — ОДИН таб для субтитров: и ТЕКСТ (что говорится), и СТИЛЬ (как
// выглядит). Раньше это были два таба (Captions / Style), которые резали ОДИН
// объект (CaptionTrack) надвое и путали юзера. Теперь: сверху строки (правка/
// вырезать/вернуть), ниже — пресеты и оформление. Семантика правок не изменилась
// (те же колбэки), это чисто реорганизация UI.
// ────────────────────────────────────────────────────────────────────────────

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

export function SubtitlesTab({
  words,
  replies,
  activeReplyIndex,
  busy,
  burn,
  onReplyTextChange,
  onCutReply,
  onSeekReply,
  onBurnChange,
  edit,
  activePresetId,
  onPresetApply,
  onError,
  onStyleChange,
  onHighlightChange,
  onApplyAll,
  onSaveDefault,
}: {
  words: Word[];
  replies: CaptionReply[];
  activeReplyIndex: number | null;
  busy: boolean;
  burn: boolean;
  onReplyTextChange: (replyIndex: number, text: string | null) => void;
  onCutReply: (replyIndex: number) => void;
  onSeekReply: (replyIndex: number) => void;
  onBurnChange: (burn: boolean) => void;
  edit: ClipEdit;
  activePresetId: string | null;
  onPresetApply: (presetId: string) => Promise<void>;
  onError: (msg: string) => void;
  onStyleChange: (patch: Partial<CaptionStyle>) => void;
  onHighlightChange: (patch: Partial<HighlightStyle> | null) => void;
  /** Apply this clip's look to every clip of the video → returns how many were updated. */
  onApplyAll: () => Promise<number>;
  /** Save this look as the user's default → future videos start from it. */
  onSaveDefault: () => Promise<void>;
}) {
  const [editing, setEditing] = useState<number | null>(null);
  const [draft, setDraft] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const activeRef = useRef<HTMLDivElement>(null);
  // Style-memory buttons: own busy + transient confirmation (no global busy → other controls stay live).
  const [reuseBusy, setReuseBusy] = useState<"all" | "default" | null>(null);
  const [reuseMsg, setReuseMsg] = useState<string | null>(null);

  const runReuse = async (kind: "all" | "default") => {
    setReuseBusy(kind);
    setReuseMsg(null);
    try {
      if (kind === "all") {
        const n = await onApplyAll();
        setReuseMsg(`Applied to ${n} clip${n === 1 ? "" : "s"}`);
      } else {
        await onSaveDefault();
        setReuseMsg("Saved — new videos will start with this style");
      }
      setTimeout(() => setReuseMsg(null), 3500);
    } catch (e) {
      onError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setReuseBusy(null);
    }
  };

  const st = edit.captions.style;
  const hl = edit.captions.highlight ?? null;

  useEffect(() => {
    if (editing !== null && textareaRef.current) {
      textareaRef.current.focus();
      textareaRef.current.select();
    }
  }, [editing]);

  // автоскролл к активной реплике (следим за видео)
  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [activeReplyIndex]);

  const startEdit = (i: number) => {
    const original = originalReplyText(replies, words, i);
    setDraft(replies[i]?.text_override ?? original);
    setEditing(i);
  };

  const commit = () => {
    if (editing === null) return;
    const i = editing;
    const original = originalReplyText(replies, words, i);
    const trimmed = draft.trim();
    setEditing(null);
    onReplyTextChange(i, trimmed && trimmed !== original ? trimmed : null);
  };

  // позиционный offset слов для каждой реплики (для отображения текста)
  const rows = useMemo(() => {
    const out: { reply: CaptionReply; i: number; group: Word[] }[] = [];
    for (let i = 0, offset = 0; i < replies.length; i++) {
      const count = replies[i].word_refs.length;
      out.push({ reply: replies[i], i, group: words.slice(offset, offset + count) });
      offset += count;
    }
    return out;
  }, [replies, words]);

  return (
    <div className="flex flex-col gap-5 pr-1">
      {/* ───────────── LINES (content) ───────────── */}
      <section className="flex flex-col gap-2">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">
          Lines · click to edit text · ✂ to cut from clip
        </p>

        {/* видео уже с вшитыми субтитрами → не накладывать наши (без двойных) */}
        <div className="rounded-md border border-line bg-surface-2 px-2.5 py-2">
          <Switch
            checked={!burn}
            disabled={busy}
            onChange={(e) => onBurnChange(!e.target.checked)}
            label="Video already has captions — don’t overlay ours"
            className="w-full text-xs"
          />
        </div>

        <div
          className={`max-h-[38vh] min-h-[8rem] space-y-1 overflow-y-auto rounded-md border border-line bg-surface-2 p-2 ${
            burn ? "" : "pointer-events-none opacity-40"
          }`}
        >
          {rows.map(({ reply, i, group }) => {
            if (reply.hidden || group.length === 0) return null;
            const text = reply.text_override ?? group.map((w) => w.text).join(" ");
            const isActive = i === activeReplyIndex;
            const isEditing = editing === i;
            return (
              <div
                key={i}
                ref={isActive ? activeRef : undefined}
                className={`group/reply rounded-md border-l-2 px-2.5 py-1.5 transition ${
                  isActive
                    ? "border-l-accent bg-surface-3"
                    : "border-l-transparent hover:bg-surface-2"
                }`}
              >
                <div className="flex items-start gap-2">
                  <button
                    type="button"
                    onClick={() => onSeekReply(i)}
                    title="Jump to line"
                    className="shrink-0 pt-0.5 font-mono text-[10px] tabular-nums text-muted transition hover:text-accent"
                  >
                    {fmtSec(group[0].start)}
                  </button>

                  {isEditing ? (
                    <textarea
                      ref={textareaRef}
                      value={draft}
                      onChange={(e) => setDraft(e.target.value)}
                      onBlur={commit}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                          e.preventDefault();
                          commit();
                        } else if (e.key === "Escape") {
                          e.preventDefault();
                          setEditing(null);
                        }
                      }}
                      rows={2}
                      className="w-full resize-none rounded-sm border border-accent/60 bg-bg p-1.5 text-sm text-ink outline-none transition-colors focus:border-accent"
                    />
                  ) : (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => startEdit(i)}
                      className="min-w-0 flex-1 text-left text-sm leading-snug text-ink transition hover:text-accent"
                    >
                      {text}
                      {reply.text_override != null && (
                        <span className="ml-1.5 align-middle rounded bg-accent px-1 py-px text-[9px] font-bold uppercase text-bg">
                          edit
                        </span>
                      )}
                    </button>
                  )}

                  {!isEditing && (
                    <span className="flex shrink-0 items-center gap-1 transition focus-within:opacity-100 [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover/reply:opacity-100">
                      {reply.text_override != null && (
                        <IconButton
                          size="sm"
                          tone="accent"
                          title="Restore original text"
                          aria-label="Restore original text"
                          onClick={() => onReplyTextChange(i, null)}
                        >
                          <RotateCcw className="size-3.5" />
                        </IconButton>
                      )}
                      <IconButton
                        size="sm"
                        tone="danger"
                        title="Cut this line from the clip"
                        aria-label="Cut this line from the clip"
                        disabled={busy}
                        onClick={() => onCutReply(i)}
                      >
                        <Scissors className="size-3.5" />
                      </IconButton>
                    </span>
                  )}
                </div>
              </div>
            );
          })}
          {rows.length === 0 && (
            <p className="px-2 py-3 text-xs text-muted">No lines in this clip.</p>
          )}
        </div>
      </section>

      <div className="border-t border-line" />

      {/* ───────────── STYLE (appearance) ───────────── */}
      <section className="space-y-2">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">Presets</p>
        <PresetStrip activePresetId={activePresetId} onApply={onPresetApply} onError={onError} />
      </section>

      <section className="space-y-3">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">Colors</p>
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
        </div>

        <div className="space-y-2 border-t border-line pt-3">
          <Checkbox
            checked={!!st.emphasis_color}
            disabled={busy}
            onChange={(e) =>
              onStyleChange({ emphasis_color: e.target.checked ? "#FF5A3D" : null })
            }
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

      <section className="space-y-3">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">Text</p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
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
        <Checkbox
          checked={st.uppercase ?? true}
          disabled={busy}
          onChange={(e) => onStyleChange({ uppercase: e.target.checked })}
          label="UPPERCASE"
          className="text-xs"
        />
      </section>

      <section className="space-y-3">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">Position</p>
        <DebouncedSlider
          label="Position (from bottom)"
          min={40}
          max={1200}
          value={st.margin_v ?? 260}
          disabled={busy}
          onCommit={(v) => onStyleChange({ margin_v: v, pos_y: null })}
          hint="Or just drag the captions on the video"
        />
      </section>

      <section className="space-y-3">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">Animation</p>
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
      </section>

      {/* ───────────── REUSE THIS STYLE (style memory) ───────────── */}
      <section className="space-y-2 border-t border-line pt-4">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">
          Reuse this style
        </p>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <button
            type="button"
            disabled={busy || reuseBusy !== null}
            onClick={() => void runReuse("all")}
            className="rounded-md border border-line bg-surface-2 px-3 py-2 text-xs font-semibold text-ink transition enabled:hover:border-line-strong enabled:hover:bg-surface-3 disabled:opacity-50"
          >
            {reuseBusy === "all" ? "Applying…" : "Apply to all clips"}
          </button>
          <button
            type="button"
            disabled={busy || reuseBusy !== null}
            onClick={() => void runReuse("default")}
            className="rounded-md border border-line bg-surface-2 px-3 py-2 text-xs font-semibold text-ink transition enabled:hover:border-line-strong enabled:hover:bg-surface-3 disabled:opacity-50"
          >
            {reuseBusy === "default" ? "Saving…" : "Save as my default"}
          </button>
        </div>
        <p className="text-[11px] leading-snug text-muted">
          {reuseMsg ? (
            <span className="font-medium text-accent">{reuseMsg}</span>
          ) : (
            "Apply this clip’s look to every clip of this video, or save it as the default for your future videos."
          )}
        </p>
      </section>
    </div>
  );
}

function fmtSec(s: number): string {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, "0")}`;
}
