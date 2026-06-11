"use client";

import { ZoomIn, ZoomOut } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getChapters } from "@/lib/api";
import { mmss } from "@/lib/format";
import type {
  Chapter,
  ChaptersData,
  ClipType,
  TimelineData,
  TimelineSegment,
  Word,
} from "@/lib/types";

// ────────────────────────────────────────────────────────────────────────────
// TimelineV2 — таймлайн всего видео для страницы редактора.
// Сверху: полоса AI-ГЛАВ (Gemini описал каждый момент видоса — hover даёт
// summary, клик прыгает шортсом на главу). Ниже: дорожка с волной, маркерами
// AI-моментов и оранжевым блоком шортса (drag/resize). Зум 1×–10× (кнопки и
// Ctrl+колесо), пан ползунком — для часовых видео.
// ────────────────────────────────────────────────────────────────────────────

const CLIP_MIN_SEC = 15;
const CLIP_MAX_SEC = 60;

const TYPE_COLOR: Record<ClipType, string> = {
  hook: "#ff5a3d",
  strong_quote: "#ffd23d",
  emotional_peak: "#34e36b",
  complete_thought: "#2f7cf6",
};

const TYPE_LABEL: Record<ClipType, string> = {
  hook: "Хук",
  strong_quote: "Цитата",
  emotional_peak: "Пик эмоций",
  complete_thought: "Мысль целиком",
};

const WAVE_BUCKETS = 160;
const MAX_ZOOM = 10;
const CHAPTERS_POLL_MS = 4000;

const clamp = (n: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, n));

function buildWave(words: Word[], duration: number, buckets: number): number[] {
  const out = new Array(buckets).fill(0);
  if (duration <= 0 || words.length === 0) return out.map(() => 0.12);
  for (const w of words) {
    const b = clamp(Math.floor((w.start / duration) * buckets), 0, buckets - 1);
    out[b] += 1;
  }
  const max = Math.max(...out, 1);
  return out.map((v) => 0.12 + 0.88 * (v / max));
}

function wordsAround(words: Word[], t: number, pad: number): string {
  const lo = t - pad;
  const hi = t + pad;
  return words
    .filter((w) => w.end >= lo && w.start <= hi)
    .map((w) => w.text)
    .join(" ")
    .trim();
}

function nearestSegment(segments: TimelineSegment[], t: number): TimelineSegment | null {
  let best: TimelineSegment | null = null;
  let bestDist = Infinity;
  for (const s of segments) {
    const d = t < s.start ? s.start - t : t > s.end ? t - s.end : 0;
    if (d < bestDist) {
      bestDist = d;
      best = s;
    }
  }
  return best;
}

function chapterAt(chapters: Chapter[], t: number): Chapter | null {
  return chapters.find((c) => t >= c.start && t < c.end) ?? null;
}

type DragMode = "move" | "resize-l" | "resize-r";

interface DragState {
  mode: DragMode;
  pointerStart: number;
  intervalStart: number;
  intervalEnd: number;
}

export interface TimelineV2Props {
  jobId: string;
  clipId: string;
  version: number;
  data: TimelineData;
  interval: { source_start: number; source_end: number };
  onIntervalChange: (start: number, end: number) => void;
}

export function TimelineV2({ jobId, data, interval, onIntervalChange }: TimelineV2Props) {
  const duration = Math.max(data.duration, 0.001);
  const trackRef = useRef<HTMLDivElement>(null);

  const [live, setLive] = useState<{ start: number; end: number } | null>(null);
  const dragRef = useRef<DragState | null>(null);
  const [hover, setHover] = useState<{ x: number; t: number } | null>(null);

  // ── зум/пан: видимое окно [viewStart, viewStart+viewLen] ⊆ [0, duration] ──
  const [zoom, setZoom] = useState(1);
  const [viewStart, setViewStart] = useState(0);
  const viewLen = duration / zoom;
  const viewStartClamped = clamp(viewStart, 0, duration - viewLen);

  // ── AI-главы: кэш-эндпоинт + поллинг пока pending ──
  const [chapters, setChapters] = useState<ChaptersData | null>(null);
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    async function poll() {
      try {
        const ch = await getChapters(jobId);
        if (cancelled) return;
        setChapters(ch);
        if (ch.status === "pending") timer = setTimeout(poll, CHAPTERS_POLL_MS);
      } catch {
        if (!cancelled) setChapters({ status: "failed", chapters: [], error: "недоступно" });
      }
    }
    void poll();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [jobId]);

  const segStart = live ? live.start : interval.source_start;
  const segEnd = live ? live.end : interval.source_end;

  const wave = useMemo(() => buildWave(data.words, duration, WAVE_BUCKETS), [data.words, duration]);

  // t (sec источника) → проценты ВИДИМОГО окна
  const pct = useCallback(
    (t: number) => `${clamp(((t - viewStartClamped) / viewLen) * 100, -10, 110)}%`,
    [viewStartClamped, viewLen],
  );
  const fracOf = useCallback(
    (t: number) => (t - viewStartClamped) / viewLen,
    [viewStartClamped, viewLen],
  );

  const pxToTime = useCallback(
    (clientX: number): number => {
      const el = trackRef.current;
      if (!el) return 0;
      const r = el.getBoundingClientRect();
      const frac = clamp((clientX - r.left) / r.width, 0, 1);
      return viewStartClamped + frac * viewLen;
    },
    [viewStartClamped, viewLen],
  );

  const setZoomAround = useCallback(
    (nextZoom: number, anchorT: number) => {
      const z = clamp(nextZoom, 1, MAX_ZOOM);
      const nextLen = duration / z;
      // якорим точку под курсором: её доля в окне сохраняется
      const frac = clamp((anchorT - viewStartClamped) / viewLen, 0, 1);
      setZoom(z);
      setViewStart(clamp(anchorT - frac * nextLen, 0, duration - nextLen));
    },
    [duration, viewStartClamped, viewLen],
  );

  const onWheel = useCallback(
    (e: React.WheelEvent) => {
      if (!e.ctrlKey && !e.metaKey) return; // обычный скролл страницы не перехватываем
      e.preventDefault();
      const anchor = pxToTime(e.clientX);
      setZoomAround(zoom * (e.deltaY < 0 ? 1.25 : 0.8), anchor);
    },
    [zoom, pxToTime, setZoomAround],
  );

  const commit = useCallback(
    (start: number, end: number) => onIntervalChange(start, end),
    [onIntervalChange],
  );

  const onPointerDown = useCallback(
    (mode: DragMode) => (e: React.PointerEvent) => {
      e.preventDefault();
      e.stopPropagation();
      (e.target as HTMLElement).setPointerCapture(e.pointerId);
      dragRef.current = {
        mode,
        pointerStart: pxToTime(e.clientX),
        intervalStart: interval.source_start,
        intervalEnd: interval.source_end,
      };
      setLive({ start: interval.source_start, end: interval.source_end });
    },
    [interval.source_start, interval.source_end, pxToTime],
  );

  const onPointerMove = useCallback(
    (e: React.PointerEvent) => {
      const drag = dragRef.current;
      if (!drag) {
        if (trackRef.current) {
          const r = trackRef.current.getBoundingClientRect();
          setHover({ x: e.clientX - r.left, t: pxToTime(e.clientX) });
        }
        return;
      }
      const t = pxToTime(e.clientX);
      const delta = t - drag.pointerStart;
      let start = drag.intervalStart;
      let end = drag.intervalEnd;

      if (drag.mode === "move") {
        const len = drag.intervalEnd - drag.intervalStart;
        start = clamp(drag.intervalStart + delta, 0, duration - len);
        end = start + len;
      } else if (drag.mode === "resize-l") {
        const minStart = Math.max(0, end - CLIP_MAX_SEC);
        const maxStart = end - CLIP_MIN_SEC;
        start = clamp(drag.intervalStart + delta, minStart, maxStart);
      } else {
        const minEnd = start + CLIP_MIN_SEC;
        const maxEnd = Math.min(duration, start + CLIP_MAX_SEC);
        end = clamp(drag.intervalEnd + delta, minEnd, maxEnd);
      }
      setLive({ start, end });
    },
    [duration, pxToTime],
  );

  const endDrag = useCallback(
    (e: React.PointerEvent) => {
      const drag = dragRef.current;
      if (!drag) return;
      try {
        (e.target as HTMLElement).releasePointerCapture(e.pointerId);
      } catch {
        /* capture мог не стоять */
      }
      dragRef.current = null;
      const cur = live;
      setLive(null);
      if (cur && (cur.start !== drag.intervalStart || cur.end !== drag.intervalEnd)) {
        commit(cur.start, cur.end);
      }
    },
    [live, commit],
  );

  const jumpTo = useCallback(
    (rawStart: number, rawEnd: number) => {
      const len = clamp(rawEnd - rawStart, CLIP_MIN_SEC, CLIP_MAX_SEC);
      let start = rawStart;
      let end = start + len;
      if (end > duration) {
        end = duration;
        start = Math.max(0, end - len);
      }
      commit(start, end);
    },
    [duration, commit],
  );

  const hoverSeg = hover ? nearestSegment(data.segments, hover.t) : null;
  const chapterList = chapters?.status === "done" ? (chapters.chapters ?? []) : [];
  const hoverChapter = hover ? chapterAt(chapterList, hover.t) : null;
  const hoverText = hover ? wordsAround(data.words, hover.t, 3) : "";

  return (
    <div className="w-full select-none" onWheel={onWheel}>
      {/* ── верхняя строка: легенда + зум ── */}
      <div className="mb-1.5 flex items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
          {(Object.keys(TYPE_LABEL) as ClipType[]).map((t) => (
            <span key={t} className="inline-flex items-center gap-1.5 text-[11px] text-muted">
              <span className="size-2 rounded-full" style={{ background: TYPE_COLOR[t] }} />
              {TYPE_LABEL[t]}
            </span>
          ))}
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            aria-label="Отдалить"
            disabled={zoom <= 1}
            onClick={() => setZoomAround(zoom / 1.5, viewStartClamped + viewLen / 2)}
            className="inline-flex size-6 items-center justify-center rounded-md border border-line text-muted transition enabled:hover:text-ink disabled:opacity-30"
          >
            <ZoomOut className="size-3.5" />
          </button>
          <span className="w-9 text-center font-mono text-[10px] text-muted">
            {zoom.toFixed(1)}×
          </span>
          <button
            type="button"
            aria-label="Приблизить"
            disabled={zoom >= MAX_ZOOM}
            onClick={() => setZoomAround(zoom * 1.5, segStart + (segEnd - segStart) / 2)}
            className="inline-flex size-6 items-center justify-center rounded-md border border-line text-muted transition enabled:hover:text-ink disabled:opacity-30"
          >
            <ZoomIn className="size-3.5" />
          </button>
        </div>
      </div>

      {/* ── полоса AI-глав ── */}
      <div className="relative mb-1 h-7 w-full overflow-hidden rounded-lg border border-line bg-surface-2">
        {chapters === null || chapters.status === "pending" ? (
          <div className="flex h-full items-center gap-2 px-3">
            <span className="size-2 animate-pulse rounded-full bg-accent" />
            <span className="text-[11px] text-muted">
              ИИ описывает моменты видео… (можно работать дальше)
            </span>
          </div>
        ) : chapters.status === "failed" ? (
          <div className="flex h-full items-center px-3">
            <span className="truncate text-[11px] text-muted">
              AI-карта недоступна: {chapters.error ?? "ошибка"}
            </span>
          </div>
        ) : (
          chapterList.map((c, i) => {
            const leftFrac = fracOf(c.start);
            const widthFrac = (c.end - c.start) / viewLen;
            if (leftFrac + widthFrac < 0 || leftFrac > 1) return null;
            return (
              <button
                key={i}
                type="button"
                onClick={() => jumpTo(c.start, c.end)}
                title={`${c.title}\n${c.summary}`}
                className={`absolute top-0 h-full truncate border-r border-line/60 px-1.5 text-left text-[10px] leading-7 transition hover:bg-accent/15 hover:text-ink ${
                  i % 2 === 0 ? "bg-surface text-muted" : "bg-surface-2 text-muted"
                }`}
                style={{ left: pct(c.start), width: `${Math.max(widthFrac * 100, 0.5)}%` }}
              >
                {c.title}
              </button>
            );
          })
        )}
      </div>

      <div className="relative">
        {/* дорожка */}
        <div
          ref={trackRef}
          className="relative h-20 w-full overflow-hidden rounded-xl border border-line bg-surface-2"
          onPointerMove={onPointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          onPointerLeave={() => {
            if (!dragRef.current) setHover(null);
          }}
        >
          {/* волна (декор): рисуем только видимое окно */}
          <div className="pointer-events-none absolute inset-0 flex items-end gap-px px-px">
            {wave.map((h, i) => {
              const t0 = (i / WAVE_BUCKETS) * duration;
              if (t0 < viewStartClamped - duration / WAVE_BUCKETS || t0 > viewStartClamped + viewLen)
                return null;
              return (
                <div
                  key={i}
                  className="absolute bottom-0 rounded-t-sm bg-muted/25"
                  style={{
                    left: pct(t0),
                    width: `${(duration / WAVE_BUCKETS / viewLen) * 100}%`,
                    height: `${h * 100}%`,
                  }}
                />
              );
            })}
          </div>

          {/* маркеры сегментов ИИ */}
          {data.segments.map((s, i) => {
            const widthFrac = Math.max((s.end - s.start) / viewLen, 0.004);
            return (
              <button
                key={`${s.clip_id ?? "seg"}-${i}`}
                type="button"
                onPointerDown={(e) => e.stopPropagation()}
                onClick={(e) => {
                  e.stopPropagation();
                  jumpTo(s.start, s.end);
                }}
                title={`${TYPE_LABEL[s.type]} · ${s.score.toFixed(2)} · ${s.reason}`}
                aria-label={`Перейти к моменту: ${TYPE_LABEL[s.type]}`}
                className="absolute bottom-0 cursor-pointer rounded-sm opacity-80 transition hover:opacity-100"
                style={{
                  left: pct(s.start),
                  width: `${widthFrac * 100}%`,
                  height: "6px",
                  background: TYPE_COLOR[s.type],
                }}
              />
            );
          })}

          {/* блок шортса */}
          <div
            onPointerDown={onPointerDown("move")}
            className="absolute top-0 bottom-0 cursor-grab touch-none rounded-md border-2 border-accent bg-accent/25 active:cursor-grabbing"
            style={{
              left: pct(segStart),
              width: `${((segEnd - segStart) / viewLen) * 100}%`,
              minWidth: "3rem",
            }}
          >
            <div
              onPointerDown={onPointerDown("resize-l")}
              className="absolute -left-1 top-0 bottom-0 flex w-3 cursor-ew-resize items-center justify-center"
            >
              <span className="h-8 w-1 rounded-full bg-accent" />
            </div>
            <div
              onPointerDown={onPointerDown("resize-r")}
              className="absolute -right-1 top-0 bottom-0 flex w-3 cursor-ew-resize items-center justify-center"
            >
              <span className="h-8 w-1 rounded-full bg-accent" />
            </div>
            <span className="pointer-events-none absolute inset-x-0 top-1 text-center font-mono text-[10px] font-semibold text-accent">
              {mmss(segEnd - segStart)}
            </span>
          </div>

          {/* плейхед-курсор */}
          {hover && (
            <div
              className="pointer-events-none absolute top-0 bottom-0 w-px bg-ink/70"
              style={{ left: `${hover.x}px` }}
            />
          )}
        </div>

        {/* hover-тултип: глава + транскрипт + reason ближайшего момента */}
        {hover && (hoverText || hoverSeg || hoverChapter) && (
          <div
            className="pointer-events-none absolute z-10 max-w-sm -translate-x-1/2 rounded-lg border border-line bg-surface px-3 py-2 shadow-lg"
            style={{
              left: `clamp(100px, ${hover.x}px, calc(100% - 100px))`,
              bottom: "calc(100% + 8px)",
            }}
          >
            <div className="mb-1 flex items-center gap-2 font-mono text-[10px] text-muted">
              {mmss(hover.t)}
              {hoverChapter && (
                <span className="truncate font-sans font-semibold text-ink">
                  {hoverChapter.title}
                </span>
              )}
            </div>
            {hoverChapter && (
              <p className="mb-1 line-clamp-2 text-[11px] leading-snug text-muted">
                {hoverChapter.summary}
              </p>
            )}
            {hoverText && (
              <p className="mb-1 line-clamp-3 text-xs leading-snug text-ink">«{hoverText}»</p>
            )}
            {hoverSeg && (
              <p className="flex items-start gap-1.5 text-[11px] leading-snug text-muted">
                <span
                  className="mt-1 size-2 shrink-0 rounded-full"
                  style={{ background: TYPE_COLOR[hoverSeg.type] }}
                />
                <span>{hoverSeg.reason}</span>
              </p>
            )}
          </div>
        )}
      </div>

      {/* ── пан при зуме + линейка ── */}
      {zoom > 1 && (
        <input
          type="range"
          min={0}
          max={1000}
          value={Math.round((viewStartClamped / Math.max(0.001, duration - viewLen)) * 1000)}
          onChange={(e) =>
            setViewStart(((Number(e.target.value) / 1000) * (duration - viewLen)) | 0)
          }
          aria-label="Прокрутка таймлайна"
          className="mt-1 h-1 w-full cursor-pointer appearance-none rounded-full bg-surface-2 accent-accent"
        />
      )}
      <div className="relative mt-1.5 h-4">
        {Array.from({ length: 6 }).map((_, i) => {
          const frac = i / 5;
          return (
            <span
              key={i}
              className="absolute font-mono text-[10px] text-muted"
              style={{
                left: `${frac * 100}%`,
                transform:
                  i === 0 ? "translateX(0)" : i === 5 ? "translateX(-100%)" : "translateX(-50%)",
              }}
            >
              {mmss(viewStartClamped + frac * viewLen)}
            </span>
          );
        })}
      </div>
    </div>
  );
}

export default TimelineV2;
