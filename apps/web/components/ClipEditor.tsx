"use client";

import { CheckCircle, Film, Loader2, Scissors, Type } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  extendClip,
  getClipAnalysis,
  getClipEdit,
  getRenderStatus,
  patchClipEdit,
  startRenderClip,
  trimClip,
} from "@/lib/api";
import type { CaptionReply, ClipEdit, Word } from "@/lib/types";

const WORKER_BASE = process.env.NEXT_PUBLIC_WORKER_URL ?? "";

function resolveUrl(url: string) {
  if (!url || url.startsWith("http")) return url;
  return `${WORKER_BASE}/${url}`;
}

interface ClipEditorProps {
  jobId: string;
  clipId: string;
  onRenderDone: (newVideoUrl: string) => void;
  // called whenever edit state changes so ClipCard can sync the CC overlay
  onRepliesChange?: (replies: CaptionReply[] | null) => void;
}

type Phase = "loading" | "ready" | "saving" | "rendering" | "done" | "error";

export default function ClipEditor({ jobId, clipId, onRenderDone, onRepliesChange }: ClipEditorProps) {
  const [phase, setPhase] = useState<Phase>("loading");
  const [error, setError] = useState<string | null>(null);
  const [edit, setEdit] = useState<ClipEdit | null>(null);
  const [words, setWords] = useState<Word[]>([]);
  const [globalIndices, setGlobalIndices] = useState<number[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [extendSec, setExtendSec] = useState<string>("5");
  const [renderElapsed, setRenderElapsed] = useState(0);
  const [loadKey, setLoadKey] = useState(0);

  // Subtitle editing: maps reply index → draft text
  const [captionEdits, setCaptionEdits] = useState<Record<number, string>>({});
  const [savingCaptions, setSavingCaptions] = useState(false);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPoll = useCallback(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
  }, []);

  // Notify parent whenever replies change (for CC overlay sync)
  useEffect(() => {
    onRepliesChange?.(edit?.captions.replies ?? null);
  }, [edit, onRepliesChange]);

  useEffect(() => {
    let cancelled = false;
    async function fetchData() {
      setPhase("loading");
      setError(null);
      setSelected(new Set());
      setCaptionEdits({});
      try {
        const [editData, analysisData] = await Promise.all([
          getClipEdit(jobId, clipId),
          getClipAnalysis(jobId, clipId),
        ]);
        if (cancelled) return;
        setEdit(editData);
        setWords(analysisData.words);
        setGlobalIndices((editData.captions.replies ?? []).flatMap((r) => r.word_refs));
        setPhase("ready");
      } catch (e) {
        if (cancelled) return;
        setError(String(e));
        setPhase("error");
      }
    }
    fetchData();
    return () => { cancelled = true; stopPoll(); };
  }, [jobId, clipId, loadKey, stopPoll]);

  // Build caption display groups using positional mapping:
  // reply[i] covers analysis_words[offset .. offset + len(word_refs)]
  const captionGroups = useMemo(() => {
    if (!edit?.captions.replies || words.length === 0) return [];
    let offset = 0;
    return edit.captions.replies.map((reply) => {
      const count = reply.word_refs.length;
      const group = words.slice(offset, offset + count);
      offset += count;
      return {
        reply,
        defaultText: group.map((w) => w.text).join(" "),
      };
    });
  }, [edit, words]);

  const toggleWord = (pos: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(pos)) next.delete(pos); else next.add(pos);
      return next;
    });
  };

  const handleConflict = () => {
    setError("Данные обновились — попробуй ещё раз");
    setLoadKey((k) => k + 1);
  };

  const handleTrim = async () => {
    if (!edit || selected.size === 0) return;
    const wordIndices = Array.from(selected).map((pos) => globalIndices[pos]);
    setPhase("saving");
    setError(null);
    try {
      const newEdit = await trimClip(jobId, clipId, edit.version ?? 1, wordIndices);
      const analysisData = await getClipAnalysis(jobId, clipId);
      setEdit(newEdit);
      setWords(analysisData.words);
      setGlobalIndices((newEdit.captions.replies ?? []).flatMap((r) => r.word_refs));
      setSelected(new Set());
      setCaptionEdits({});
      setPhase("ready");
    } catch (e) {
      const msg = String(e);
      if (msg.includes("conflict") || msg.includes("409")) handleConflict();
      else { setError(msg); setPhase("ready"); }
    }
  };

  const handleExtend = async (secs: number) => {
    if (!edit) return;
    const lastInterval = edit.source_intervals[edit.source_intervals.length - 1];
    if (!lastInterval) return;
    const newEnd = lastInterval.source_end + secs;
    setPhase("saving");
    setError(null);
    try {
      const newEdit = await extendClip(jobId, clipId, edit.version ?? 1, "end", newEnd);
      const analysisData = await getClipAnalysis(jobId, clipId);
      setEdit(newEdit);
      setWords(analysisData.words);
      setGlobalIndices((newEdit.captions.replies ?? []).flatMap((r) => r.word_refs));
      setSelected(new Set());
      setCaptionEdits({});
      setPhase("ready");
    } catch (e) {
      const msg = String(e);
      if (msg.includes("conflict") || msg.includes("409")) handleConflict();
      else { setError(msg); setPhase("ready"); }
    }
  };

  const handleSaveCaptions = async () => {
    if (!edit || Object.keys(captionEdits).length === 0) return;
    setSavingCaptions(true);
    setError(null);
    try {
      const updatedReplies = (edit.captions.replies ?? []).map((reply, i): CaptionReply => ({
        ...reply,
        // captionEdits[i] = user typed something; empty string means clear override
        text_override: captionEdits[i] !== undefined
          ? (captionEdits[i].trim() || null)
          : reply.text_override,
      }));
      const newEdit = await patchClipEdit(jobId, clipId, edit.version ?? 1, {
        ...edit.captions,
        replies: updatedReplies,
      });
      setEdit(newEdit);
      setCaptionEdits({});
    } catch (e) {
      const msg = String(e);
      if (msg.includes("conflict") || msg.includes("409")) handleConflict();
      else setError(msg);
    } finally {
      setSavingCaptions(false);
    }
  };

  const handleRender = async () => {
    if (!edit) return;
    setPhase("rendering");
    setRenderElapsed(0);
    setError(null);
    stopPoll();
    try {
      await startRenderClip(jobId, clipId);
    } catch (e) {
      setError(String(e));
      setPhase("ready");
      return;
    }
    timerRef.current = setInterval(() => setRenderElapsed((s) => s + 1), 1000);
    pollRef.current = setInterval(async () => {
      try {
        const st = await getRenderStatus(jobId, clipId);
        if (st.status === "done" && st.video_url) {
          stopPoll();
          setPhase("done");
          onRenderDone(resolveUrl(st.video_url));
        } else if (st.status === "failed") {
          stopPoll();
          setError(st.error ?? "Render failed");
          setPhase("ready");
        }
      } catch { /* keep polling */ }
    }, 2000);
  };

  if (phase === "loading") {
    return (
      <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted">
        <Loader2 className="size-4 animate-spin" />
        Loading transcript…
      </div>
    );
  }

  if (phase === "error" && !edit) {
    return (
      <div className="space-y-2 py-4 text-center text-sm">
        <p className="text-red-400">{error}</p>
        <button
          onClick={() => setLoadKey((k) => k + 1)}
          className="rounded-lg border border-line px-3 py-1.5 text-xs text-muted hover:text-ink transition-colors"
        >
          Try again
        </button>
      </div>
    );
  }

  const totalSec = edit
    ? edit.source_intervals.reduce((s, iv) => s + (iv.source_end - iv.source_start), 0)
    : 0;
  const busy = phase === "saving" || phase === "rendering" || savingCaptions;
  const cutCount = edit ? edit.source_intervals.length - 1 : 0;
  const dirtyCapCount = Object.keys(captionEdits).length;

  return (
    <div className="divide-y divide-line">

      {/* ── HEADER ── */}
      <div className="flex items-center justify-between px-4 py-3">
        <div className="flex items-center gap-2">
          <Scissors className="size-4 text-accent" />
          <span className="font-medium text-ink text-sm">Edit clip</span>
        </div>
        <div className="flex items-center gap-3 text-xs text-muted font-mono">
          <span>{totalSec.toFixed(1)}s</span>
          {cutCount > 0 && (
            <span className="rounded-full bg-accent/15 px-2 py-0.5 text-accent">
              {cutCount} cut{cutCount > 1 ? "s" : ""}
            </span>
          )}
        </div>
      </div>

      {/* ── ERROR BANNER ── */}
      {error && (
        <div className="px-4 py-2 text-xs text-red-400 bg-red-900/20">
          {error}
        </div>
      )}

      {/* ── STEP 1: SUBTITLES ── */}
      <div className="px-4 py-3 space-y-2">
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold text-muted uppercase tracking-wider flex items-center gap-1.5">
            <Type className="size-3" />
            1 · Субтитры
          </p>
          {dirtyCapCount > 0 && (
            <span className="text-xs text-accent">{dirtyCapCount} изменено</span>
          )}
        </div>

        <div className="max-h-56 overflow-y-auto space-y-1 rounded-xl border border-line bg-surface p-2">
          {captionGroups.length === 0 && (
            <span className="block text-xs text-muted py-1 px-1">Нет субтитров</span>
          )}
          {captionGroups.map(({ reply, defaultText }, i) => {
            const isDirty = captionEdits[i] !== undefined;
            const hasOverride = reply.text_override != null;
            const displayValue = isDirty
              ? captionEdits[i]
              : (reply.text_override ?? defaultText);
            return (
              <div
                key={i}
                className={`flex items-center gap-1.5 rounded-lg border px-2 py-1.5 transition ${
                  isDirty
                    ? "border-accent/40 bg-accent/5"
                    : hasOverride
                    ? "border-yellow-500/30 bg-yellow-500/5"
                    : "border-transparent bg-surface-2"
                }`}
              >
                <span className="shrink-0 text-[10px] font-mono text-muted w-5 text-right">{i + 1}</span>
                <input
                  type="text"
                  value={displayValue}
                  onChange={(e) =>
                    setCaptionEdits((prev) => ({ ...prev, [i]: e.target.value }))
                  }
                  disabled={busy}
                  className="min-w-0 flex-1 bg-transparent text-xs font-semibold uppercase text-ink outline-none disabled:opacity-50 placeholder:text-muted"
                  placeholder={defaultText.toUpperCase()}
                />
                {(isDirty || hasOverride) && (
                  <button
                    type="button"
                    disabled={busy}
                    title="Сбросить к оригиналу"
                    onClick={() => {
                      if (isDirty) {
                        setCaptionEdits((prev) => {
                          const next = { ...prev };
                          delete next[i];
                          return next;
                        });
                      } else {
                        // clear persisted override
                        setCaptionEdits((prev) => ({ ...prev, [i]: "" }));
                      }
                    }}
                    className="shrink-0 text-[10px] text-muted hover:text-red-400 transition"
                  >
                    ✕
                  </button>
                )}
              </div>
            );
          })}
        </div>

        {dirtyCapCount > 0 && (
          <button
            disabled={busy}
            onClick={handleSaveCaptions}
            className="flex w-full items-center justify-center gap-2 rounded-xl border border-accent/50 bg-accent/10 py-2 text-sm font-semibold text-accent transition hover:bg-accent/20 disabled:opacity-30"
          >
            {savingCaptions
              ? <><Loader2 className="size-4 animate-spin" /> Сохраняю…</>
              : `Сохранить правки субтитров (${dirtyCapCount})`}
          </button>
        )}

        <p className="text-xs text-muted">
          Отредактируй текст → «Сохранить» → нажми «Рендерить» чтобы прожечь в видео.
          После рендера — отключи CC.
        </p>
      </div>

      {/* ── STEP 2: CUT WORDS ── */}
      <div className="px-4 py-3 space-y-2">
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold text-muted uppercase tracking-wider">
            2 · Вырезать слова
          </p>
          {selected.size > 0 && (
            <button
              onClick={() => setSelected(new Set())}
              className="text-xs text-muted hover:text-ink transition-colors"
            >
              Сбросить
            </button>
          )}
        </div>

        <div className="flex flex-wrap gap-1 max-h-44 overflow-y-auto rounded-xl border border-line bg-surface p-2">
          {words.map((w, i) => (
            <button
              key={i}
              disabled={busy}
              onClick={() => toggleWord(i)}
              title={`${w.start.toFixed(1)}s – ${w.end.toFixed(1)}s`}
              className={[
                "rounded-md px-2 py-1 text-xs transition-all select-none",
                selected.has(i)
                  ? "bg-red-500/20 text-red-400 line-through ring-1 ring-red-500/40"
                  : "bg-surface-2 text-ink hover:ring-1 hover:ring-line",
              ].join(" ")}
            >
              {w.text}
            </button>
          ))}
          {words.length === 0 && (
            <span className="text-xs text-muted py-1">Нет слов</span>
          )}
        </div>

        {selected.size > 0 ? (
          <p className="text-xs text-red-400">{selected.size} слов будет вырезано из клипа</p>
        ) : (
          <p className="text-xs text-muted">Нажми на слово чтобы отметить его.</p>
        )}

        <button
          disabled={busy || selected.size === 0}
          onClick={handleTrim}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-red-600/80 py-2 text-sm font-semibold text-white transition-colors hover:bg-red-600 disabled:cursor-not-allowed disabled:opacity-30"
        >
          {phase === "saving" ? (
            <><Loader2 className="size-4 animate-spin" /> Сохраняю…</>
          ) : (
            <><Scissors className="size-4" /> Вырезать {selected.size > 0 ? `(${selected.size} слов)` : ""}</>
          )}
        </button>
      </div>

      {/* ── STEP 3: EXTEND ── */}
      <div className="px-4 py-3 space-y-2">
        <p className="text-xs font-semibold text-muted uppercase tracking-wider">
          3 · Продлить конец клипа
        </p>
        <div className="flex gap-2">
          {[3, 5, 10, 15].map((s) => (
            <button
              key={s}
              disabled={busy}
              onClick={() => handleExtend(s)}
              className="flex-1 rounded-xl border border-line bg-surface py-2 text-xs font-medium text-ink transition-colors hover:border-accent/50 hover:text-accent disabled:opacity-30"
            >
              +{s}s
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <input
            type="number"
            value={extendSec}
            onChange={(e) => setExtendSec(e.target.value)}
            disabled={busy}
            min="0.5"
            step="0.5"
            className="w-20 rounded-xl border border-line bg-surface px-3 py-2 text-xs text-ink disabled:opacity-30 focus:outline-none focus:ring-1 focus:ring-accent/50"
          />
          <span className="text-xs text-muted">секунд</span>
          <button
            disabled={busy}
            onClick={() => handleExtend(parseFloat(extendSec) || 5)}
            className="flex-1 rounded-xl border border-line bg-surface py-2 text-xs font-medium text-ink transition-colors hover:border-accent/50 hover:text-accent disabled:opacity-30"
          >
            Применить
          </button>
        </div>
      </div>

      {/* ── STEP 4: RE-RENDER ── */}
      <div className="px-4 py-3 space-y-2">
        <p className="text-xs font-semibold text-muted uppercase tracking-wider">
          4 · Рендер с правками
        </p>

        {phase === "done" ? (
          <div className="flex items-center gap-2 rounded-xl bg-green-900/30 px-4 py-3 text-sm text-green-400">
            <CheckCircle className="size-5 shrink-0" />
            <span>Готово — видео обновилось сверху</span>
          </div>
        ) : phase === "rendering" ? (
          <div className="rounded-xl border border-accent/20 bg-accent/5 px-4 py-3">
            <div className="flex items-center gap-2 text-sm text-accent">
              <Loader2 className="size-4 animate-spin" />
              <span>Рендеринг… {renderElapsed}s</span>
            </div>
            <p className="mt-1 text-xs text-muted">Обычно 10–30 секунд. Видео появится автоматически.</p>
          </div>
        ) : (
          <>
            {dirtyCapCount > 0 && (
              <p className="text-xs text-yellow-400">
                ⚠ Есть несохранённые правки субтитров — сохрани их перед рендером.
              </p>
            )}
            <p className="text-xs text-muted">
              Нажми — клип перерендерится с твоими вырезками и субтитрами. Видео сверху обновится автоматически.
            </p>
            <button
              disabled={busy}
              onClick={handleRender}
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-accent py-2.5 text-sm font-semibold text-white transition-colors hover:bg-accent-2 disabled:opacity-30"
            >
              <Film className="size-4" />
              Рендерить клип
            </button>
          </>
        )}
      </div>

    </div>
  );
}
