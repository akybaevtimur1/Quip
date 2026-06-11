"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import { mmss } from "@/lib/format";
import type { ClipType, TimelineData, TimelineSegment, Word } from "@/lib/types";

// Длина шортса клампится в эти границы (sec). Совпадает с CLIP_MIN_SEC/CLIP_MAX_SEC бэка.
const CLIP_MIN_SEC = 15;
const CLIP_MAX_SEC = 60;

// Цвета маркеров по типу сегмента — согласованная палитра из мокапа (спека §B2).
const TYPE_COLOR: Record<ClipType, string> = {
  hook: "#ff5a3d", // коралл
  strong_quote: "#ffd23d", // жёлтый
  emotional_peak: "#34e36b", // зелёный
  complete_thought: "#2f7cf6", // синий
};

const TYPE_LABEL: Record<ClipType, string> = {
  hook: "Хук",
  strong_quote: "Цитата",
  emotional_peak: "Пик эмоций",
  complete_thought: "Мысль целиком",
};

// Кол-во столбиков «волны». Декоративно — из плотности слов по бакетам.
const WAVE_BUCKETS = 120;

const clamp = (n: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, n));

/**
 * Плотность слов по равным бакетам времени → нормализованные высоты [0.12..1].
 * Чисто декоративная «волна» (MVP: плотность слов, не громкость).
 */
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

/** Транскрипт в окне [t-pad, t+pad] (sec) — для hover-тултипа. */
function wordsAround(words: Word[], t: number, pad: number): string {
  const lo = t - pad;
  const hi = t + pad;
  const picked = words.filter((w) => w.end >= lo && w.start <= hi).map((w) => w.text);
  return picked.join(" ").trim();
}

/** Ближайший по времени сегмент к точке t (для reason в тултипе). */
function nearestSegment(segments: TimelineSegment[], t: number): TimelineSegment | null {
  let best: TimelineSegment | null = null;
  let bestDist = Infinity;
  for (const s of segments) {
    // расстояние до интервала: 0 если внутри
    const d = t < s.start ? s.start - t : t > s.end ? t - s.end : 0;
    if (d < bestDist) {
      bestDist = d;
      best = s;
    }
  }
  return best;
}

type DragMode = "move" | "resize-l" | "resize-r";

interface DragState {
  mode: DragMode;
  // координата источника на момент захвата (sec)
  pointerStart: number;
  intervalStart: number;
  intervalEnd: number;
}

export interface TimelineEditorProps {
  jobId: string;
  clipId: string;
  version: number;
  data: TimelineData;
  interval: { source_start: number; source_end: number };
  /** Вызывается по отпусканию (или клику по маркеру) с новыми границами в координатах источника. */
  onIntervalChange: (start: number, end: number) => void;
}

export function TimelineEditor({ data, interval, onIntervalChange }: TimelineEditorProps) {
  const duration = Math.max(data.duration, 0.001);
  const trackRef = useRef<HTMLDivElement>(null);

  // Локальный «живой» интервал во время drag — мгновенный отклик до коммита наверх.
  const [live, setLive] = useState<{ start: number; end: number } | null>(null);
  const dragRef = useRef<DragState | null>(null);

  // Hover-тултип.
  const [hover, setHover] = useState<{ x: number; t: number } | null>(null);

  const segStart = live ? live.start : interval.source_start;
  const segEnd = live ? live.end : interval.source_end;

  const wave = useMemo(
    () => buildWave(data.words, duration, WAVE_BUCKETS),
    [data.words, duration],
  );

  const pct = (t: number) => `${clamp((t / duration) * 100, 0, 100)}%`;

  // px → секунды источника по ширине дорожки.
  const pxToTime = useCallback(
    (clientX: number): number => {
      const el = trackRef.current;
      if (!el) return 0;
      const r = el.getBoundingClientRect();
      const frac = clamp((clientX - r.left) / r.width, 0, 1);
      return frac * duration;
    },
    [duration],
  );

  const commit = useCallback(
    (start: number, end: number) => {
      onIntervalChange(start, end);
    },
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
        // только hover, без drag
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
        // левый край: длина в [min,max], не залезает за правый
        const minStart = Math.max(0, end - CLIP_MAX_SEC);
        const maxStart = end - CLIP_MIN_SEC;
        start = clamp(drag.intervalStart + delta, minStart, maxStart);
      } else {
        // resize-r: правый край
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
        // capture мог не стоять — не критично
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

  // Клик по маркеру сегмента → переместить шортс на него (кламп длины в [min,max]).
  const jumpToSegment = useCallback(
    (s: TimelineSegment) => {
      const rawLen = s.end - s.start;
      const len = clamp(rawLen, CLIP_MIN_SEC, CLIP_MAX_SEC);
      let start = s.start;
      // центрируем, если сегмент пришлось укоротить/удлинить, держим start как якорь
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
  const hoverText = hover ? wordsAround(data.words, hover.t, 3) : "";

  return (
    <div className="w-full select-none">
      {/* легенда типов */}
      <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1">
        {(Object.keys(TYPE_LABEL) as ClipType[]).map((t) => (
          <span key={t} className="inline-flex items-center gap-1.5 text-[11px] text-muted">
            <span
              className="size-2 rounded-full"
              style={{ background: TYPE_COLOR[t] }}
            />
            {TYPE_LABEL[t]}
          </span>
        ))}
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
          {/* волна (декор) */}
          <div className="pointer-events-none absolute inset-0 flex items-end gap-px px-px">
            {wave.map((h, i) => (
              <div
                key={i}
                className="flex-1 rounded-t-sm bg-muted/25"
                style={{ height: `${h * 100}%` }}
              />
            ))}
          </div>

          {/* маркеры сегментов ИИ */}
          {data.segments.map((s, i) => {
            const left = (s.start / duration) * 100;
            const width = Math.max(((s.end - s.start) / duration) * 100, 0.4);
            return (
              <button
                key={`${s.clip_id ?? "seg"}-${i}`}
                type="button"
                onPointerDown={(e) => e.stopPropagation()}
                onClick={(e) => {
                  e.stopPropagation();
                  jumpToSegment(s);
                }}
                title={`${TYPE_LABEL[s.type]} · ${s.score.toFixed(2)} · ${s.reason}`}
                aria-label={`Перейти к моменту: ${TYPE_LABEL[s.type]}`}
                className="absolute bottom-0 cursor-pointer rounded-sm opacity-80 transition hover:opacity-100"
                style={{
                  left: `${left}%`,
                  width: `${width}%`,
                  height: "6px",
                  background: TYPE_COLOR[s.type],
                }}
              />
            );
          })}

          {/* блок шортса */}
          <div
            onPointerDown={onPointerDown("move")}
            className="absolute top-0 bottom-0 cursor-grab rounded-md border-2 border-accent bg-accent/15 active:cursor-grabbing"
            style={{ left: pct(segStart), width: `${((segEnd - segStart) / duration) * 100}%` }}
          >
            {/* грип левый */}
            <div
              onPointerDown={onPointerDown("resize-l")}
              className="absolute -left-1 top-0 bottom-0 flex w-3 cursor-ew-resize items-center justify-center"
            >
              <span className="h-8 w-1 rounded-full bg-accent" />
            </div>
            {/* грип правый */}
            <div
              onPointerDown={onPointerDown("resize-r")}
              className="absolute -right-1 top-0 bottom-0 flex w-3 cursor-ew-resize items-center justify-center"
            >
              <span className="h-8 w-1 rounded-full bg-accent" />
            </div>
            {/* длительность по центру блока */}
            <span className="pointer-events-none absolute inset-x-0 top-1 text-center font-mono text-[10px] font-semibold text-accent">
              {mmss(segEnd - segStart)}
            </span>
          </div>

          {/* плейхед (позиция курсора при hover) */}
          {hover && (
            <div
              className="pointer-events-none absolute top-0 bottom-0 w-px bg-ink/70"
              style={{ left: `${hover.x}px` }}
            />
          )}
        </div>

        {/* hover-тултип */}
        {hover && (hoverText || hoverSeg) && (
          <div
            className="pointer-events-none absolute z-10 max-w-xs -translate-x-1/2 rounded-lg border border-line bg-surface px-3 py-2 shadow-lg"
            style={{
              // CSS clamp: держим тултип в пределах дорожки без чтения ref в рендере.
              left: `clamp(80px, ${hover.x}px, calc(100% - 80px))`,
              bottom: "calc(100% + 8px)",
            }}
          >
            <div className="mb-1 font-mono text-[10px] text-muted">{mmss(hover.t)}</div>
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

      {/* линейка времени */}
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
              {mmss(frac * duration)}
            </span>
          );
        })}
      </div>
    </div>
  );
}

export default TimelineEditor;
