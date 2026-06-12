"use client";

import { RotateCcw, Scissors } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { CaptionReply, Word } from "@/lib/types";
import { originalReplyText } from "./replyUtils";

// ── Таб «Субтитры»: список реплик. Клик по тексту — правка (text_override);
// ✂ на строке — вырезать ЭТУ реплику из клипа целиком (не по одному слову —
// пословный грид убран как неудобный); ↩ — вернуть оригинальный текст.
// Правка текста доступна и здесь, и прямо на видео — оба пути в onReplyTextChange.
// Тонкую пословную нарезку юзер добивает в CapCut (экспорт-свобода).

export function CaptionsTab({
  words,
  replies,
  activeReplyIndex,
  busy,
  burn,
  onReplyTextChange,
  onCutReply,
  onSeekReply,
  onBurnChange,
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
}) {
  const [editing, setEditing] = useState<number | null>(null);
  const [draft, setDraft] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const activeRef = useRef<HTMLDivElement>(null);

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
    <div className="flex min-h-0 flex-1 flex-col gap-2">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">
        Реплики · клик — правка текста · ✂ — вырезать из клипа
      </p>

      {/* T4 #8: видео уже с вшитыми субтитрами → не накладывать наши (без двойных) */}
      <label className="flex items-center gap-2 rounded-lg border border-line bg-surface-2 px-2.5 py-2 text-xs text-muted">
        <input
          type="checkbox"
          checked={!burn}
          disabled={busy}
          onChange={(e) => onBurnChange(!e.target.checked)}
          className="size-3.5 accent-accent"
        />
        Видео уже с субтитрами — не накладывать наши
      </label>

      <div className={`min-h-0 flex-1 space-y-1 overflow-y-auto rounded-xl border border-line bg-surface-2 p-2 ${burn ? "" : "pointer-events-none opacity-40"}`}>
        {rows.map(({ reply, i, group }) => {
          if (reply.hidden || group.length === 0) return null;
          const text = reply.text_override ?? group.map((w) => w.text).join(" ");
          const isActive = i === activeReplyIndex;
          const isEditing = editing === i;
          return (
            <div
              key={i}
              ref={isActive ? activeRef : undefined}
              className={`group/reply rounded-lg border px-2.5 py-1.5 transition ${
                isActive ? "border-accent/50 bg-accent/10" : "border-transparent hover:border-line"
              }`}
            >
              <div className="flex items-start gap-2">
                <button
                  type="button"
                  onClick={() => onSeekReply(i)}
                  title="Перемотать к реплике"
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
                    className="w-full resize-none rounded-md border border-accent/60 bg-black/40 p-1.5 text-sm text-ink outline-none focus:ring-2 focus:ring-accent/40"
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
                      <span className="ml-1.5 align-middle rounded bg-accent/20 px-1 py-px text-[9px] font-semibold uppercase text-accent">
                        правка
                      </span>
                    )}
                  </button>
                )}

                {!isEditing && (
                  <span className="flex shrink-0 items-center gap-1.5 opacity-0 transition group-hover/reply:opacity-100">
                    {reply.text_override != null && (
                      <button
                        type="button"
                        title="Вернуть оригинальный текст"
                        onClick={() => onReplyTextChange(i, null)}
                        className="text-muted transition hover:text-accent"
                      >
                        <RotateCcw className="size-3.5" />
                      </button>
                    )}
                    <button
                      type="button"
                      title="Вырезать эту реплику из клипа"
                      disabled={busy}
                      onClick={() => onCutReply(i)}
                      className="text-muted transition hover:text-red-400 disabled:opacity-30"
                    >
                      <Scissors className="size-3.5" />
                    </button>
                  </span>
                )}
              </div>
            </div>
          );
        })}
        {rows.length === 0 && (
          <p className="px-2 py-3 text-xs text-muted">Нет реплик в этом клипе.</p>
        )}
      </div>
    </div>
  );
}

function fmtSec(s: number): string {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, "0")}`;
}
