"use client";

import {
  ArrowDown,
  ArrowUp,
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
  getClipAss,
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
import { LibassLayer } from "./LibassLayer";
import { PresetStrip } from "./PresetStrip";
import TimelineEditor from "./TimelineEditor";

// ────────────────────────────────────────────────────────────────────────────
// ClipEditorModal — широкая модалка-редактор клипа (WYSIWYG-превью).
// ЛЕВО: видео = ИСТОЧНИК (source.mp4), перемотанный на текущий интервал (луп),
//   в 9:16-контейнере (cover, центр-кроп) + libass.wasm рисует ТОТ ЖЕ ASS, что
//   жжёт ffmpeg на экспорте (превью субтитров = экспорт пиксель-в-пиксель).
//   Фолбэк: если libass не поднялся — старый CSS-CaptionOverlay (не белый экран).
// ПРАВО: широкий таймлайн «Момент на видео» + вырезание слов + рендер.
// Двигаешь блок на таймлайне → меняется интервал → видео едет на новый момент.
// ────────────────────────────────────────────────────────────────────────────

interface ClipEditorModalProps {
  jobId: string;
  clipId: string;
  clip: ClipOut;
  onClose: () => void;
  onRenderDone: (url: string) => void;
}

type Phase = "loading" | "ready" | "saving" | "rendering" | "done" | "error";

/** Клип-временной диапазон активной реплики (в секундах, 0-based от outerStart). */
interface ReplyRange {
  replyIndex: number;
  startSec: number;
  endSec: number;
}

/**
 * Клип-времена реплик из edit-state. reply[i] позиционно покрывает
 * words[offset .. offset+word_refs.length] (зеркало backend compile_ass /
 * CaptionOverlay.buildPagesFromReplies). Скрытые/пустые НЕ кликабельны, но
 * всё равно сдвигают offset (иначе позиционное соответствие слов поедет).
 * Клип-время = source-время слова − outerStart (один интервал).
 */
function buildReplyRanges(
  replies: CaptionReply[],
  words: Word[],
  outerStart: number,
): ReplyRange[] {
  const ranges: ReplyRange[] = [];
  let offset = 0;
  for (let i = 0; i < replies.length; i++) {
    const reply = replies[i];
    const count = reply.word_refs.length;
    const group = words.slice(offset, offset + count);
    offset += count;
    if (reply.hidden || count === 0 || group.length === 0) continue;
    ranges.push({
      replyIndex: i,
      startSec: Math.max(0, group[0].start - outerStart),
      endSec: Math.max(0, group[group.length - 1].end - outerStart),
    });
  }
  return ranges;
}

/**
 * Текст слов реплики (оригинал) — для начального значения textarea и сравнения
 * «правка == оригинал → снять override». reply[i] покрывает words[offset..].
 */
function originalReplyText(
  replies: CaptionReply[],
  words: Word[],
  replyIndex: number,
): string {
  let offset = 0;
  for (let i = 0; i < replies.length; i++) {
    const count = replies[i].word_refs.length;
    if (i === replyIndex) {
      return words
        .slice(offset, offset + count)
        .map((w) => w.text)
        .join(" ");
    }
    offset += count;
  }
  return "";
}

export default function ClipEditorModal({
  jobId,
  clipId,
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

  // ── WYSIWYG-превью ──
  const [assText, setAssText] = useState<string>("");
  const [libassFailed, setLibassFailed] = useState(false);
  // активная реплика для inline-правки текста (хит-зона над canvas)
  const [editingReply, setEditingReply] = useState<number | null>(null);
  const [draft, setDraft] = useState("");
  const [nowSec, setNowSec] = useState(0); // currentTime видео (для выбора активной реплики)

  const videoRef = useRef<HTMLVideoElement>(null);
  const presetRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Превью-видео = ИСТОЧНИК (не отрендеренный клип). Кроп 9:16 — CSS (центр).
  const sourceSrc = useMemo(() => resolveUrl(`media/${jobId}/source.mp4`), [jobId]);

  // Границы текущего интервала клипа в source-времени (для seek/лупа/timeOffset).
  const outerStart = edit?.source_intervals[0]?.source_start ?? 0;
  const outerEnd =
    edit?.source_intervals[edit.source_intervals.length - 1]?.source_end ?? 0;

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

  // ── Esc закрывает модалку (но не когда правим текст субтитра — там Esc = отмена) ──
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && editingReply === null) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, editingReply]);

  // ── общий хелпер: перезапрос ASS после любой правки субтитров/стиля/интервала ──
  const refreshAss = useCallback(async () => {
    try {
      const ass = await getClipAss(jobId, clipId);
      setAssText(ass);
    } catch (e) {
      setError(`Не удалось обновить превью субтитров: ${String(e)}`);
    }
  }, [jobId, clipId]);

  // ── загрузка edit-state + analysis + ASS, timeline отдельно/не-фатально ──
  useEffect(() => {
    let cancelled = false;
    async function fetchData() {
      setPhase("loading");
      setError(null);
      setSelected(new Set());
      setActivePresetId(null);
      setLibassFailed(false);
      try {
        const [editData, analysisData, ass] = await Promise.all([
          getClipEdit(jobId, clipId),
          getClipAnalysis(jobId, clipId),
          getClipAss(jobId, clipId).catch(() => ""),
        ]);
        if (cancelled) return;
        setEdit(editData);
        setWords(analysisData.words);
        setGlobalIndices((editData.captions.replies ?? []).flatMap((r) => r.word_refs));
        setAssText(ass);
        if (!ass) setError("Не удалось загрузить субтитры превью — показываю CSS-фолбэк.");
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

  // ── перемотка источника на момент клипа + луп в границах интервала ──
  // Слушаем сам video-элемент: loadedmetadata → seek на outerStart; timeupdate →
  // луп если вышли за [outerStart, outerEnd). Реагируем на смену интервала
  // (outerStart/outerEnd в deps) → видео едет на новый момент.
  useEffect(() => {
    const video = videoRef.current;
    if (!video || phase === "loading" || phase === "error") return;
    if (outerEnd <= outerStart) return;

    const seekToStart = () => {
      // только если реально вне окна — иначе сбивали бы плавное воспроизведение
      if (video.currentTime < outerStart || video.currentTime >= outerEnd) {
        try {
          video.currentTime = outerStart;
        } catch {
          /* до loadedmetadata seek может бросить — onLoaded повторит */
        }
      }
    };
    const onLoaded = () => {
      try {
        video.currentTime = outerStart;
      } catch {
        /* noop */
      }
    };
    const onTimeUpdate = () => {
      setNowSec(video.currentTime);
      if (video.currentTime >= outerEnd || video.currentTime < outerStart - 0.3) {
        seekToStart();
      }
    };

    // если метаданные уже есть (readyState>=1) — сразу seek
    if (video.readyState >= 1) onLoaded();
    video.addEventListener("loadedmetadata", onLoaded);
    video.addEventListener("timeupdate", onTimeUpdate);
    return () => {
      video.removeEventListener("loadedmetadata", onLoaded);
      video.removeEventListener("timeupdate", onTimeUpdate);
    };
  }, [outerStart, outerEnd, phase]);

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

  // ── refetch analysis + ASS после любого изменения интервалов (trim / set-interval) ──
  const refetchAfter = useCallback(
    async (newEdit: ClipEdit) => {
      const analysisData = await getClipAnalysis(jobId, clipId);
      setEdit(newEdit);
      setWords(analysisData.words);
      setGlobalIndices((newEdit.captions.replies ?? []).flatMap((r) => r.word_refs));
      setSelected(new Set());
      setEditingReply(null);
      setPhase("ready");
      await refreshAss();
    },
    [jobId, clipId, refreshAss],
  );

  const handleSetInterval = useCallback(
    async (start: number, end: number) => {
      if (!edit) return;
      setPhase("saving");
      setError(null);
      try {
        const newEdit = await setClipInterval(jobId, clipId, edit.version ?? 1, start, end);
        await refetchAfter(newEdit);
        // reseek видео на новый момент: outerStart изменится → seek-эффект сработает,
        // но подстрахуемся явно (currentTime может уже быть внутри нового окна).
        const video = videoRef.current;
        if (video) {
          try {
            video.currentTime = newEdit.source_intervals[0]?.source_start ?? start;
          } catch {
            /* noop */
          }
        }
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

  // ── inline-правка субтитра (контракт: replyIndex выровнен по replies) ──
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
        await refreshAss();
      } catch (e) {
        const msg = String(e);
        if (msg.includes("conflict") || msg.includes("409")) handleConflict();
        else setError(msg);
      }
    },
    [edit, jobId, clipId, handleConflict, refreshAss],
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
        await refreshAss();
      } catch (e) {
        const msg = String(e);
        if (msg.includes("conflict") || msg.includes("409")) handleConflict();
        else setError(msg);
      }
    },
    [edit, jobId, clipId, handleConflict, refreshAss],
  );

  const handleStyleClick = useCallback(() => {
    presetRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, []);

  const handlePresetApplied = useCallback(
    (updated: ClipEdit, presetId: string) => {
      setEdit(updated);
      setActivePresetId(presetId);
      void refreshAss();
    },
    [refreshAss],
  );

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

  // ── клип-времена реплик + активная реплика по текущему времени видео ──
  const replyRanges = useMemo(() => {
    const replies = edit?.captions.replies ?? [];
    if (replies.length === 0 || words.length === 0) return [];
    return buildReplyRanges(replies, words, outerStart);
  }, [edit, words, outerStart]);

  const activeReplyIndex = useMemo(() => {
    if (replyRanges.length === 0) return null;
    const clipNow = nowSec - outerStart;
    // внутри диапазона реплики
    for (const r of replyRanges) {
      if (clipNow >= r.startSec && clipNow <= r.endSec) return r.replyIndex;
    }
    // в паузе между репликами → ближайшая прошедшая
    let prev: number | null = null;
    for (const r of replyRanges) {
      if (r.startSec <= clipNow) prev = r.replyIndex;
      else break;
    }
    // до первой реплики → первая
    return prev ?? replyRanges[0].replyIndex;
  }, [replyRanges, nowSec, outerStart]);

  // фокус на textarea при входе в правку
  useEffect(() => {
    if (editingReply !== null && textareaRef.current) {
      textareaRef.current.focus();
      textareaRef.current.select();
    }
  }, [editingReply]);

  const openReplyEdit = useCallback(() => {
    if (activeReplyIndex === null || !edit) return;
    const replies = edit.captions.replies ?? [];
    const reply = replies[activeReplyIndex];
    const original = originalReplyText(replies, words, activeReplyIndex);
    setDraft(reply?.text_override ?? original);
    setEditingReply(activeReplyIndex);
  }, [activeReplyIndex, edit, words]);

  const commitReplyEdit = useCallback(() => {
    if (editingReply === null || !edit) return;
    const idx = editingReply;
    const original = originalReplyText(edit.captions.replies ?? [], words, idx);
    const trimmed = draft.trim();
    setEditingReply(null);
    // пустой или равный оригиналу → снять override (null)
    void handleCaptionsChange(idx, trimmed && trimmed !== original ? trimmed : null);
  }, [editingReply, edit, words, draft, handleCaptionsChange]);

  const cancelReplyEdit = useCallback(() => setEditingReply(null), []);

  const busy = phase === "saving" || phase === "rendering";
  const totalSec = edit
    ? edit.source_intervals.reduce((s, iv) => s + (iv.source_end - iv.source_start), 0)
    : 0;
  const cutCount = edit ? edit.source_intervals.length - 1 : 0;
  const replies = edit?.captions.replies ?? null;
  const marginV = edit?.captions.style.margin_v ?? 260;
  // libass показываем когда ASS есть и инициализация не упала; иначе CSS-фолбэк
  const useLibass = !!assText && !libassFailed;

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
              {/* 9:16 контейнер: видео-источник (cover-кроп по центру) + libass canvas + хит-зона */}
              <div className="relative aspect-[9/16] w-full overflow-hidden rounded-xl border border-line bg-black">
                <video
                  ref={videoRef}
                  key={sourceSrc}
                  src={sourceSrc}
                  controls
                  playsInline
                  preload="auto"
                  className="absolute inset-0 size-full bg-black object-cover [object-position:center]"
                />

                {/* субтитры: libass (точно как экспорт) ИЛИ CSS-фолбэк */}
                {useLibass ? (
                  <LibassLayer
                    videoRef={videoRef}
                    assText={assText}
                    sourceStart={outerStart}
                    onError={() => setLibassFailed(true)}
                  />
                ) : (
                  words.length > 0 &&
                  edit && (
                    <CaptionOverlay
                      editing
                      words={words}
                      clipStart={outerStart}
                      videoRef={videoRef}
                      replies={replies}
                      style={edit.captions.style}
                      highlight={edit.captions.highlight}
                      onCaptionsChange={handleCaptionsChange}
                      onMarginChange={handleMarginChange}
                      onStyleClick={handleStyleClick}
                    />
                  )
                )}

                {/* хит-зона правки субтитра поверх libass-canvas (canvas не кликается).
                    Только когда libass активен — у CSS-фолбэка свой клик. */}
                {useLibass && edit && replyRanges.length > 0 && editingReply === null && (
                  <button
                    type="button"
                    aria-label="Редактировать активный субтитр"
                    onClick={openReplyEdit}
                    className="absolute inset-x-0 bottom-0 z-20 h-[28%] w-full cursor-text bg-transparent"
                  />
                )}

                {/* мини-тулбар (двигать субтитр ↑↓ + стиль) — только при libass */}
                {useLibass && edit && editingReply === null && (
                  <div className="absolute left-1/2 top-2 z-30 flex -translate-x-1/2 items-center gap-1">
                    <ToolbarBtn
                      title="Поднять субтитр"
                      onClick={() => handleMarginChange(clampMargin(marginV + 60))}
                    >
                      <ArrowUp className="size-3.5" />
                    </ToolbarBtn>
                    <ToolbarBtn
                      title="Опустить субтитр"
                      onClick={() => handleMarginChange(clampMargin(marginV - 60))}
                    >
                      <ArrowDown className="size-3.5" />
                    </ToolbarBtn>
                    <ToolbarBtn title="Стиль" onClick={handleStyleClick}>
                      <Palette className="size-3.5" />
                    </ToolbarBtn>
                  </div>
                )}

                {/* inline-textarea правки активной реплики */}
                {useLibass && editingReply !== null && (
                  <div className="absolute inset-x-3 bottom-[10%] z-40">
                    <textarea
                      ref={textareaRef}
                      value={draft}
                      onChange={(e) => setDraft(e.target.value)}
                      onBlur={commitReplyEdit}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                          e.preventDefault();
                          commitReplyEdit();
                        } else if (e.key === "Escape") {
                          e.preventDefault();
                          cancelReplyEdit();
                        }
                      }}
                      rows={2}
                      placeholder="Текст субтитра…"
                      className="w-full resize-none rounded-lg border border-accent/60 bg-black/80 p-2 text-center text-sm font-semibold text-white outline-none focus:ring-2 focus:ring-accent/50"
                    />
                    <p className="mt-1 text-center text-[10px] text-white/70">
                      Enter — сохранить · Esc — отмена
                    </p>
                  </div>
                )}
              </div>

              <p className="text-xs leading-snug text-muted">
                {useLibass
                  ? "Клик по субтитру внизу видео — правь текст. ↑↓ — двигают субтитр. Субтитры точно как в экспорте."
                  : "Кликни по субтитру на видео — правь текст. Стрелки ↑↓ — двигают субтитр. Стиль — ниже."}
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
                      Двигаешь блок — видео едет на момент. Субтитры — точно как в экспорте.
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
                      Клип перерендерится с вырезками, стилем и правками субтитров — финальный
                      экспорт совпадёт с превью.
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

function ToolbarBtn({
  children,
  title,
  onClick,
}: {
  children: React.ReactNode;
  title: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      title={title}
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      className="inline-flex size-7 items-center justify-center rounded-md bg-black/70 text-white/90 backdrop-blur transition hover:bg-accent hover:text-white"
    >
      {children}
    </button>
  );
}

// margin_v кламп в разумный safe-диапазон (ASS-единицы, PlayResY=1920).
function clampMargin(m: number): number {
  return Math.max(40, Math.min(900, Math.round(m)));
}
