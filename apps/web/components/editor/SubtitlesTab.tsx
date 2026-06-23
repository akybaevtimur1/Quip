"use client";

import { Check, Plus, RotateCcw, Scissors, Star, Trash2 } from "lucide-react";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { IconButton } from "@/components/ui/IconButton";
import { Badge } from "@/components/ui/Badge";
import { Checkbox } from "@/components/ui/Checkbox";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { Numeral } from "@/components/ui/Numeral";
import { Select } from "@/components/ui/Select";
import { Switch } from "@/components/ui/Switch";
import type { StylePreferencePayload, StyleTemplate } from "@/lib/api";
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

// Primary group title (tier 1): Onest semibold ink, NOT uppercase, with a hairline rule —
// the loud structural anchor. Eyebrow stays for tier-2 minor sub-captions inside a group.
function GroupTitle({ children, hint }: { children: ReactNode; hint?: string }) {
  return (
    <div className="flex items-baseline gap-2 border-t border-line pt-4">
      <h3 className="text-sm font-semibold text-ink">{children}</h3>
      {hint && <span className="text-xs text-muted">{hint}</span>}
    </div>
  );
}

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
  templates,
  defaultTemplateId,
  onApplyTemplateClip,
  onApplyTemplateAll,
  onSaveTemplate,
  onDeleteTemplate,
  onSetDefaultTemplate,
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
  /** The user's saved style templates + which one seeds new clips of future videos. */
  templates: StyleTemplate[];
  defaultTemplateId: string | null;
  /** Apply a template's look to THIS clip (instant). */
  onApplyTemplateClip: (look: StylePreferencePayload) => void;
  /** Apply a template to ALL clips (instant on this one, rest in background) → count. */
  onApplyTemplateAll: (look: StylePreferencePayload) => Promise<number>;
  /** Save the current look as a NAMED template (optionally the new-clip default). */
  onSaveTemplate: (name: string, setDefault: boolean) => Promise<void>;
  onDeleteTemplate: (id: string) => Promise<void>;
  onSetDefaultTemplate: (id: string, isDefault: boolean) => Promise<void>;
}) {
  const [editing, setEditing] = useState<number | null>(null);
  const [draft, setDraft] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const activeRef = useRef<HTMLDivElement>(null);
  // Templates: own busy keyed by action (no global busy → other controls stay live) + toast.
  const [tplBusy, setTplBusy] = useState<string | null>(null);
  const [tplMsg, setTplMsg] = useState<string | null>(null);
  const [newName, setNewName] = useState("");

  const flashTpl = (msg: string) => {
    setTplMsg(msg);
    setTimeout(() => setTplMsg(null), 3000);
  };

  const applyToClip = (t: StyleTemplate) => {
    onApplyTemplateClip(t.look);
    flashTpl(`Applied “${t.name}” to this clip`);
  };

  const applyToAll = async (t: StyleTemplate) => {
    setTplBusy(`all:${t.id}`);
    try {
      const n = await onApplyTemplateAll(t.look);
      flashTpl(`Applied “${t.name}” to ${n} clip${n === 1 ? "" : "s"}`);
    } catch (e) {
      onError(e instanceof Error ? e.message : "Couldn’t apply to all clips");
    } finally {
      setTplBusy(null);
    }
  };

  const saveCurrent = async () => {
    setTplBusy("save");
    try {
      await onSaveTemplate(newName.trim() || `My style ${templates.length + 1}`, false);
      setNewName("");
      flashTpl("Template saved");
    } catch (e) {
      onError(e instanceof Error ? e.message : "Couldn’t save the template");
    } finally {
      setTplBusy(null);
    }
  };

  const removeTpl = async (t: StyleTemplate) => {
    setTplBusy(`del:${t.id}`);
    try {
      await onDeleteTemplate(t.id);
    } catch (e) {
      onError(e instanceof Error ? e.message : "Couldn’t delete the template");
    } finally {
      setTplBusy(null);
    }
  };

  const toggleDefault = async (t: StyleTemplate) => {
    setTplBusy(`def:${t.id}`);
    try {
      await onSetDefaultTemplate(t.id, defaultTemplateId !== t.id);
      flashTpl(
        defaultTemplateId === t.id
          ? "No longer your default"
          : `“${t.name}” will start new videos`,
      );
    } catch (e) {
      onError(e instanceof Error ? e.message : "Couldn’t set default");
    } finally {
      setTplBusy(null);
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
        <Eyebrow tone="muted">Lines · click to edit · cut to drop from clip</Eyebrow>

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
                    className="shrink-0 pt-0.5 text-muted transition hover:text-accent"
                  >
                    <Numeral className="text-[10px]">{fmtSec(group[0].start)}</Numeral>
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
                        <Badge tone="neutral" className="ml-1.5 align-middle">
                          edited
                        </Badge>
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

      {/* ───────────── STYLE (appearance) — one clear group: how the captions LOOK ───────────── */}
      <GroupTitle hint="how your captions look">Style</GroupTitle>

      <section className="space-y-2">
        <Eyebrow tone="muted">Presets</Eyebrow>
        <PresetStrip activePresetId={activePresetId} onApply={onPresetApply} onError={onError} />
      </section>

      <section className="space-y-3">
        <Eyebrow tone="muted">Colors</Eyebrow>
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
        <Eyebrow tone="muted">Text</Eyebrow>
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
        <Eyebrow tone="muted">Position</Eyebrow>
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
        <Eyebrow tone="muted">Animation</Eyebrow>
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

      {/* ───────────── MY TEMPLATES (save a look → reuse on any clip / whole video) ───────────── */}
      <section className="space-y-2.5">
        <div className="flex items-center justify-between gap-2 border-t border-line pt-4">
          <h3 className="text-sm font-semibold text-ink">My templates</h3>
          {tplMsg && (
            <span className="truncate text-xs font-medium text-ok">{tplMsg}</span>
          )}
        </div>

        {templates.length === 0 ? (
          <p className="text-xs leading-snug text-muted">
            Save the current look as a template, then reuse it on any clip — or apply it to a
            whole video in one click. Star one to start every new video with it.
          </p>
        ) : (
          <div className="space-y-1.5">
            {templates.map((t) => {
              const isDefault = defaultTemplateId === t.id;
              const swatch = (t.look.style?.color as string) ?? "#ffffff";
              const hi = (t.look.highlight?.color as string | undefined) ?? null;
              const busyAll = tplBusy === `all:${t.id}`;
              return (
                <div
                  key={t.id}
                  className="flex items-center gap-2 rounded-md border border-line bg-surface-2 px-2.5 py-2"
                >
                  <span className="flex shrink-0 items-center -space-x-1">
                    <span
                      className="size-3.5 rounded-full ring-1 ring-line"
                      style={{ background: swatch }}
                    />
                    {hi && (
                      <span
                        className="size-3.5 rounded-full ring-1 ring-line"
                        style={{ background: hi }}
                      />
                    )}
                  </span>
                  <button
                    type="button"
                    onClick={() => applyToClip(t)}
                    disabled={busy}
                    title="Apply to this clip"
                    className="min-w-0 flex-1 truncate text-left text-xs font-semibold text-ink transition hover:text-accent disabled:opacity-50"
                  >
                    {t.name}
                    {isDefault && (
                      <Badge tone="neutral" className="ml-1.5 align-middle">
                        default
                      </Badge>
                    )}
                  </button>
                  <button
                    type="button"
                    onClick={() => void applyToAll(t)}
                    disabled={busy || tplBusy !== null}
                    title="Apply to ALL clips of this video"
                    className="shrink-0 rounded border border-line px-2 py-1 text-xs font-semibold text-muted transition duration-150 ease-snappy enabled:hover:border-line-strong enabled:hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 disabled:opacity-50"
                  >
                    {busyAll ? "Applying…" : "All clips"}
                  </button>
                  <IconButton
                    size="sm"
                    tone="accent"
                    title={isDefault ? "Default for new videos (click to unset)" : "Use for new videos"}
                    aria-label="Toggle default template"
                    disabled={tplBusy !== null}
                    onClick={() => void toggleDefault(t)}
                  >
                    <Star className={`size-3.5 ${isDefault ? "fill-current" : ""}`} />
                  </IconButton>
                  <IconButton
                    size="sm"
                    tone="danger"
                    title="Delete template"
                    aria-label="Delete template"
                    disabled={tplBusy !== null}
                    onClick={() => void removeTpl(t)}
                  >
                    <Trash2 className="size-3.5" />
                  </IconButton>
                </div>
              );
            })}
          </div>
        )}

        <div className="flex items-center gap-2">
          <input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="Name this style…"
            maxLength={60}
            onKeyDown={(e) => {
              if (e.key === "Enter") void saveCurrent();
            }}
            className="min-w-0 flex-1 rounded-md border border-line bg-surface-2 px-2.5 py-1.5 text-xs text-ink outline-none transition focus:border-accent/60"
          />
          <button
            type="button"
            onClick={() => void saveCurrent()}
            disabled={busy || tplBusy !== null}
            className="inline-flex shrink-0 items-center gap-1 rounded-md border border-line bg-surface-2 px-2.5 py-1.5 text-xs font-semibold text-muted transition duration-150 ease-snappy enabled:hover:border-line-strong enabled:hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 disabled:opacity-50"
          >
            {tplBusy === "save" ? (
              <Check className="size-3.5 text-ok" />
            ) : (
              <Plus className="size-3.5" />
            )}
            Save current
          </button>
        </div>
      </section>
    </div>
  );
}

function fmtSec(s: number): string {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, "0")}`;
}
