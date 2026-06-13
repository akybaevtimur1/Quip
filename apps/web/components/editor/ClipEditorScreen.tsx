"use client";

import { Captions, Crop, Loader2, Palette, Type } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  type Aspect,
  applyPreset,
  getClipAnalysis,
  getClipAss,
  getClipEdit,
  getJob,
  getRenderStatus,
  getTimeline,
  patchClipEdit,
  setClipAspect,
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
  HookOverlay,
  TimelineData,
  Word,
} from "@/lib/types";
import { CaptionOverlay } from "../CaptionOverlay";
import { resolveUrl } from "../ClipCard";
import { LibassLayer } from "../LibassLayer";
import { CaptionsTab } from "./CaptionsTab";
import { EditorHeader, type RenderState } from "./EditorHeader";
import { FrameTab } from "./FrameTab";
import { HookTab } from "./HookTab";
import { type FrameState, PreviewPlayer } from "./PreviewPlayer";
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
type Tab = "captions" | "hook" | "style" | "frame";

/** Регион reframe-плана пайплайна (reframe_<clip>.json), клип-время. */
interface RawRegion {
  t0: number;
  t1: number;
  mode: string;
  points: { t: number; cx: number | null }[];
  points_b?: { t: number; cx: number | null }[];
}

function cxAt(points: { t: number; cx: number | null }[] | undefined, clipT: number): number {
  if (!points || points.length === 0) return 0.5;
  let cx = points[0].cx ?? 0.5;
  for (const p of points) {
    if (p.t <= clipT && p.cx !== null) cx = p.cx;
    if (p.t > clipT) break;
  }
  return cx;
}

const TABS: { id: Tab; label: string; icon: typeof Captions }[] = [
  { id: "captions", label: "Субтитры", icon: Captions },
  { id: "hook", label: "Хук", icon: Type },
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
  const [loadKey, setLoadKey] = useState(0);
  const [tab, setTab] = useState<Tab>("captions");

  const [timeline, setTimeline] = useState<TimelineData | null>(null);
  const [clipIds, setClipIds] = useState<string[]>([]);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [activePresetId, setActivePresetId] = useState<string | null>(null);
  // reframe-план пайплайна (для честного превью кадра) + исходный старт сегмента
  const [rawRegions, setRawRegions] = useState<RawRegion[] | null>(null);
  const [origStart, setOrigStart] = useState<number | null>(null);

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
      setActivePresetId(null);
      setLibassFailed(false);
      setEditingReply(null);
      setRenderState({ kind: "idle" });
      setRawRegions(null);
      setOrigStart(null);
      // Авто-ретрай с backoff: воркер мог ещё подниматься (cold start torch/MediaPipe)
      // или сетевой блип на первом запросе → не показываем ошибку сразу, тихо повторяем.
      const MAX_ATTEMPTS = 4;
      for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
        try {
          const [editData, analysisData, ass] = await Promise.all([
            getClipEdit(jobId, clipId),
            getClipAnalysis(jobId, clipId),
            getClipAss(jobId, clipId).catch(() => ""),
          ]);
          if (cancelled) return;
          setEdit(editData);
          setWords(analysisData.words);
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
              if (me) {
                setDownloadUrl(resolveUrl(me.video_url));
                setOrigStart(me.start);
              }
            })
            .catch(() => !cancelled && setClipIds([clipId]));
          // план кадра пайплайна (нефатально): превью уважает реальные режимы fit/fill/split
          fetch(resolveUrl(`media/${jobId}/reframe_${clipId}.json`), { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((data) => {
              if (!cancelled) setRawRegions((data?.regions as RawRegion[]) ?? null);
            })
            .catch(() => !cancelled && setRawRegions(null));
          return; // успех
        } catch (e) {
          if (cancelled) return;
          if (attempt < MAX_ATTEMPTS - 1) {
            await new Promise((r) => setTimeout(r, 600 * (attempt + 1)));
            if (cancelled) return;
            continue; // повторяем (воркер ещё поднимается)
          }
          setError(String(e));
          setPhase("error");
        }
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

  const handleCutReply = useCallback(
    async (replyIndex: number) => {
      if (!edit) return;
      const reply = (edit.captions.replies ?? [])[replyIndex];
      if (!reply || reply.word_refs.length === 0) return;
      setPhase("saving");
      setError(null);
      try {
        const newEdit = await trimClip(jobId, clipId, edit.version ?? 1, reply.word_refs);
        await refetchAfter(newEdit);
      } catch (e) {
        failOr409(e);
      }
    },
    [edit, jobId, clipId, refetchAfter, failOr409],
  );

  // ── правки субтитров/стиля → PATCH + refetch ASS ──
  // ОЧЕРЕДЬ мутаций: правки на ходу (цвет/анимация/текст во время воспроизведения)
  // могут сыпаться быстрее, чем отвечает сервер. Параллельные PATCH'и со старой
  // версией давали 409 → полный reload редактора. Теперь мутации выполняются
  // строго по одной, каждая берёт СВЕЖИЕ captions/version на момент исполнения.
  const editRef = useRef<ClipEdit | null>(null);
  useEffect(() => {
    editRef.current = edit;
  }, [edit]);
  const patchChain = useRef<Promise<void>>(Promise.resolve());

  const patchCaptions = useCallback(
    (update: (captions: ClipEdit["captions"]) => ClipEdit["captions"]) => {
      patchChain.current = patchChain.current.then(async () => {
        const cur = editRef.current;
        if (!cur) return;
        setError(null);
        try {
          const newEdit = await patchClipEdit(
            jobId,
            clipId,
            cur.version ?? 1,
            update(cur.captions),
          );
          editRef.current = newEdit; // свежая версия доступна СЛЕДУЮЩЕЙ мутации сразу
          setEdit(newEdit);
          setDirty(true);
          await refreshAss();
        } catch (e) {
          failOr409(e);
        }
      });
      return patchChain.current;
    },
    [jobId, clipId, refreshAss, failOr409],
  );

  const handleCaptionsChange = useCallback(
    (replyIndex: number, text: string | null) => {
      void patchCaptions((captions) => ({
        ...captions,
        replies: (captions.replies ?? []).map(
          (reply, i): CaptionReply =>
            i === replyIndex ? { ...reply, text_override: text } : reply,
        ),
      }));
    },
    [patchCaptions],
  );

  const handleStyleChange = useCallback(
    (patch: Partial<CaptionStyle>) => {
      setActivePresetId(null); // кастомизация поверх пресета — пресет больше не «чистый»
      void patchCaptions((captions) => ({
        ...captions,
        style: { ...captions.style, ...patch },
      }));
    },
    [patchCaptions],
  );

  const handleHighlightChange = useCallback(
    (patch: Partial<HighlightStyle> | null) => {
      setActivePresetId(null);
      void patchCaptions((captions) => ({
        ...captions,
        highlight:
          patch === null
            ? null
            : {
                color: "#FF5A3D", // дефолт = коралл пресета A (не жёлтый)
                scale: 1.0,
                box: false,
                animation: "karaoke_fill" as const,
                ...(captions.highlight ?? {}),
                ...patch,
              },
      }));
    },
    [patchCaptions],
  );

  const handleMarginChange = useCallback(
    (marginV: number) => {
      void patchCaptions((captions) => ({
        ...captions,
        style: { ...captions.style, margin_v: clampMargin(marginV) },
      }));
    },
    [patchCaptions],
  );

  // ── burn-тогл (таб «Субтитры», T4 #8): не накладывать наши субтитры ──
  const handleBurnChange = useCallback(
    (burn: boolean) => {
      void patchCaptions((captions) => ({ ...captions, burn }));
    },
    [patchCaptions],
  );

  // ── хук (таб «Хук») → PATCH captions.hook через ту же очередь мутаций ──
  // patch=null → убрать хук; иначе мерж поверх текущего (или нового {text:""}) —
  // опущенные поля дольёт pydantic (шрифт/плашка/размер по дефолту).
  const handleHookChange = useCallback(
    (patch: Partial<HookOverlay> | null) => {
      void patchCaptions((captions) => ({
        ...captions,
        hook: patch === null ? null : { ...(captions.hook ?? { text: "" }), ...patch },
      }));
    },
    [patchCaptions],
  );

  // применение пресета — в ТОЙ ЖЕ очереди мутаций (свежая версия, никаких 409 на ходу)
  const handlePresetApply = useCallback(
    (presetId: string) => {
      patchChain.current = patchChain.current.then(async () => {
        const cur = editRef.current;
        if (!cur) return;
        setError(null);
        try {
          const updated = await applyPreset(jobId, clipId, cur.version ?? 1, presetId);
          editRef.current = updated;
          setEdit(updated);
          setActivePresetId(presetId);
          setDirty(true);
          await refreshAss();
        } catch (e) {
          failOr409(e);
        }
      });
      return patchChain.current;
    },
    [jobId, clipId, refreshAss, failOr409],
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

  // ── соотношение сторон (T5): меняет выход + PlayRes ASS → рефетчим ASS ──
  const handleAspectChange = useCallback(
    async (aspect: Aspect) => {
      if (!edit || edit.aspect === aspect) return;
      setError(null);
      try {
        const newEdit = await setClipAspect(jobId, clipId, edit.version ?? 1, aspect);
        setEdit(newEdit);
        setDirty(true);
        await refreshAss(); // PlayRes изменился → libass перерисует в новом аспекте
      } catch (e) {
        failOr409(e);
      }
    },
    [edit, jobId, clipId, refreshAss, failOr409],
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

  // ── РЕАЛЬНЫЙ режим кадра для превью на текущий момент ──
  // Приоритет: ручной override (таб «Кадр», виден сразу) → план пайплайна
  // (reframe_<clip>.json; валиден пока интервал не сдвинут) → дефолт fill-центр.
  const frame = useMemo<FrameState | null>(() => {
    const ovs = (edit?.reframe_overrides ?? []).filter(
      (ov) => ov.source_start < outerEnd && ov.source_end > outerStart,
    );
    const ov = ovs.at(-1);
    if (ov) {
      const m = ov.mode === "fit" ? "fit" : ov.mode === "split" ? "split" : "fill";
      return {
        mode: m,
        cx: ov.center ?? (m === "split" ? 0.3 : 0.5),
        cxB: ov.center_b ?? 0.7,
      };
    }
    // план пайплайна устаревает, если шортс сдвинули с исходного сегмента
    if (rawRegions && origStart !== null && Math.abs(outerStart - origStart) < 0.5) {
      const clipT = Math.max(0, nowSec - outerStart);
      const reg =
        rawRegions.find((r) => clipT >= r.t0 && clipT < r.t1) ?? rawRegions.at(-1) ?? null;
      if (reg && (reg.mode === "fit" || reg.mode === "split" || reg.mode === "fill")) {
        return {
          mode: reg.mode,
          cx: cxAt(reg.points, clipT),
          cxB: cxAt(reg.points_b, clipT),
        };
      }
    }
    return null;
  }, [edit, outerStart, outerEnd, rawRegions, origStart, nowSec]);

  // T5: аспект превью-контейнера (литералы → Tailwind JIT их видит)
  const aspectClass =
    { "9:16": "aspect-[9/16]", "1:1": "aspect-[1/1]", "4:5": "aspect-[4/5]", "16:9": "aspect-[16/9]" }[
      edit?.aspect ?? "9:16"
    ] ?? "aspect-[9/16]";

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
            href={`/dashboard?job=${jobId}`}
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
          {/* ЛЕВО: превью. Доступная область = ширина колонки × ограниченная высота;
              PreviewPlayer сам contain'ится по aspectClass (w-full + max-h-full + aspect) →
              НЕ распирает страницу на 16:9/1:1/4:5 (баг T5 пофикшен). */}
          <div className="flex min-h-0 items-center justify-center">
            <div className="flex h-[58vh] max-h-full w-full items-center justify-center lg:h-full">
              <PreviewPlayer
                src={sourceSrc}
                outerStart={outerStart}
                outerEnd={outerEnd}
                videoRef={videoRef}
                frame={frame}
                onTimeChange={setNowSec}
                aspectClass={aspectClass}
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

          {/* ПРАВО: табы */}
          <div className="flex min-h-0 flex-col gap-3">
            {/* #1: явно про live-vs-рендер — частый вопрос «надо ли ререндерить» */}
            <p className="shrink-0 rounded-lg border border-line bg-surface-2 px-3 py-1.5 text-[11px] leading-snug text-muted">
              <span className="text-accent">Превью живое</span> — субтитры, хук, стиль и кадр
              видно сразу, рендерить не нужно. Кнопка <span className="font-semibold text-ink">«Рендер»</span> записывает
              правки в скачиваемый файл (мигает жёлтым, когда файл отстал от превью).
            </p>
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
                  busy={busy}
                  burn={edit.captions.burn ?? true}
                  onReplyTextChange={handleCaptionsChange}
                  onCutReply={handleCutReply}
                  onSeekReply={seekToReply}
                  onBurnChange={handleBurnChange}
                />
              )}
              {edit && tab === "hook" && (
                <HookTab edit={edit} busy={busy} onHookChange={handleHookChange} />
              )}
              {edit && tab === "style" && (
                <StyleTab
                  edit={edit}
                  activePresetId={activePresetId}
                  busy={busy}
                  onPresetApply={handlePresetApply}
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
                  onAspectChange={handleAspectChange}
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
            key={clipId}
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
