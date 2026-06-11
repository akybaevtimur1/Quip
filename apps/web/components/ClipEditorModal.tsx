"use client";

import {
  CheckCircle,
  Film,
  Loader2,
  Move,
  Palette,
  Scissors,
  Type,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  getClipAnalysis,
  getClipEdit,
  getRenderStatus,
  getTimeline,
  patchClipEdit,
  setClipInterval,
  startRenderClip,
  trimClip,
} from "@/lib/api";
import type { CaptionReply, ClipEdit, ClipOut, TimelineData, Word } from "@/lib/types";
import { CaptionOverlay } from "./CaptionOverlay";
import { resolveUrl } from "./ClipCard";
import { PresetStrip } from "./PresetStrip";
import TimelineEditor from "./TimelineEditor";

// ────────────────────────────────────────────────────────────────────────────
// ClipEditorModal — широкая модалка-редактор клипа (замена инлайн-редактору).
// ЛЕВО: видео 9:16 + CaptionOverlay (editing) + галерея пресетов.
// ПРАВО: широкий таймлайн «Момент на видео» + вырезание слов + рендер.
// Логика адаптирована из ClipEditor.tsx (та же семантика optimistic-lock/poll).
// ────────────────────────────────────────────────────────────────────────────

interface ClipEditorModalProps {
  jobId: string;
  clipId: string;
  clip: ClipOut;
  onClose: () => void;
  onRenderDone: (url: string) => void;
}

type Phase = "loading" | "ready" | "saving" | "rendering" | "done" | "error";

export default function ClipEditorModal({
  jobId,
  clipId,
  clip,
  onClose,
  onRenderDone,
}: ClipEditorModalProps) {
  const [phase, setPhase] = useState<Phase>("loading");
  const [error, setError] = useState<string | null>(null);
  const [edit, setEdit] = useState<ClipEdit | null>(null);
  const [words, setWords] = useState<Word[]>([]);
  const [globalIndices, setGlobalIndices] = useState<number[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [renderElapsed, setRenderElapsed] = useState(0);
  const [loadKey, setLoadKey] = useState(0);

  const [timeline, setTimeline] = useState<TimelineData | null>(null);
  const [activePresetId, setActivePresetId] = useState<string | null>(null);

  const videoRef = useRef<HTMLVideoElement>(null);
  const presetRef = useRef<HTMLDivElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const videoSrc = useMemo(() => resolveUrl(clip.video_url), [clip.video_url]);

  const stopPoll = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  // ── Esc закрывает модалку ──
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // ── загрузка edit-state + analysis (параллельно), timeline отдельно/не-фатально ──
  useEffect(() => {
    let cancelled = false;
    async function fetchData() {
      setPhase("loading");
      setError(null);
      setSelected(new Set());
      setActivePresetId(null);
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
        getTimeline(jobId)
          .then((t) => {
            if (!cancelled) setTimeline(t);
          })
          .catch(() => {
            if (!cancelled) setTimeline(null);
          });
      } catch (e) {
        if (cancelled) return;
        setError(String(e));
        setPhase("error");
      }
    }
    fetchData();
    return () => {
      cancelled = true;
      stopPoll();
    };
  }, [jobId, clipId, loadKey, stopPoll]);

  const handleConflict = useCallback(() => {
    setError("Данные обновились — перезагружаю редактор…");
    setLoadKey((k) => k + 1);
  }, []);

  const toggleWord = (pos: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(pos)) next.delete(pos);
      else next.add(pos);
      return next;
    });
  };

  // ── refetch analysis после любого изменения интервалов (trim / set-interval) ──
  const refetchAfter = useCallback(
    async (newEdit: ClipEdit) => {
      const analysisData = await getClipAnalysis(jobId, clipId);
      setEdit(newEdit);
      setWords(analysisData.words);
      setGlobalIndices((newEdit.captions.replies ?? []).flatMap((r) => r.word_refs));
      setSelected(new Set());
      setPhase("ready");
    },
    [jobId, clipId],
  );

  const handleSetInterval = useCallback(
    async (start: number, end: number) => {
      if (!edit) return;
      setPhase("saving");
      setError(null);
      try {
        const newEdit = await setClipInterval(jobId, clipId, edit.version ?? 1, start, end);
        await refetchAfter(newEdit);
      } catch (e) {
        const msg = String(e);
        if (msg.includes("conflict") || msg.includes("409")) handleConflict();
        else {
          setError(msg);
          setPhase("ready");
        }
      }
    },
    [edit, jobId, clipId, refetchAfter, handleConflict],
  );

  const handleTrim = async () => {
    if (!edit || selected.size === 0) return;
    const wordIndices = Array.from(selected).map((pos) => globalIndices[pos]);
    setPhase("saving");
    setError(null);
    try {
      const newEdit = await trimClip(jobId, clipId, edit.version ?? 1, wordIndices);
      await refetchAfter(newEdit);
    } catch (e) {
      const msg = String(e);
      if (msg.includes("conflict") || msg.includes("409")) handleConflict();
      else {
        setError(msg);
        setPhase("ready");
      }
    }
  };

  // ── inline-правка субтитра (контракт CaptionOverlay: replyIndex выровнен по replies) ──
  const handleCaptionsChange = useCallback(
    async (replyIndex: number, text: string | null) => {
      if (!edit) return;
      const replies = (edit.captions.replies ?? []).map(
        (reply, i): CaptionReply =>
          i === replyIndex ? { ...reply, text_override: text } : reply,
      );
      setError(null);
      try {
        const newEdit = await patchClipEdit(jobId, clipId, edit.version ?? 1, {
          ...edit.captions,
          replies,
        });
        setEdit(newEdit);
      } catch (e) {
        const msg = String(e);
        if (msg.includes("conflict") || msg.includes("409")) handleConflict();
        else setError(msg);
      }
    },
    [edit, jobId, clipId, handleConflict],
  );

  const handleMarginChange = useCallback(
    async (marginV: number) => {
      if (!edit) return;
      setError(null);
      try {
        const newEdit = await patchClipEdit(jobId, clipId, edit.version ?? 1, {
          ...edit.captions,
          style: { ...edit.captions.style, margin_v: marginV },
        });
        setEdit(newEdit);
      } catch (e) {
        const msg = String(e);
        if (msg.includes("conflict") || msg.includes("409")) handleConflict();
        else setError(msg);
      }
    },
    [edit, jobId, clipId, handleConflict],
  );

  const handleStyleClick = useCallback(() => {
    presetRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, []);

  const handlePresetApplied = (updated: ClipEdit, presetId: string) => {
    setEdit(updated);
    setActivePresetId(presetId);
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
      } catch {
        /* keep polling */
      }
    }, 2000);
  };

  const busy = phase === "saving" || phase === "rendering";
  const totalSec = edit
    ? edit.source_intervals.reduce((s, iv) => s + (iv.source_end - iv.source_start), 0)
    : 0;
  const cutCount = edit ? edit.source_intervals.length - 1 : 0;
  const replies = edit?.captions.replies ?? null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Редактор клипа"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6"
    >
      {/* backdrop */}
      <button
        type="button"
        aria-label="Закрыть редактор"
        onClick={onClose}
        className="absolute inset-0 cursor-default bg-black/70 backdrop-blur-sm"
      />

      {/* dialog */}
      <div className="relative flex max-h-[92vh] w-full max-w-6xl flex-col overflow-hidden rounded-2xl border border-line bg-surface shadow-2xl">
        {/* ── header ── */}
        <div className="flex shrink-0 items-center justify-between border-b border-line px-6 py-4">
          <div className="flex items-center gap-2.5">
            <Scissors className="size-5 text-accent" />
            <h2 className="font-display text-lg font-semibold text-ink">Редактор клипа</h2>
            <span className="ml-2 font-mono text-xs text-muted">{totalSec.toFixed(1)}s</span>
            {cutCount > 0 && (
              <span className="rounded-full bg-accent/15 px-2 py-0.5 font-mono text-xs text-accent">
                {cutCount} cut{cutCount > 1 ? "s" : ""}
              </span>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Закрыть"
            className="inline-flex size-9 items-center justify-center rounded-lg border border-line text-muted transition hover:border-accent/50 hover:text-ink focus:outline-none focus:ring-2 focus:ring-accent/40"
          >
            <X className="size-5" />
          </button>
        </div>

        {/* ── error banner ── */}
        {error && (
          <div className="shrink-0 border-b border-red-900/40 bg-red-900/20 px-6 py-2.5 text-sm text-red-300">
            {error}
          </div>
        )}

        {/* ── body ── */}
        {phase === "loading" ? (
          <div className="flex flex-1 items-center justify-center gap-2 py-24 text-sm text-muted">
            <Loader2 className="size-4 animate-spin" />
            Загружаю транскрипт…
          </div>
        ) : phase === "error" && !edit ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 py-24 text-center text-sm">
            <p className="max-w-md text-red-400">{error}</p>
            <button
              onClick={() => setLoadKey((k) => k + 1)}
              className="rounded-lg border border-line px-4 py-2 text-xs text-muted transition-colors hover:text-ink"
            >
              Попробовать снова
            </button>
          </div>
        ) : (
          <div className="flex flex-1 flex-col gap-6 overflow-y-auto p-6 lg:flex-row">
            {/* ════ ЛЕВО: видео + пресеты ════ */}
            <div className="flex w-full shrink-0 flex-col gap-3 lg:w-[360px]">
              <div className="relative overflow-hidden rounded-xl border border-line bg-black">
                <video
                  ref={videoRef}
                  key={videoSrc}
                  src={videoSrc}
                  controls
                  playsInline
                  preload="metadata"
                  className="aspect-[9/16] w-full bg-black object-contain"
                />
                {words.length > 0 && edit && (
                  <CaptionOverlay
                    editing
                    words={words}
                    clipStart={clip.start}
                    videoRef={videoRef}
                    replies={replies}
                    style={edit.captions.style}
                    highlight={edit.captions.highlight}
                    onCaptionsChange={handleCaptionsChange}
                    onMarginChange={handleMarginChange}
                    onStyleClick={handleStyleClick}
                  />
                )}
              </div>

              <p className="text-xs leading-snug text-muted">
                Кликни по субтитру на видео — правь текст. Стрелки ↑↓ — двигают субтитр. Стиль — ниже.
              </p>

              {/* галерея стилей */}
              <div ref={presetRef} className="space-y-1.5">
                <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted">
                  <Palette className="size-3" />
                  Стиль субтитров
                </p>
                {edit && (
                  <PresetStrip
                    jobId={jobId}
                    clipId={clipId}
                    version={edit.version ?? 1}
                    activePresetId={activePresetId}
                    onApplied={handlePresetApplied}
                    onConflict={handleConflict}
                    onError={setError}
                  />
                )}
              </div>
            </div>

            {/* ════ ПРАВО: таймлайн + вырезать слова + рендер ════ */}
            <div className="flex min-w-0 flex-1 flex-col gap-6">
              {/* ── момент на видео (широкий таймлайн) ── */}
              <section className="space-y-2.5">
                <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted">
                  <Move className="size-3.5" />
                  Момент на видео
                </p>
                {timeline && edit ? (
                  <>
                    <TimelineEditor
                      jobId={jobId}
                      clipId={clipId}
                      version={edit.version ?? 1}
                      data={timeline}
                      interval={{
                        source_start: edit.source_intervals[0]?.source_start ?? 0,
                        source_end:
                          edit.source_intervals[edit.source_intervals.length - 1]?.source_end ?? 0,
                      }}
                      onIntervalChange={handleSetInterval}
                    />
                    <p className="text-xs leading-snug text-muted">
                      Тащи блок — двигать; края — короче/длиннее. Цветные маркеры = сильные
                      моменты ИИ (клик — прыгнуть). Превью обновится после рендера.
                    </p>
                  </>
                ) : (
                  <div className="rounded-xl border border-dashed border-line bg-surface-2 px-4 py-6 text-center text-xs text-muted">
                    Таймлайн недоступен для этого клипа.
                  </div>
                )}
              </section>

              {/* ── вырезать слова ── */}
              <section className="space-y-2.5">
                <div className="flex items-center justify-between">
                  <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted">
                    <Type className="size-3.5" />
                    Вырезать слова
                  </p>
                  {selected.size > 0 && (
                    <button
                      onClick={() => setSelected(new Set())}
                      className="text-xs text-muted transition-colors hover:text-ink"
                    >
                      Сбросить
                    </button>
                  )}
                </div>

                <div className="flex max-h-48 flex-wrap gap-1 overflow-y-auto rounded-xl border border-line bg-surface-2 p-2.5">
                  {words.map((w, i) => (
                    <button
                      key={i}
                      disabled={busy}
                      onClick={() => toggleWord(i)}
                      title={`${w.start.toFixed(1)}s – ${w.end.toFixed(1)}s`}
                      className={[
                        "select-none rounded-md px-2 py-1 text-xs transition-all",
                        selected.has(i)
                          ? "bg-red-500/20 text-red-400 line-through ring-1 ring-red-500/40"
                          : "bg-surface text-ink hover:ring-1 hover:ring-line",
                      ].join(" ")}
                    >
                      {w.text}
                    </button>
                  ))}
                  {words.length === 0 && <span className="py-1 text-xs text-muted">Нет слов</span>}
                </div>

                {selected.size > 0 ? (
                  <p className="text-xs text-red-400">
                    {selected.size} слов будет вырезано из клипа
                  </p>
                ) : (
                  <p className="text-xs text-muted">Нажми на слово, чтобы отметить его на вырез.</p>
                )}

                <button
                  disabled={busy || selected.size === 0}
                  onClick={handleTrim}
                  className="flex w-full items-center justify-center gap-2 rounded-xl bg-red-600/80 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-red-600 disabled:cursor-not-allowed disabled:opacity-30"
                >
                  {phase === "saving" ? (
                    <>
                      <Loader2 className="size-4 animate-spin" /> Сохраняю…
                    </>
                  ) : (
                    <>
                      <Scissors className="size-4" /> Вырезать{" "}
                      {selected.size > 0 ? `(${selected.size} слов)` : ""}
                    </>
                  )}
                </button>
              </section>

              {/* ── рендер ── */}
              <section className="mt-auto space-y-2.5 border-t border-line pt-5">
                <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted">
                  <Film className="size-3.5" />
                  Рендер с правками
                </p>

                {phase === "done" ? (
                  <div className="flex items-center gap-2 rounded-xl bg-green-900/30 px-4 py-3 text-sm text-green-400">
                    <CheckCircle className="size-5 shrink-0" />
                    <span>Готово — видео обновилось.</span>
                  </div>
                ) : phase === "rendering" ? (
                  <div className="rounded-xl border border-accent/20 bg-accent/5 px-4 py-3">
                    <div className="flex items-center gap-2 text-sm text-accent">
                      <Loader2 className="size-4 animate-spin" />
                      <span>Рендеринг… {renderElapsed}s</span>
                    </div>
                    <p className="mt-1 text-xs text-muted">
                      Обычно 10–30 секунд. Видео обновится автоматически.
                    </p>
                  </div>
                ) : (
                  <>
                    <p className="text-xs leading-snug text-muted">
                      Клип перерендерится с вырезками, стилем и правками субтитров. Видео слева
                      обновится автоматически.
                    </p>
                    <button
                      disabled={busy}
                      onClick={handleRender}
                      className="flex w-full items-center justify-center gap-2 rounded-xl bg-accent py-3 text-sm font-semibold text-white transition-colors hover:bg-accent-2 disabled:opacity-30"
                    >
                      <Film className="size-4" />
                      Рендерить клип
                    </button>
                  </>
                )}
              </section>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
