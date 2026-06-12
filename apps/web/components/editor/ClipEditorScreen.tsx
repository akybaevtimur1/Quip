"use client";

import { Captions, Crop, Loader2, Palette } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  getClipAnalysis,
  getClipAss,
  getClipEdit,
  getJob,
  getRenderStatus,
  getTimeline,
  patchClipEdit,
  setClipInterval,
  setCropOverride,
  startRenderClip,
  trimClip,
} from "@/lib/api";
import type {
  CaptionReply,
  CaptionStyle,
  ClipEdit,
  HighlightStyle,
  TimelineData,
  Word,
} from "@/lib/types";
import { CaptionOverlay } from "../CaptionOverlay";
import { resolveUrl } from "../ClipCard";
import { LibassLayer } from "../LibassLayer";
import { CaptionsTab } from "./CaptionsTab";
import { EditorHeader, type RenderState } from "./EditorHeader";
import { FrameTab } from "./FrameTab";
import { PreviewPlayer } from "./PreviewPlayer";
import { buildReplyRanges, clampMargin, originalReplyText } from "./replyUtils";
import { StyleTab } from "./StyleTab";
import TimelineV2 from "./TimelineV2";

// ────────────────────────────────────────────────────────────────────────────
// ClipEditorScreen — страница-редактор клипа (/edit/[jobId]/[clipId]).
// ЛЕВО: PreviewPlayer (источник на моменте + libass WYSIWYG + он-видео правка
//   и драг позиции субтитров). ПРАВО: табы Субтитры / Стиль / Кадр.
// НИЗ: таймлайн всего видео (двигать/растягивать шортс).
// Возврат: хедер «← Все клипы» → /?job=<id> (deep-link, ничего не теряется).
// ────────────────────────────────────────────────────────────────────────────

type Phase = "loading" | "ready" | "saving" | "error";
type Tab = "captions" | "style" | "frame";

const TABS: { id: Tab; label: string; icon: typeof Captions }[] = [
  { id: "captions", label: "Субтитры", icon: Captions },
  { id: "style", label: "Стиль", icon: Palette },
  { id: "frame", label: "Кадр", icon: Crop },
];

export default function ClipEditorScreen({
  jobId,
  clipId,
}: {
  jobId: string;
  clipId: string;
}) {
  const [phase, setPhase] = useState<Phase>("loading");
  const [error, setError] = useState<string | null>(null);
  const [edit, setEdit] = useState<ClipEdit | null>(null);
  const [words, setWords] = useState<Word[]>([]);
  const [globalIndices, setGlobalIndices] = useState<number[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [loadKey, setLoadKey] = useState(0);
  const [tab, setTab] = useState<Tab>("captions");

  const [timeline, setTimeline] = useState<TimelineData | null>(null);
  const [clipIds, setClipIds] = useState<string[]>([]);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [activePresetId, setActivePresetId] = useState<string | null>(null);

  const [renderState, setRenderState] = useState<RenderState>({ kind: "idle" });
  // есть правки после последнего рендера → юзеру явно видно, что скачивание/результат
  // отстаёт от превью, пока не нажмёт «Рендер» (фидбек фаундера)
  const [dirty, setDirty] = useState(false);

  // ── WYSIWYG-превью ──
  const [assText, setAssText] = useState("");
  const [libassFailed, setLibassFailed] = useState(false);
  const [editingReply, setEditingReply] = useState<number | null>(null);
  const [draft, setDraft] = useState("");
  const [nowSec, setNowSec] = useState(0);
  // драг позиции субтитров: текущая Y-доля гайда (null = не тащим)
  const [dragFrac, setDragFrac] = useState<number | null>(null);

  const videoRef = useRef<HTMLVideoElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const sourceSrc = useMemo(() => resolveUrl(`media/${jobId}/source.mp4`), [jobId]);
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

  // ── общий хелпер: перезапрос ASS после любой правки ──
  // Секвенсирование: быстрые правки подряд → ответы могут прийти не по порядку,
  // устаревший НЕ должен перетирать свежий (иначе субтитры «прыгают» назад).
  const assSeq = useRef(0);
  const refreshAss = useCallback(async () => {
    const seq = ++assSeq.current;
    try {
      const ass = await getClipAss(jobId, clipId);
      if (seq === assSeq.current) setAssText(ass);
    } catch (e) {
      if (seq === assSeq.current)
        setError(`Не удалось обновить превью субтитров: ${String(e)}`);
    }
  }, [jobId, clipId]);

  // ── загрузка: edit + analysis + ASS (фатально), timeline/job (нефатально) ──
  useEffect(() => {
    let cancelled = false;
    async function fetchData() {
      setPhase("loading");
      setError(null);
      setSelected(new Set());
      setActivePresetId(null);
      setLibassFailed(false);
      setEditingReply(null);
      setRenderState({ kind: "idle" });
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
        if (!ass) setError("Не удалось загрузить субтитры превью — показываю упрощённый режим.");
        setPhase("ready");
        getTimeline(jobId)
          .then((t) => !cancelled && setTimeline(t))
          .catch(() => !cancelled && setTimeline(null));
        getJob(jobId)
          .then((job) => {
            if (cancelled) return;
            const ids = (job.clips ?? []).map((c) => c.id);
            setClipIds(ids.length > 0 ? ids : [clipId]);
            const me = (job.clips ?? []).find((c) => c.id === clipId);
            if (me) setDownloadUrl(resolveUrl(me.video_url));
          })
          .catch(() => !cancelled && setClipIds([clipId]));
      } catch (e) {
        if (cancelled) return;
        setError(String(e));
        setPhase("error");
      }
    }
    void fetchData();
    return () => {
      cancelled = true;
      stopPoll();
    };
  }, [jobId, clipId, loadKey, stopPoll]);

  const handleConflict = useCallback(() => {
    setError("Данные обновились — перезагружаю редактор…");
    setLoadKey((k) => k + 1);
  }, []);

  const failOr409 = useCallback(
    (e: unknown) => {
      const msg = String(e);
      if (msg.includes("conflict") || msg.includes("409")) handleConflict();
      else {
        setError(msg);
        setPhase("ready");
      }
    },
    [handleConflict],
  );

  // ── refetch analysis + ASS после изменения интервалов (trim / set-interval) ──
  // АТОМАРНО: и анализ, и НОВЫЙ ASS грузим ДО setState, применяем одним батчем.
  // Иначе между setEdit (новый outerStart) и приездом ASS старые субтитры
  // показываются с новым оффсетом → «не те слова» мигают при драге интервала.
  const refetchAfter = useCallback(
    async (newEdit: ClipEdit) => {
      const seq = ++assSeq.current;
      const [analysisData, ass] = await Promise.all([
        getClipAnalysis(jobId, clipId),
        getClipAss(jobId, clipId).catch(() => null),
      ]);
      setEdit(newEdit);
      setWords(analysisData.words);
      setGlobalIndices((newEdit.captions.replies ?? []).flatMap((r) => r.word_refs));
      setSelected(new Set());
      setEditingReply(null);
      setPhase("ready");
      setDirty(true);
      if (ass !== null && seq === assSeq.current) setAssText(ass);
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
        const video = videoRef.current;
        if (video) {
          try {
            video.currentTime = newEdit.source_intervals[0]?.source_start ?? start;
          } catch {
            /* noop */
          }
        }
      } catch (e) {
        failOr409(e);
      }
    },
    [edit, jobId, clipId, refetchAfter, failOr409],
  );

  const handleTrim = useCallback(async () => {
    if (!edit || selected.size === 0) return;
    const wordIndices = Array.from(selected).map((pos) => globalIndices[pos]);
    setPhase("saving");
    setError(null);
    try {
      const newEdit = await trimClip(jobId, clipId, edit.version ?? 1, wordIndices);
      await refetchAfter(newEdit);
    } catch (e) {
      failOr409(e);
    }
  }, [edit, selected, globalIndices, jobId, clipId, refetchAfter, failOr409]);

  // ── правки субтитров/стиля → PATCH + refetch ASS ──
  const patchCaptions = useCallback(
    async (captions: ClipEdit["captions"]) => {
      if (!edit) return;
      setError(null);
      try {
        const newEdit = await patchClipEdit(jobId, clipId, edit.version ?? 1, captions);
        setEdit(newEdit);
        setDirty(true);
        await refreshAss();
      } catch (e) {
        failOr409(e);
      }
    },
    [edit, jobId, clipId, refreshAss, failOr409],
  );

  const handleCaptionsChange = useCallback(
    (replyIndex: number, text: string | null) => {
      if (!edit) return;
      const replies = (edit.captions.replies ?? []).map(
        (reply, i): CaptionReply =>
          i === replyIndex ? { ...reply, text_override: text } : reply,
      );
      void patchCaptions({ ...edit.captions, replies });
    },
    [edit, patchCaptions],
  );

  const handleStyleChange = useCallback(
    (patch: Partial<CaptionStyle>) => {
      if (!edit) return;
      setActivePresetId(null); // кастомизация поверх пресета — пресет больше не «чистый»
      void patchCaptions({
        ...edit.captions,
        style: { ...edit.captions.style, ...patch },
      });
    },
    [edit, patchCaptions],
  );

  const handleHighlightChange = useCallback(
    (patch: Partial<HighlightStyle> | null) => {
      if (!edit) return;
      setActivePresetId(null);
      const prev = edit.captions.highlight ?? null;
      const next =
        patch === null
          ? null
          : {
              color: "#FFE000",
              scale: 1.0,
              box: false,
              animation: "karaoke_fill" as const,
              ...(prev ?? {}),
              ...patch,
            };
      void patchCaptions({ ...edit.captions, highlight: next });
    },
    [edit, patchCaptions],
  );

  const handleMarginChange = useCallback(
    (marginV: number) => {
      if (!edit) return;
      void patchCaptions({
        ...edit.captions,
        style: { ...edit.captions.style, margin_v: clampMargin(marginV) },
      });
    },
    [edit, patchCaptions],
  );

  const handlePresetApplied = useCallback(
    (updated: ClipEdit, presetId: string) => {
      setEdit(updated);
      setActivePresetId(presetId);
      setDirty(true);
      void refreshAss();
    },
    [refreshAss],
  );

  // ── кадр (таб «Кадр») ──
  const handleFrameApply = useCallback(
    async (
      mode: "auto" | "fill" | "fit" | "split",
      center: number | null,
      centerB: number | null,
    ) => {
      if (!edit) return;
      setError(null);
      try {
        const newEdit = await setCropOverride(jobId, clipId, edit.version ?? 1, {
          source_start: outerStart,
          source_end: outerEnd,
          mode,
          center,
          center_b: centerB,
        });
        setEdit(newEdit);
        setDirty(true);
      } catch (e) {
        failOr409(e);
      }
    },
    [edit, jobId, clipId, outerStart, outerEnd, failOr409],
  );

  // ── рендер ──
  const handleRender = useCallback(async () => {
    if (!edit) return;
    setError(null);
    stopPoll();
    try {
      await startRenderClip(jobId, clipId);
    } catch (e) {
      setError(String(e));
      return;
    }
    setRenderState({ kind: "rendering", elapsed: 0 });
    timerRef.current = setInterval(
      () =>
        setRenderState((s) =>
          s.kind === "rendering" ? { kind: "rendering", elapsed: s.elapsed + 1 } : s,
        ),
      1000,
    );
    pollRef.current = setInterval(async () => {
      try {
        const st = await getRenderStatus(jobId, clipId);
        if (st.status === "done" && st.video_url) {
          stopPoll();
          setRenderState({ kind: "done" });
          setDirty(false); // рендер догнал правки
          setDownloadUrl(resolveUrl(st.video_url));
        } else if (st.status === "failed") {
          stopPoll();
          setRenderState({ kind: "idle" });
          setError(st.error ?? "Рендер не удался");
        }
      } catch {
        /* keep polling */
      }
    }, 2000);
  }, [edit, jobId, clipId, stopPoll]);

  // ── активная реплика по текущему времени видео ──
  const replyRanges = useMemo(() => {
    const replies = edit?.captions.replies ?? [];
    if (replies.length === 0 || words.length === 0) return [];
    return buildReplyRanges(replies, words, outerStart);
  }, [edit, words, outerStart]);

  const activeReplyIndex = useMemo(() => {
    if (replyRanges.length === 0) return null;
    const clipNow = nowSec - outerStart;
    for (const r of replyRanges) {
      if (clipNow >= r.startSec && clipNow <= r.endSec) return r.replyIndex;
    }
    let prev: number | null = null;
    for (const r of replyRanges) {
      if (r.startSec <= clipNow) prev = r.replyIndex;
      else break;
    }
    return prev ?? replyRanges[0].replyIndex;
  }, [replyRanges, nowSec, outerStart]);

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
    videoRef.current?.pause(); // правим на паузе — текст не убегает
  }, [activeReplyIndex, edit, words]);

  const commitReplyEdit = useCallback(() => {
    if (editingReply === null || !edit) return;
    const idx = editingReply;
    const original = originalReplyText(edit.captions.replies ?? [], words, idx);
    const trimmed = draft.trim();
    setEditingReply(null);
    handleCaptionsChange(idx, trimmed && trimmed !== original ? trimmed : null);
  }, [editingReply, edit, words, draft, handleCaptionsChange]);

  const seekToReply = useCallback(
    (replyIndex: number) => {
      const range = replyRanges.find((r) => r.replyIndex === replyIndex);
      const video = videoRef.current;
      if (!range || !video) return;
      try {
        video.currentTime = outerStart + range.startSec;
      } catch {
        /* noop */
      }
    },
    [replyRanges, outerStart],
  );

  // ── драг субтитров по видео: клик = правка, увод по Y = позиция ──
  const dragRef = useRef<{ startY: number; moved: boolean; boxH: number; boxTop: number } | null>(
    null,
  );
  const onHitPointerDown = useCallback((e: React.PointerEvent<HTMLButtonElement>) => {
    const box = (e.currentTarget.offsetParent as HTMLElement | null)?.getBoundingClientRect();
    if (!box) return;
    dragRef.current = { startY: e.clientY, moved: false, boxH: box.height, boxTop: box.top };
    e.currentTarget.setPointerCapture(e.pointerId);
  }, []);
  const onHitPointerMove = useCallback((e: React.PointerEvent<HTMLButtonElement>) => {
    const d = dragRef.current;
    if (!d) return;
    if (!d.moved && Math.abs(e.clientY - d.startY) < 6) return;
    d.moved = true;
    const frac = Math.min(1, Math.max(0, (e.clientY - d.boxTop) / d.boxH));
    setDragFrac(frac);
  }, []);
  const onHitPointerUp = useCallback(
    (e: React.PointerEvent<HTMLButtonElement>) => {
      const d = dragRef.current;
      dragRef.current = null;
      setDragFrac(null);
      if (!d) return;
      if (!d.moved) {
        openReplyEdit();
        return;
      }
      const frac = Math.min(1, Math.max(0, (e.clientY - d.boxTop) / d.boxH));
      // позиция указателя = базлайн субтитров: margin_v отсчитывается от низа (PlayResY=1920)
      handleMarginChange(Math.round((1 - frac) * 1920));
    },
    [openReplyEdit, handleMarginChange],
  );

  const busy = phase === "saving" || renderState.kind === "rendering";
  const totalSec = edit
    ? edit.source_intervals.reduce((s, iv) => s + (iv.source_end - iv.source_start), 0)
    : 0;
  const useLibass = !!assText && !libassFailed;

  // ── error / loading экраны ──
  if (phase === "error" && !edit) {
    return (
      <div className="flex h-dvh flex-col items-center justify-center gap-4 bg-bg text-center">
        <p className="max-w-md text-sm text-red-400">{error}</p>
        <div className="flex gap-2">
          <button
            onClick={() => setLoadKey((k) => k + 1)}
            className="rounded-lg border border-line px-4 py-2 text-sm text-muted transition hover:text-ink"
          >
            Попробовать снова
          </button>
          <a
            href={`/?job=${jobId}`}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white transition hover:bg-accent-2"
          >
            ← Все клипы
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="grid h-dvh grid-rows-[auto_minmax(0,1fr)_auto] bg-bg">
      <EditorHeader
        jobId={jobId}
        clipId={clipId}
        clipIds={clipIds}
        totalSec={totalSec}
        downloadUrl={downloadUrl}
        renderState={renderState}
        busy={busy}
        dirty={dirty}
        onRender={handleRender}
      />

      {/* ── error banner ── */}
      {error && phase !== "error" && (
        <div className="absolute left-1/2 top-16 z-50 -translate-x-1/2 rounded-xl border border-red-900/50 bg-red-950/90 px-4 py-2 text-sm text-red-300 shadow-lg backdrop-blur">
          {error}
          <button
            onClick={() => setError(null)}
            className="ml-3 text-red-400 transition hover:text-red-200"
          >
            ✕
          </button>
        </div>
      )}

      {/* ── main: превью + панель ── */}
      {phase === "loading" ? (
        <div className="flex items-center justify-center gap-2 text-sm text-muted">
          <Loader2 className="size-4 animate-spin" />
          Загружаю редактор…
        </div>
      ) : (
        <main className="grid min-h-0 grid-cols-1 gap-4 p-4 lg:grid-cols-[minmax(280px,380px)_minmax(0,1fr)]">
          {/* ЛЕВО: превью */}
          <div className="flex min-h-0 items-start justify-center">
            <div className="h-full max-h-full">
              <div className="mx-auto aspect-[9/16] h-full max-h-full">
                <PreviewPlayer
                  src={sourceSrc}
                  outerStart={outerStart}
                  outerEnd={outerEnd}
                  videoRef={videoRef}
                  onTimeChange={setNowSec}
                >
                  {/* субтитры: libass (пиксель-в-пиксель как экспорт) ИЛИ CSS-фолбэк */}
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
                        replies={edit.captions.replies}
                        style={edit.captions.style}
                        highlight={edit.captions.highlight}
                        onCaptionsChange={handleCaptionsChange}
                        onMarginChange={handleMarginChange}
                      />
                    )
                  )}

                  {/* видимый бейдж деградации (не тихий фолбэк) */}
                  {!useLibass && (
                    <span className="absolute left-2 top-2 z-30 rounded bg-amber-600/85 px-1.5 py-0.5 text-[10px] font-semibold text-white">
                      упрощённое превью
                    </span>
                  )}

                  {/* хит-зона: клик = правка активной реплики, драг по Y = позиция */}
                  {useLibass && edit && replyRanges.length > 0 && editingReply === null && (
                    <button
                      type="button"
                      aria-label="Субтитры: клик — правка текста, перетаскивание — позиция"
                      onPointerDown={onHitPointerDown}
                      onPointerMove={onHitPointerMove}
                      onPointerUp={onHitPointerUp}
                      className="absolute inset-x-0 bottom-0 z-20 h-[30%] w-full cursor-grab touch-none bg-transparent active:cursor-grabbing"
                    />
                  )}

                  {/* гайд-линия при драге позиции */}
                  {dragFrac !== null && (
                    <div
                      className="pointer-events-none absolute inset-x-0 z-40"
                      style={{ top: `${dragFrac * 100}%` }}
                    >
                      <div className="h-px w-full bg-accent shadow-[0_0_8px_rgba(255,90,61,0.9)]" />
                      <span className="absolute right-2 top-1 rounded bg-accent px-1.5 py-0.5 font-mono text-[10px] text-white">
                        позиция субтитров
                      </span>
                    </div>
                  )}

                  {/* inline-textarea правки активной реплики НА ВИДЕО */}
                  {useLibass && editingReply !== null && (
                    <div className="absolute inset-x-3 bottom-[12%] z-40">
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
                            setEditingReply(null);
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
                </PreviewPlayer>
              </div>
            </div>
          </div>

          {/* ПРАВО: табы */}
          <div className="flex min-h-0 flex-col gap-3">
            <div className="flex shrink-0 gap-1 rounded-xl border border-line bg-surface p-1">
              {TABS.map(({ id, label, icon: Icon }) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => setTab(id)}
                  className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-sm font-semibold transition ${
                    tab === id
                      ? "bg-accent/15 text-accent"
                      : "text-muted hover:bg-surface-2 hover:text-ink"
                  }`}
                >
                  <Icon className="size-4" />
                  {label}
                </button>
              ))}
            </div>

            <div className="flex min-h-0 flex-1 flex-col rounded-xl border border-line bg-surface p-4">
              {edit && tab === "captions" && (
                <CaptionsTab
                  words={words}
                  replies={edit.captions.replies ?? []}
                  activeReplyIndex={activeReplyIndex}
                  selected={selected}
                  busy={busy}
                  saving={phase === "saving"}
                  onToggleWord={(pos) =>
                    setSelected((prev) => {
                      const next = new Set(prev);
                      if (next.has(pos)) next.delete(pos);
                      else next.add(pos);
                      return next;
                    })
                  }
                  onClearSelected={() => setSelected(new Set())}
                  onTrim={handleTrim}
                  onReplyTextChange={handleCaptionsChange}
                  onSeekReply={seekToReply}
                />
              )}
              {edit && tab === "style" && (
                <StyleTab
                  jobId={jobId}
                  clipId={clipId}
                  edit={edit}
                  activePresetId={activePresetId}
                  busy={busy}
                  onPresetApplied={handlePresetApplied}
                  onConflict={handleConflict}
                  onError={setError}
                  onStyleChange={handleStyleChange}
                  onHighlightChange={handleHighlightChange}
                />
              )}
              {edit && tab === "frame" && (
                <FrameTab
                  edit={edit}
                  outerStart={outerStart}
                  outerEnd={outerEnd}
                  busy={busy}
                  onApply={handleFrameApply}
                />
              )}
            </div>
          </div>
        </main>
      )}

      {/* ── НИЗ: таймлайн всего видео ── */}
      <footer className="shrink-0 border-t border-line bg-surface px-4 py-3">
        {timeline && edit ? (
          <TimelineV2
            jobId={jobId}
            clipId={clipId}
            version={edit.version ?? 1}
            data={timeline}
            interval={{ source_start: outerStart, source_end: outerEnd }}
            busy={phase === "saving"}
            onIntervalChange={handleSetInterval}
          />
        ) : (
          <div className="rounded-xl border border-dashed border-line bg-surface-2 px-4 py-5 text-center text-xs text-muted">
            {phase === "loading" ? "Загружаю таймлайн…" : "Таймлайн недоступен для этого клипа."}
          </div>
        )}
      </footer>
    </div>
  );
}
