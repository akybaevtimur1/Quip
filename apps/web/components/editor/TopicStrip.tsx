"use client";

import { BookOpen } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { getVideoMap } from "@/lib/api";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { Numeral } from "@/components/ui/Numeral";
import { mmss } from "@/lib/format";
import { KIND_COLOR, KIND_KEYS, kindColor } from "@/lib/momentKinds";
import type { VideoChapter, VideoMap, VideoMoment } from "@/lib/types";

// ────────────────────────────────────────────────────────────────────────────
// TopicStrip — compact chapter/moment navigator inside the clip editor.
// Visually distinct from FitTimeline (neutral surface, BookOpen icon, "Темы видео" header).
// Shows «Подвинуть клип сюда» per moment; marks current-clip overlap subtly.
// Mobile: outer details default-closed so the strip stays compact below FitTimeline.
// ────────────────────────────────────────────────────────────────────────────

interface Props {
  jobId: string;
  currentStart: number;
  currentEnd: number;
  duration: number;
  onMoveTo: (start: number, end: number) => void;
}

const MIN_CLIP_SEC = 20;

/** Expand a moment interval to ≥MIN_CLIP_SEC, symmetric, clamped to [0,duration]. */
function expandInterval(
  start: number,
  end: number,
  duration: number,
): [number, number] {
  const len = end - start;
  if (len >= MIN_CLIP_SEC) {
    return [Math.max(0, start), Math.min(end, duration)];
  }
  const need = MIN_CLIP_SEC - len;
  const half = need / 2;
  let s = start - half;
  let e = end + half;
  if (s < 0) {
    e = Math.min(duration, e + (-s));
    s = 0;
  }
  if (e > duration) {
    s = Math.max(0, s - (e - duration));
    e = duration;
  }
  return [s, e];
}

/** Returns true if [a,b] and [c,d] overlap (at least a shared point). */
function overlaps(a: number, b: number, c: number, d: number): boolean {
  return a < d && c < b;
}

// ─── Skeleton (pending) ──────────────────────────────────────────────────────
function PendingState() {
  return (
    <div className="px-3 py-2.5 text-xs text-muted" role="status">
      AI is reading the video…
    </div>
  );
}

// ─── Moment row ──────────────────────────────────────────────────────────────
function MomentRow({
  moment,
  isCurrent,
  duration,
  onMoveTo,
}: {
  moment: VideoMoment;
  isCurrent: boolean;
  duration: number;
  onMoveTo: (s: number, e: number) => void;
}) {
  const { dot, chip } = kindColor(moment.kind);

  function handleMove() {
    const [s, e] = expandInterval(moment.start, moment.end, duration);
    onMoveTo(s, e);
  }

  return (
    <div
      className={`flex items-center gap-2 rounded-md border px-2.5 py-1.5 text-xs ${chip} ${
        isCurrent ? "ring-1 ring-inset ring-accent/40" : ""
      }`}
    >
      {/* dot */}
      <span className={`size-2 shrink-0 rounded-full ${dot}`} aria-hidden />

      {/* label + time */}
      <div className="min-w-0 flex-1">
        <span className="font-semibold text-ink leading-snug">{moment.label}</span>
        <Numeral className="ml-1.5 text-faint">{mmss(moment.start)}</Numeral>
        {isCurrent && (
          <span className="ml-1.5 text-accent font-semibold">current</span>
        )}
      </div>

      {/* move button — min tap target 40px (height via py + line-height) */}
      <button
        type="button"
        onClick={handleMove}
        style={{ minHeight: "40px" }}
        className="shrink-0 rounded-md bg-surface-2 border border-line px-2 py-1 text-xs font-semibold text-ink hover:border-line-strong hover:bg-surface-3 transition-colors duration-150 whitespace-nowrap"
        title="Move the clip to this moment"
      >
        Move here
      </button>
    </div>
  );
}

// ─── Chapter accordion item ──────────────────────────────────────────────────
function ChapterRow({
  chapter,
  currentStart,
  currentEnd,
  duration,
  onMoveTo,
}: {
  chapter: VideoChapter;
  currentStart: number;
  currentEnd: number;
  duration: number;
  onMoveTo: (s: number, e: number) => void;
}) {
  const moments = chapter.moments ?? [];

  return (
    <details className="group border-b border-line last:border-b-0">
      <summary
        className="flex cursor-pointer list-none items-center gap-2 py-2 px-3 text-xs text-ink [&::-webkit-details-marker]:hidden"
        style={{ minHeight: "40px" }}
      >
        {/* chevron */}
        <svg
          className="size-3.5 shrink-0 text-muted transition-transform duration-200 ease-snappy group-open:rotate-180"
          viewBox="0 0 16 16"
          fill="none"
          aria-hidden
        >
          <path
            d="M4 6l4 4 4-4"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>

        <span className="min-w-0 flex-1 font-semibold leading-snug truncate">
          {chapter.title}
        </span>
        <Numeral className="ml-auto shrink-0 whitespace-nowrap text-faint">
          {mmss(chapter.start)}–{mmss(chapter.end)}
        </Numeral>
      </summary>

      {/* body */}
      <div className="px-3 pb-3 space-y-1.5">
        {chapter.summary && (
          <p className="text-xs text-muted leading-relaxed">{chapter.summary}</p>
        )}
        {moments.length > 0 && (
          <div className="space-y-1.5">
            {moments.map((m, i) => (
              <MomentRow
                key={i}
                moment={m}
                isCurrent={overlaps(m.start, m.end, currentStart, currentEnd)}
                duration={duration}
                onMoveTo={onMoveTo}
              />
            ))}
          </div>
        )}
      </div>
    </details>
  );
}

// ─── Kind legend ─────────────────────────────────────────────────────────────
function KindLegend() {
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-1 px-3 py-1.5 text-xs text-muted border-b border-line">
      {KIND_KEYS.map((k) => (
        <span key={k} className="flex items-center gap-1">
          <span className={`size-1.5 rounded-full ${KIND_COLOR[k].dot}`} aria-hidden />
          {KIND_COLOR[k].label}
        </span>
      ))}
    </div>
  );
}

// ─── TopicStrip (main export) ─────────────────────────────────────────────────
export function TopicStrip({
  jobId,
  currentStart,
  currentEnd,
  duration,
  onMoveTo,
}: Props) {
  const [map, setMap] = useState<VideoMap | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  function poll(retry = false) {
    setError(null);
    getVideoMap(jobId, retry)
      .then((data) => {
        setMap(data);
        if (data.status === "pending") {
          timerRef.current = setTimeout(() => poll(false), 2500);
        }
        if (data.status === "failed") {
          setError(data.error ?? "Couldn’t build the topic map");
        }
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Failed to load the topic map");
      });
  }

  useEffect(() => {
    poll(false);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  const chapters = map?.chapters ?? [];
  const isPending = !map || map.status === "pending";
  const isDone = map?.status === "done" && chapters.length > 0;
  const isEmpty = map?.status === "done" && chapters.length === 0;

  return (
    // Outer details: on mobile default-closed, on desktop default-open via open attr.
    // We use CSS sm: to set the open attribute server-side isn't possible — instead we
    // rely on a static `open` prop only on wider screens via a wrapper class trick.
    // Simplest approach: always default-closed so it doesn't crowd mobile; desktop users
    // open once and the browser remembers per-session (native <details> behaviour).
    <details className="group rounded-lg border border-line bg-surface overflow-hidden">
      <summary
        className="flex cursor-pointer list-none items-center gap-2 px-3 py-2.5 text-ink [&::-webkit-details-marker]:hidden"
        style={{ minHeight: "44px" }}
      >
        <BookOpen className="size-3.5 shrink-0 text-muted" aria-hidden />
        <Eyebrow tone="muted" className="flex-1">
          Video topics
        </Eyebrow>
        <svg
          className="size-3.5 shrink-0 text-muted transition-transform duration-200 ease-snappy group-open:rotate-180"
          viewBox="0 0 16 16"
          fill="none"
          aria-hidden
        >
          <path
            d="M4 6l4 4 4-4"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </summary>

      <div className="border-t border-line">
        {/* Pending */}
        {isPending && !error && <PendingState />}

        {/* Error */}
        {error && (
          <div className="flex items-center gap-2 px-3 py-2">
            <p className="flex-1 text-xs text-bad">{error}</p>
            <button
              type="button"
              onClick={() => poll(true)}
              style={{ minHeight: "40px" }}
              className="shrink-0 rounded-md bg-surface-2 border border-line px-2 py-1 text-xs font-semibold text-ink hover:border-line-strong transition-colors duration-150"
            >
              Retry
            </button>
          </div>
        )}

        {/* Empty (done but no chapters) */}
        {isEmpty && !error && (
          <p className="px-3 py-3 text-xs text-muted">No topics yet.</p>
        )}

        {/* Done */}
        {isDone && (
          <>
            <KindLegend />
            {chapters.map((ch, i) => (
              <ChapterRow
                key={i}
                chapter={ch}
                currentStart={currentStart}
                currentEnd={currentEnd}
                duration={duration}
                onMoveTo={onMoveTo}
              />
            ))}
          </>
        )}
      </div>
    </details>
  );
}
