"use client";

import { Captions, Crop, Loader2, Palette, Type, Wand2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  type Aspect,
  applyPreset,
  getClipAnalysis,
  getClipAss,
  getClipEdit,
  getClipReframe,
  getJob,
  getRenderStatus,
  getTimeline,
  patchClipEdit,
  patchClipEditKeepalive,
  regenerateHook,
  setClipAspect,
  setClipInterval,
  setCropOverride,
  startRenderClip,
  trimClip,
} from "@/lib/api";
import { patchAssStyles } from "@/lib/assStyle";
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
import { AgentTab } from "./AgentTab";
import { CaptionsTab } from "./CaptionsTab";
import { EditorHeader, type RenderState } from "./EditorHeader";
import { FitTimeline } from "./FitTimeline";
import { FrameTab } from "./FrameTab";
import { HookTab } from "./HookTab";
import { OverlaySelectionBox } from "./OverlaySelectionBox";
import type { SubRects } from "@/lib/overlayBox";
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
type Tab = "captions" | "hook" | "style" | "frame" | "agent";

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
  const first = points[0];
  if (clipT <= first.t) return first.cx ?? 0.5;
  // Линейная интерполяция между кейфреймами — как кусочно-линейное cx-выражение ffmpeg
  // в рендере. Раньше тут была СТУПЕНЬКА (держим последний кейфрейм) → превью «прыгало»
  // между разреженными кейфреймами ВНУТРИ плана (где контент непрерывен), хотя реальный
  // рендер плавный. Теперь превью = рендер: камера едет плавно внутри fill-региона.
  for (let i = 1; i < points.length; i++) {
    const p0 = points[i - 1];
    const p1 = points[i];
    if (clipT < p1.t) {
      const c0 = p0.cx ?? 0.5;
      const c1 = p1.cx ?? c0;
      const span = p1.t - p0.t;
      return span > 0 ? c0 + (c1 - c0) * ((clipT - p0.t) / span) : c1;
    }
  }
  return points[points.length - 1].cx ?? 0.5;
}

const TABS: { id: Tab; label: string; icon: typeof Captions }[] = [
  { id: "agent", label: "Agent", icon: Wand2 },
  { id: "captions", label: "Captions", icon: Captions },
  { id: "hook", label: "Hook", icon: Type },
  { id: "style", label: "Style", icon: Palette },
  { id: "frame", label: "Frame", icon: Crop },
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
  // reframe-план для честного превью кадра (D2: от эндпоинта /reframe = единый путь рендера;
  // отражает ТЕКУЩИЕ интервалы → не устаревает после сдвига/трима, и работает на облаке)
  const [rawRegions, setRawRegions] = useState<RawRegion[] | null>(null);

  const [renderState, setRenderState] = useState<RenderState>({ kind: "idle" });
  // есть правки после последнего рендера → юзеру явно видно, что скачивание/результат
  // отстаёт от превью, пока не нажмёт «Рендер» (фидбек фаундера)
  const [dirty, setDirty] = useState(false);
  // есть НЕсохранённые правки (debounce-PATCH ещё не ушёл / в полёте) — индикатор
  // «Сохраняю…/Сохранено» + гарантия flush перед уходом (B-#5, без потери данных).
  const [unsaved, setUnsaved] = useState(false);

  // ── WYSIWYG-превью ──
  const [assText, setAssText] = useState("");
  const [libassFailed, setLibassFailed] = useState(false);
  const [editingReply, setEditingReply] = useState<number | null>(null);
  const [draft, setDraft] = useState("");
  const [nowSec, setNowSec] = useState(0);
  // Драг позиции субтитров/хука НЕ держим в state — гайд-линии двигаются императивно по ref
  // (см. блок «драг субтитров/хука по видео»): иначе ререндер на каждый move = лаги/прыжки.

  const videoRef = useRef<HTMLVideoElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Воркер-эндпоинт: лёгкий preview-прокси (≤720p H.264 faststart, пара МБ) для БЫСТРОЙ загрузки.
  // Бэкенд прозрачно фолбэчит на полный source.mp4 для старых джоб без прокси. На Modal — 302 на
  // CDN (cdn.quip.ink). Превью-кроп — по долям (res-независим), субтитры — libass-оверлей → 720p ок.
  const sourceSrc = useMemo(() => resolveUrl(`jobs/${jobId}/preview.mp4`), [jobId]);
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
  // reframe-план превью: единый путь /reframe (как рендер), отражает текущие интервалы.
  // Нефатально: ошибка/таймаут → null → превью fallback в центр (как было), без поломки.
  const loadReframe = useCallback(async () => {
    try {
      const data = await getClipReframe(jobId, clipId);
      setRawRegions((data.regions as RawRegion[]) ?? null);
    } catch {
      setRawRegions(null);
    }
  }, [jobId, clipId]);

  const assSeq = useRef(0);
  // Optimistic-edit generation: bumped on every editCaptions (instant local patchAssStyles).
  // refreshAss captures it BEFORE its fetch and skips setAssText if a NEWER optimistic edit
  // landed meanwhile — otherwise a refresh that was already in flight when the user changed
  // the font/style resolves with PRE-EDIT server ASS and visibly reverts the change ("font
  // snaps back, have to change it again" — reproduced live: a stale /ass clobbered a newer
  // optimistic font). The next debounced flush issues its own refreshAss and reconciles, so
  // dropping the stale one loses nothing. (A primitive counter — NOT reading editRef into a
  // state setter — keeps the React Compiler immutability rule happy.)
  const optGenRef = useRef(0);
  // refreshAss skips setAssText if a NEWER optimistic edit landed after `gen` — otherwise a
  // refresh in flight (or queued behind a slow PATCH in the mutation chain) resolves with
  // PRE-EDIT server ASS and visibly reverts the change ("font snaps back, change it again").
  // `gen` MUST be the generation of the edit being reconciled (captured at flush time, tied to
  // the flushed captions) — NOT optGenRef read here, which runs AFTER the PATCH and could
  // already include a newer edit (→ it would then wrongly apply the stale ASS). Authoritative
  // callers (preset/agent/aspect) pass no gen → default to current → always apply.
  const refreshAss = useCallback(async (gen: number = optGenRef.current) => {
    const seq = ++assSeq.current;
    try {
      const ass = await getClipAss(jobId, clipId);
      if (seq !== assSeq.current) return; // a newer refreshAss superseded this one
      if (gen !== optGenRef.current) return; // a newer optimistic edit happened → don't clobber
      setAssText(ass);
    } catch (e) {
      if (seq === assSeq.current)
        setError(`Couldn’t refresh caption preview: ${String(e)}`);
    }
  }, [jobId, clipId]);

  // W3: агент изменил edit-state (интервал/хук) на бэке → перечитать edit + ASS-превью.
  // editRef синхронизирует эффект [edit] (тут НЕ мутируем — это не путь мутации-очереди).
  const handleAgentEdited = useCallback(async () => {
    try {
      const fresh = await getClipEdit(jobId, clipId);
      setEdit(fresh);
      await refreshAss();
    } catch {
      /* реконсиляция не критична — следующий poll/действие повторит */
    }
  }, [jobId, clipId, refreshAss]);

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
          if (!ass) setError("Couldn’t load caption preview — showing a simplified mode.");
          setPhase("ready");
          getTimeline(jobId)
            .then((t) => !cancelled && setTimeline(t))
            .catch(() => !cancelled && setTimeline(null));
          getJob(jobId)
            .then((job) => {
              if (cancelled) return;
              // Same order the grid shows (best score first) so "Clip N of M" and the
              // ‹ › nav match what the user clicked — otherwise opening the first card
              // (highest score) showed "Clip 2 of 5". ДЕТЕРМИНИРОВАННЫЙ тай-брейк по id
              // (как в ClipGrid): при равных score порядок не зависит от очерёдности фетча,
              // иначе грид и редактор расходились → «открыл первый — попал в третий».
              const ids = [...(job.clips ?? [])]
                .sort((a, b) => b.score - a.score || a.id.localeCompare(b.id))
                .map((c) => c.id);
              setClipIds(ids.length > 0 ? ids : [clipId]);
              // D1: НЕ берём me.video_url (ЧИСТЫЙ клип без субтитров) как download —
              // downloadUrl остаётся null до рендера → ExportMenu рендерит captioned на лету.
            })
            .catch(() => !cancelled && setClipIds([clipId]));
          // D2: план кадра от эндпоинта /reframe (единый путь рендера, работает и на облаке)
          if (!cancelled) void loadReframe();
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
  }, [jobId, clipId, loadKey, stopPoll, loadReframe]);

  const handleConflict = useCallback(() => {
    setError("Data changed — reloading the editor…");
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

  // editRef = СВЕЖАЯ версия edit-state для очереди мутаций. Синкается эффектом
  // (на каждый render), НО любой путь, который setEdit(newEdit) напрямую (trim/
  // set-interval/frame/aspect), ОБЯЗАН обновить editRef.current ТУТ ЖЕ —
  // эффект отстаёт на коммит, и следующая мутация в очереди прочла бы старую
  // версию → 409 → reload (баг-класс, ради которого очередь и сделана).
  const editRef = useRef<ClipEdit | null>(null);
  useEffect(() => {
    editRef.current = edit;
  }, [edit]);

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
      editRef.current = newEdit; // мутации-очередь читает СВЕЖУЮ версию (иначе 409→reload)
      setEdit(newEdit);
      setWords(analysisData.words);
      setEditingReply(null);
      setPhase("ready");
      setDirty(true);
      if (ass !== null && seq === assSeq.current) setAssText(ass);
      // D2: интервал изменился → пере-считать reframe-план для НОВОГО окна (превью-кроп
      // больше не устаревает после сдвига/трима — эндпоинт отражает текущие интервалы).
      void loadReframe();
    },
    [jobId, clipId, loadReframe],
  );

  // ── правки субтитров/стиля → PATCH + refetch ASS ──
  // ОЧЕРЕДЬ мутаций: правки на ходу (цвет/анимация/текст во время воспроизведения)
  // могут сыпаться быстрее, чем отвечает сервер. Параллельные PATCH'и со старой
  // версией давали 409 → полный reload редактора. Теперь мутации выполняются
  // строго по одной, каждая берёт СВЕЖИЕ captions/version на момент исполнения.
  const patchChain = useRef<Promise<void>>(Promise.resolve());
  // Дебаунс-персист правок субтитров/хука: instant-превью локально (patchAssStyles +
  // оптимистичный edit-state), PATCH на сервер — коалесированно через ~300мс. Сервер
  // остаётся источником правды (refreshAss реконсилит ASS; экспорт всегда из Python-ASS).
  // pendingCaptionsRef = последнее желаемое captions; flushTimerRef = таймер дебаунса.
  const pendingCaptionsRef = useRef<ClipEdit["captions"] | null>(null);
  // Поколение оптимистичной правки, ПРИВЯЗАННОЕ к pendingCaptionsRef (ставится в editCaptions).
  // Захватываем его на момент flush'а и передаём в refreshAss → реконсиляция этой правки
  // пропускается, если после неё пришла более новая (анти-отскок #5, не зависит от тайминга
  // PATCH/очереди мутаций).
  const pendingGenRef = useRef(0);
  const flushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Отправить накопленные captions на сервер (через очередь мутаций) + реконсиляция ASS.
  // ⚠️ НЕ вызывать ИЗНУТРИ patchChain.then (в конце ждёт patchChain.current → дедлок).
  const flushCaptions = useCallback(async () => {
    if (flushTimerRef.current) {
      clearTimeout(flushTimerRef.current);
      flushTimerRef.current = null;
    }
    const captions = pendingCaptionsRef.current;
    const gen = pendingGenRef.current; // поколение ЭТИХ captions (для анти-отскока)
    if (captions !== null) {
      pendingCaptionsRef.current = null;
      patchChain.current = patchChain.current.then(async () => {
        const cur = editRef.current;
        if (!cur) return;
        try {
          const newEdit = await patchClipEdit(jobId, clipId, cur.version ?? 1, captions);
          // Реконсиляция версии/полей, но СОХРАНЯЕМ свежие локальные captions: юзер мог
          // править во время раунд-трипа — нельзя откатывать его правки (баг-класс очереди).
          editRef.current = {
            ...newEdit,
            captions: editRef.current?.captions ?? newEdit.captions,
          };
          setEdit((prev) => (prev ? { ...newEdit, captions: prev.captions } : newEdit));
          setDirty(true);
          // Нет более свежей правки → авторитетный ASS (реконсиляция) + «Сохранено». gen этой
          // правки → refreshAss НЕ перетрёт более новую (даже если PATCH/очередь затянулись).
          if (pendingCaptionsRef.current === null) {
            setUnsaved(false);
            await refreshAss(gen);
          }
        } catch (e) {
          failOr409(e);
        }
      });
    }
    await patchChain.current;
  }, [jobId, clipId, refreshAss, failOr409]);

  const scheduleFlush = useCallback(() => {
    if (flushTimerRef.current) clearTimeout(flushTimerRef.current);
    flushTimerRef.current = setTimeout(() => void flushCaptions(), 300);
  }, [flushCaptions]);

  // Правка субтитров/хука: оптимистичный edit-state + МГНОВЕННЫЙ локальный ASS-патч
  // (patchAssStyles) + дебаунс-персист. Лаги уходят: libass обновляется сразу, PATCH в фоне.
  const editCaptions = useCallback(
    (update: (captions: ClipEdit["captions"]) => ClipEdit["captions"]) => {
      const cur = editRef.current;
      if (!cur) return;
      setError(null);
      const next = update(cur.captions);
      const optimistic = { ...cur, captions: next };
      editRef.current = optimistic;
      setEdit(optimistic);
      // instant: переписать Style-строки локально (цвет/размер/шрифт/контур/плашка/позиция).
      // Правки Dialogue-тегов (анимация/текст/uppercase) добьёт реконсиляция через ~300мс.
      setAssText((prev) => patchAssStyles(prev, next.style, next.highlight, next.hook));
      // новый оптимистичный патч → его поколение; in-flight refreshAss с прежним gen не перетрёт (#5)
      optGenRef.current++;
      pendingGenRef.current = optGenRef.current;
      setDirty(true);
      setUnsaved(true);
      pendingCaptionsRef.current = next;
      scheduleFlush();
    },
    [scheduleFlush],
  );

  // Гарантированный flush ДО операции, бампающей версию (trim/interval/frame/aspect/preset),
  // или ухода со страницы — чтобы накопленные правки субтитров не потерялись (B-#5).
  // Алиас (не useCallback) — flushCaptions уже мемоизирован, обёртка лишь мешала бы React Compiler.
  const flushPending = flushCaptions;

  // ── ДОЛГОВЕЧНОСТЬ (B-#5): дожать pending-правки при уходе со страницы ──
  // pagehide/beforeunload (закрытие/refresh), visibilitychange→hidden (свернул вкладку),
  // и cleanup (SPA-навигация = размонтирование). keepalive-PATCH переживает unload —
  // обычный fetch на unload отменяется и правки тихо теряются (страх фаундера «всё снеслось»).
  useEffect(() => {
    const persistNow = () => {
      const captions = pendingCaptionsRef.current;
      const cur = editRef.current;
      if (captions !== null && cur) {
        pendingCaptionsRef.current = null;
        patchClipEditKeepalive(jobId, clipId, cur.version ?? 1, captions);
      }
    };
    const onHide = () => persistNow();
    const onVis = () => {
      if (document.visibilityState === "hidden") persistNow();
    };
    window.addEventListener("pagehide", onHide);
    window.addEventListener("beforeunload", onHide);
    document.addEventListener("visibilitychange", onVis);
    return () => {
      window.removeEventListener("pagehide", onHide);
      window.removeEventListener("beforeunload", onHide);
      document.removeEventListener("visibilitychange", onVis);
      if (flushTimerRef.current) clearTimeout(flushTimerRef.current);
      persistNow(); // размонтирование (уход из редактора) → keepalive-flush pending
    };
  }, [jobId, clipId]);

  // ── trim / set-interval (таймлайн): сначала flush pending-правок (B-#5), потом версия-bump ──
  const handleSetInterval = useCallback(
    async (start: number, end: number) => {
      if (!edit) return;
      setPhase("saving");
      setError(null);
      try {
        await flushPending(); // персист накопленных правок субтитров ДО смены интервала
        const v = editRef.current?.version ?? edit.version ?? 1;
        const newEdit = await setClipInterval(jobId, clipId, v, start, end);
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
    [edit, jobId, clipId, refetchAfter, failOr409, flushPending],
  );

  const handleCutReply = useCallback(
    async (replyIndex: number) => {
      if (!edit) return;
      const reply = (edit.captions.replies ?? [])[replyIndex];
      if (!reply || reply.word_refs.length === 0) return;
      setPhase("saving");
      setError(null);
      try {
        await flushPending();
        const v = editRef.current?.version ?? edit.version ?? 1;
        const newEdit = await trimClip(jobId, clipId, v, reply.word_refs);
        await refetchAfter(newEdit);
      } catch (e) {
        failOr409(e);
      }
    },
    [edit, jobId, clipId, refetchAfter, failOr409, flushPending],
  );

  const handleCaptionsChange = useCallback(
    (replyIndex: number, text: string | null) => {
      editCaptions((captions) => ({
        ...captions,
        replies: (captions.replies ?? []).map(
          (reply, i): CaptionReply =>
            i === replyIndex ? { ...reply, text_override: text } : reply,
        ),
      }));
    },
    [editCaptions],
  );

  const handleStyleChange = useCallback(
    (patch: Partial<CaptionStyle>) => {
      setActivePresetId(null); // кастомизация поверх пресета — пресет больше не «чистый»
      editCaptions((captions) => ({
        ...captions,
        style: { ...captions.style, ...patch },
      }));
    },
    [editCaptions],
  );

  const handleHighlightChange = useCallback(
    (patch: Partial<HighlightStyle> | null) => {
      setActivePresetId(null);
      editCaptions((captions) => ({
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
    [editCaptions],
  );

  const handleMarginChange = useCallback(
    (marginV: number) => {
      editCaptions((captions) => ({
        ...captions,
        style: { ...captions.style, margin_v: clampMargin(marginV) },
      }));
    },
    [editCaptions],
  );

  // ── burn-тогл (таб «Субтитры», T4 #8): не накладывать наши субтитры ──
  const handleBurnChange = useCallback(
    (burn: boolean) => {
      editCaptions((captions) => ({ ...captions, burn }));
    },
    [editCaptions],
  );

  // ── хук (таб «Хук») → instant-превью + дебаунс-персист (та же модель, что стиль) ──
  // patch=null → убрать хук; иначе мерж поверх текущего (или нового {text:""}) —
  // опущенные поля дольёт pydantic (шрифт/плашка/размер по дефолту).
  const handleHookChange = useCallback(
    (patch: Partial<HookOverlay> | null) => {
      editCaptions((captions) => ({
        ...captions,
        hook: patch === null ? null : { ...(captions.hook ?? { text: "" }), ...patch },
      }));
    },
    [editCaptions],
  );

  // применение пресета — в ТОЙ ЖЕ очереди мутаций (свежая версия, никаких 409 на ходу).
  // Сначала flush накопленных правок (ВНЕ chain → без дедлока), чтобы пресет лёг поверх
  // персистнутого состояния и ничего не потерялось.
  const handlePresetApply = useCallback(
    async (presetId: string) => {
      await flushPending();
      const p = patchChain.current.then(async () => {
        const cur = editRef.current;
        if (!cur) return;
        setError(null);
        try {
          const updated = await applyPreset(jobId, clipId, cur.version ?? 1, presetId);
          editRef.current = updated;
          setEdit(updated);
          setActivePresetId(presetId);
          setDirty(true);
          setUnsaved(false);
          await refreshAss();
        } catch (e) {
          failOr409(e);
        }
      });
      patchChain.current = p;
      return p;
    },
    [jobId, clipId, refreshAss, failOr409, flushPending],
  );

  // ── W4: перегенерация хука под текущий интервал (узкий Gemini-вызов, явный opt-in) ──
  // В ТОЙ ЖЕ очереди мутаций (свежая версия). Меняет только hook.text; стиль не трогает.
  const [regeneratingHook, setRegeneratingHook] = useState(false);
  const handleHookRegenerate = useCallback(async () => {
    await flushPending();
    const p = patchChain.current.then(async () => {
      const cur = editRef.current;
      if (!cur) return;
      setError(null);
      setRegeneratingHook(true);
      try {
        const updated = await regenerateHook(jobId, clipId, cur.version ?? 1);
        editRef.current = updated;
        setEdit(updated);
        setDirty(true);
        setUnsaved(false);
        // hook.text меняется в Dialogue-теге → пересобрать ASS (как пресет)
        await refreshAss();
      } catch (e) {
        failOr409(e);
      } finally {
        setRegeneratingHook(false);
      }
    });
    patchChain.current = p;
    return p;
  }, [jobId, clipId, refreshAss, failOr409, flushPending]);

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
        await flushPending();
        const v = editRef.current?.version ?? edit.version ?? 1;
        const newEdit = await setCropOverride(jobId, clipId, v, {
          source_start: outerStart,
          source_end: outerEnd,
          mode,
          center,
          center_b: centerB,
        });
        editRef.current = newEdit; // см. editRef-комментарий: очередь читает свежую версию
        setEdit(newEdit);
        setDirty(true);
      } catch (e) {
        failOr409(e);
      }
    },
    [edit, jobId, clipId, outerStart, outerEnd, failOr409, flushPending],
  );

  // ── FitTimeline (#1): форсировать кадр на source-диапазон ШОТОВ ──
  // Зеркалит handleFrameApply, но диапазон приходит от мини-таймлайна (выделенные
  // регионы → source-время), а не весь клип. mode:"auto" → бэкенд чистит override в
  // диапазоне. После применения перечитываем reframe-план → полоса + превью обновятся.
  const handleApplyRange = useCallback(
    async (sourceStart: number, sourceEnd: number, mode: "fit" | "fill" | "auto") => {
      if (!edit) return;
      setError(null);
      try {
        await flushPending();
        const v = editRef.current?.version ?? edit.version ?? 1;
        const newEdit = await setCropOverride(jobId, clipId, v, {
          source_start: sourceStart,
          source_end: sourceEnd,
          mode,
          center: null,
          center_b: null,
        });
        editRef.current = newEdit; // см. editRef-комментарий: очередь читает свежую версию
        setEdit(newEdit);
        setDirty(true);
        void loadReframe(); // полоса + превью отражают новый план
      } catch (e) {
        failOr409(e);
      }
    },
    [edit, jobId, clipId, failOr409, flushPending, loadReframe],
  );

  // ── соотношение сторон (T5): меняет выход + PlayRes ASS → рефетчим ASS ──
  const handleAspectChange = useCallback(
    async (aspect: Aspect) => {
      if (!edit || edit.aspect === aspect) return;
      setError(null);
      try {
        await flushPending();
        const v = editRef.current?.version ?? edit.version ?? 1;
        const newEdit = await setClipAspect(jobId, clipId, v, aspect);
        editRef.current = newEdit; // см. editRef-комментарий: очередь читает свежую версию
        setEdit(newEdit);
        setDirty(true);
        await refreshAss(); // PlayRes изменился → libass перерисует в новом аспекте
      } catch (e) {
        failOr409(e);
      }
    },
    [edit, jobId, clipId, refreshAss, failOr409, flushPending],
  );

  // ── рендер ──
  const handleRender = useCallback(async () => {
    if (!edit) return;
    setError(null);
    stopPoll();
    // Flip to "rendering" BEFORE the POST so the button disables and shows feedback
    // instantly — otherwise the request round-trip looks dead and people click again.
    setRenderState({ kind: "rendering", elapsed: 0 });
    timerRef.current = setInterval(
      () =>
        setRenderState((s) =>
          s.kind === "rendering" ? { kind: "rendering", elapsed: s.elapsed + 1 } : s,
        ),
      1000,
    );
    try {
      await startRenderClip(jobId, clipId);
    } catch (e) {
      stopPoll();
      setRenderState({ kind: "idle" });
      setError(String(e));
      return;
    }
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
          setError(st.error ?? "Render failed");
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

  // ── on-video direct-grab manipulation (CapCut-style selection box) ──
  // The visible selection box (OverlaySelectionBox) owns the pointer mechanics:
  // setPointerCapture + imperative box-style during move (NO React state per move →
  // no re-render of the heavy ClipEditorScreen / libass) and commits margin_v / size
  // ONLY on pointerup. The fraction is normalised against the LIVE render box on every
  // move, so it stays correct in fullscreen and after a resize. Here we only supply the
  // current fractions/sizes and the commit callbacks.
  //
  // Vertical anchors (PlayResY = 1920, no horizontal field — text is centered):
  //   • hook    → margin_v from the TOP  → box top    = margin_v / 1920
  //   • caption → margin_v from the BOTTOM → box bottom = margin_v / 1920
  const CAPTION_SIZE_MIN = 40; // mirror StyleTab "Size" slider
  const CAPTION_SIZE_MAX = 140;
  const HOOK_SIZE_MIN = 36; // mirror HookTab "Size" slider
  const HOOK_SIZE_MAX = 120;

  const hook = edit?.captions.hook ?? null;
  const hookEnabled = !!hook?.enabled;
  const hookSize = hook?.size ?? 66;
  const hookText = hook?.text ?? "";

  const captionStyle = edit?.captions.style;
  const captionSize = captionStyle?.size ?? 90;
  const hasCaptions = replyRanges.length > 0;

  // ── libass's REAL rendered rects (hook / caption) → CapCut selection box ──
  // LibassLayer surfaces the worker's per-frame fused bbox of each element as render-box
  // fractions. We keep the LATEST in a ref (updated every frame, no re-render) and mirror
  // it to light state at most ~once per rAF — so the heavy editor tree re-renders at frame
  // cadence (not per worker message) and the boxes hug the real text exactly.
  const subRectsRef = useRef<SubRects>({ hook: null, caption: null });
  const [subRects, setSubRects] = useState<SubRects>({ hook: null, caption: null });
  const subRectsRaf = useRef(0);
  const handleSubRects = useCallback((rects: SubRects) => {
    subRectsRef.current = rects;
    if (subRectsRaf.current) return; // coalesce bursts of worker messages to one rAF
    subRectsRaf.current = requestAnimationFrame(() => {
      subRectsRaf.current = 0;
      setSubRects(subRectsRef.current);
    });
  }, []);
  useEffect(
    () => () => {
      if (subRectsRaf.current) cancelAnimationFrame(subRectsRaf.current);
    },
    [],
  );
  // Remount the libass instances when hook/caption presence toggles: instances are created
  // per-part at mount (we don't spin up an instance for an absent track), so enabling the
  // hook (or first captions) from nothing needs a fresh instance for that slot.
  const libassKey = `${hookEnabled && hookText.trim() ? 1 : 0}-${hasCaptions ? 1 : 0}`;

  // caption: free move → pos_x (center) + pos_y (bottom edge, \an2); corner → size; side → width.
  const onCaptionMove = useCallback(
    (xFrac: number, yFrac: number) => handleStyleChange({ pos_x: xFrac, pos_y: yFrac }),
    [handleStyleChange],
  );
  const onCaptionResize = useCallback(
    (size: number) => handleStyleChange({ size }),
    [handleStyleChange],
  );
  const onCaptionWidth = useCallback(
    (wrap_width: number) => handleStyleChange({ wrap_width }),
    [handleStyleChange],
  );
  // hook: free move → pos_x (center) + pos_y (top edge, \an8); corner → size; side → width.
  const onHookMove = useCallback(
    (xFrac: number, yFrac: number) => handleHookChange({ pos_x: xFrac, pos_y: yFrac }),
    [handleHookChange],
  );
  const onHookResize = useCallback(
    (size: number) => handleHookChange({ size }),
    [handleHookChange],
  );
  const onHookWidth = useCallback(
    (wrap_width: number) => handleHookChange({ wrap_width }),
    [handleHookChange],
  );

  // ── РЕАЛЬНЫЙ режим кадра для превью на текущий момент ──
  // Приоритет: ручной override (таб «Кадр», виден сразу) → план от /reframe (D2: единый
  // путь рендера, всегда для ТЕКУЩИХ интервалов) → дефолт fill-центр.
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
    if (rawRegions) {
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
  }, [edit, outerStart, outerEnd, rawRegions, nowSec]);

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
            Try again
          </button>
          <a
            href={`/dashboard?job=${jobId}`}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white transition hover:bg-accent-2"
          >
            ← All clips
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
        saving={unsaved}
        onBeforeLeave={flushPending}
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
          Loading editor…
        </div>
      ) : (
        <main className="grid min-h-0 grid-cols-1 gap-4 overflow-y-auto p-4 lg:grid-cols-[minmax(280px,380px)_minmax(0,1fr)] lg:overflow-visible">
          {/* ЛЕВО: превью. Доступная область = ширина колонки × ограниченная высота;
              PreviewPlayer сам contain'ится по aspectClass (w-full + max-h-full + aspect) →
              НЕ распирает страницу на 16:9/1:1/4:5 (баг T5 пофикшен). */}
          <div className="sticky top-0 z-10 flex min-h-0 flex-col bg-bg pb-3 lg:static lg:z-auto lg:pb-0">
            <div className="flex h-[44vh] max-h-full w-full items-center justify-center lg:h-auto lg:min-h-0 lg:flex-1">
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
                      key={libassKey}
                      videoRef={videoRef}
                      assText={assText}
                      sourceStart={outerStart}
                      onError={() => setLibassFailed(true)}
                      onSubRects={handleSubRects}
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
                      simplified preview
                    </span>
                  )}

                  {/* CapCut-style selection box — captions (bottom-anchored): grab the box
                      to drag vertically, drag the corner to resize the font. Tapping
                      without dragging opens inline text edit. Shown whenever captions
                      exist (any tab). */}
                  {useLibass &&
                    edit &&
                    hasCaptions &&
                    subRects.caption &&
                    editingReply === null && (
                      <OverlaySelectionBox
                        anchor="bottom"
                        rect={subRects.caption}
                        size={captionSize}
                        sizeMin={CAPTION_SIZE_MIN}
                        sizeMax={CAPTION_SIZE_MAX}
                        label="Captions"
                        onMoveCommit={onCaptionMove}
                        onResizeCommit={onCaptionResize}
                        onWidthCommit={onCaptionWidth}
                        onTap={openReplyEdit}
                      />
                    )}

                  {/* CapCut-style selection box — hook (top-anchored). Shown whenever the
                      hook is enabled, on ANY tab (was previously gated to the Hook tab). */}
                  {useLibass &&
                    hookEnabled &&
                    hookText.trim() &&
                    subRects.hook &&
                    editingReply === null && (
                      <OverlaySelectionBox
                        anchor="top"
                        rect={subRects.hook}
                        size={hookSize}
                        sizeMin={HOOK_SIZE_MIN}
                        sizeMax={HOOK_SIZE_MAX}
                        label="Hook"
                        onMoveCommit={onHookMove}
                        onResizeCommit={onHookResize}
                        onWidthCommit={onHookWidth}
                      />
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
                        placeholder="Caption text…"
                        className="w-full resize-none rounded-lg border border-accent/60 bg-black/80 p-2 text-center text-sm font-semibold text-white outline-none focus:ring-2 focus:ring-accent/50"
                      />
                      <p className="mt-1 text-center text-[10px] text-white/70">
                        Enter to save · Esc to cancel
                      </p>
                    </div>
                  )}
                </PreviewPlayer>
            </div>

            {/* #1: мини-таймлайн «форсировать кадр» под превью. shrink-0 — чтобы плеер
                (flex-1 выше) ужимался под него, а не клипал полосу за пределы колонки. */}
            {edit && (
              <div className="shrink-0">
                <FitTimeline
                  regions={rawRegions}
                  intervals={edit.source_intervals}
                  overrides={edit.reframe_overrides}
                  nowSec={nowSec}
                  busy={busy}
                  onApplyRange={handleApplyRange}
                />
              </div>
            )}
          </div>

          {/* ПРАВО: табы */}
          <div className="flex min-h-0 flex-col gap-3">
            {/* #1: явно про live-vs-рендер — частый вопрос «надо ли ререндерить» */}
            <p className="shrink-0 rounded-lg border border-line bg-surface-2 px-3 py-2 text-[11px] leading-snug text-muted">
              <span className="font-semibold text-accent">Preview is live</span> — edits show
              instantly. <span className="font-semibold text-ink">“Render”</span> writes them to
              the downloadable file.
            </p>
            <div className="flex shrink-0 gap-1 rounded-xl border border-line bg-surface p-1">
              {TABS.map(({ id, label, icon: Icon }) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => setTab(id)}
                  className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-2.5 text-sm font-semibold transition sm:py-2 ${
                    tab === id
                      ? "bg-surface-3 text-accent shadow-[0_1px_2px_rgba(0,0,0,.4)]"
                      : "text-muted hover:bg-surface-2 hover:text-ink"
                  }`}
                >
                  <Icon className="size-4" />
                  {label}
                </button>
              ))}
            </div>

            <div className="flex min-h-0 flex-1 flex-col rounded-xl border border-line bg-surface p-4">
              {edit && tab === "agent" && (
                <AgentTab
                  key={clipId}
                  jobId={jobId}
                  clipId={clipId}
                  busy={busy}
                  onAgentEdited={handleAgentEdited}
                />
              )}
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
                <HookTab
                  edit={edit}
                  busy={busy}
                  onHookChange={handleHookChange}
                  onRegenerate={handleHookRegenerate}
                  regenerating={regeneratingHook}
                />
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
      <footer className="shrink-0 border-t border-line bg-surface px-4 py-2.5 sm:py-3">
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
            {phase === "loading" ? "Loading timeline…" : "Timeline unavailable for this clip."}
          </div>
        )}
      </footer>
    </div>
  );
}
