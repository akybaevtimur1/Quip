"use client";

import Link from "next/link";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { getVideoMap } from "@/lib/api";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { Numeral } from "@/components/ui/Numeral";
import { Skeleton } from "@/components/ui/Skeleton";
import { mmss } from "@/lib/format";
import { KIND_COLOR, KIND_KEYS, kindColor } from "@/lib/momentKinds";
import type { ClipOut, VideoChapter, VideoMap, VideoMoment } from "@/lib/types";

// SSR-safe media-query hook (no setState-in-effect): server snapshot = false
// (mobile-first → collapsed), client subscribes to matchMedia changes.
function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (cb: () => void) => {
      const mql = window.matchMedia(query);
      mql.addEventListener("change", cb);
      return () => mql.removeEventListener("change", cb);
    },
    [query],
  );
  return useSyncExternalStore(
    subscribe,
    () => window.matchMedia(query).matches,
    () => false,
  );
}

// ─── helpers ────────────────────────────────────────────────────────────────
/** Parse mm:ss string from narrative text → total seconds */
function parseTimecode(raw: string): number {
  const [m, s] = raw.split(":").map(Number);
  return m * 60 + (s ?? 0);
}

/** Find clip that covers a given source second */
function findClipByTime(clips: ClipOut[], sec: number): ClipOut | undefined {
  return clips.find((c) => c.start <= sec && sec <= c.end);
}

/** Extract clip number label from id like "clip_03" → "3" */
function clipNum(clipId: string): string {
  const m = clipId.match(/(\d+)$/);
  return m ? String(parseInt(m[1], 10)) : clipId;
}

// ─── Narrative parser ────────────────────────────────────────────────────────
/**
 * Parses narrative text containing `[[clip:clip_NN]]` and `[mm:ss]` tokens.
 * Returns an array of React-renderable segments.
 */
function parseNarrative(
  text: string,
  jobId: string,
  clips: ClipOut[],
): React.ReactNode[] {
  // Regex: captures [[clip:clip_NN]] OR [mm:ss] tokens
  // Accept both [[clip:clip_NN]] (prompt format) and [[clip_NN]] (Gemini sometimes drops "clip:").
  const TOKEN_RE = /\[\[(?:clip:)?(clip_\d+)\]\]|\[(\d{1,2}:\d{2})\]/g;
  const nodes: React.ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = TOKEN_RE.exec(text)) !== null) {
    // Push plain text before this token
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }

    if (match[1]) {
      // [[clip:clip_NN]] → editor link
      const clipId = match[1];
      nodes.push(
        <Link
          key={`${match.index}`}
          href={`/edit/${jobId}/${clipId}`}
          // inline-block + whitespace-nowrap: тег «Clip #N» АТОМАРЕН — никогда не рвётся между строк
          // («Clip» / «#3»). Лёгкая coral-pill (bg вместо подчёркивания) + mx-px: ряд из многих клипов
          // подряд читается раздельными тегами с воздухом, а не сплошной подчёркнутой стеной.
          className="mx-px inline-block whitespace-nowrap rounded bg-accent/10 px-1.5 py-0.5 align-baseline text-xs font-semibold text-accent hover:bg-accent/20 transition-colors duration-150"
        >
          Clip #{clipNum(clipId)}
        </Link>,
      );
    } else if (match[2]) {
      // [mm:ss] → mono chip; link if a clip covers that second
      const raw = match[2];
      const sec = parseTimecode(raw);
      const clip = findClipByTime(clips, sec);
      const chipClass =
        "font-mono text-xs px-1.5 py-0.5 rounded-md bg-surface-2 border border-line";
      if (clip) {
        nodes.push(
          <Link
            key={`${match.index}`}
            href={`/edit/${jobId}/${clip.id}`}
            className={`${chipClass} text-ink hover:border-line-strong transition-colors duration-150`}
          >
            {raw}
          </Link>,
        );
      } else {
        nodes.push(
          <span key={`${match.index}`} className={`${chipClass} text-faint`}>
            {raw}
          </span>,
        );
      }
    }

    lastIndex = TOKEN_RE.lastIndex;
  }

  // Remaining plain text
  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }

  return nodes;
}

// ─── Skeleton ────────────────────────────────────────────────────────────────
function PendingSkeleton() {
  return (
    <div className="space-y-3 py-4" role="status" aria-label="AI is reading the video…">
      <p className="text-sm text-muted">
        Reading the whole video to map its strongest moments
        <span className="text-faint"> — usually under a minute.</span>
      </p>
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-5/6" />
      <Skeleton className="h-4 w-4/6" />
      <div className="mt-4 space-y-2">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
      </div>
    </div>
  );
}

// ─── Moment chip ─────────────────────────────────────────────────────────────
function MomentChip({
  moment,
  jobId,
  clips,
  chapterClipIds,
}: {
  moment: VideoMoment;
  jobId: string;
  clips: ClipOut[];
  chapterClipIds: string[];
}) {
  const { dot, chip } = kindColor(moment.kind);
  const coveringClip = findClipByTime(clips, moment.start);
  const fallbackClipId = chapterClipIds[0];
  const targetClipId = coveringClip?.id ?? fallbackClipId;
  const interactive = !!targetClipId;

  const inner = (
    <div
      className={`flex items-start gap-2.5 rounded-lg border px-3 py-2.5 text-sm ${chip} ${
        interactive
          ? "hover:border-opacity-60 transition-colors duration-150 cursor-pointer"
          : ""
      }`}
    >
      <span
        className={`mt-1 size-2 shrink-0 rounded-pill ${dot}`}
        aria-hidden
      />
      <div className="min-w-0 flex-1">
        <p className="font-semibold text-ink leading-snug">{moment.label}</p>
        <p className="text-xs text-muted mt-0.5 leading-relaxed">
          {moment.why}
        </p>
        <Numeral className="mt-1 block text-xs text-faint">{mmss(moment.start)}</Numeral>
      </div>
    </div>
  );

  if (!interactive) return <div>{inner}</div>;

  return (
    <Link href={`/edit/${jobId}/${targetClipId}`} className="block">
      {inner}
    </Link>
  );
}

// ─── Chapter accordion item ───────────────────────────────────────────────────
function ChapterItem({
  chapter,
  jobId,
  clips,
}: {
  chapter: VideoChapter;
  jobId: string;
  clips: ClipOut[];
}) {
  const clipIds = chapter.clip_ids ?? [];
  const moments = chapter.moments ?? [];

  return (
    <details className="group border-b border-line last:border-b-0">
      <summary
        className="flex cursor-pointer list-none items-center justify-between gap-3 py-3 px-4 text-ink [&::-webkit-details-marker]:hidden"
        style={{ minHeight: "44px" }}
      >
        <div className="min-w-0 flex-1">
          <span className="font-semibold text-sm leading-snug">
            {chapter.title}
          </span>
          <Numeral className="ml-2 whitespace-nowrap text-xs text-faint">
            {mmss(chapter.start)}–{mmss(chapter.end)}
          </Numeral>
          {clipIds.length > 0 && (
            // Hierarchy via contrast (ink, not coral): the clip count matters more than
            // moments, but coral stays scarce — every chapter row repeating it would dilute it.
            <span className="ml-2 font-mono text-eyebrow uppercase tabular-nums text-ink">
              {clipIds.length} clip{clipIds.length === 1 ? "" : "s"}
            </span>
          )}
          {moments.length > 0 && (
            <span className="ml-2 font-mono text-eyebrow uppercase tabular-nums text-muted">
              {moments.length} moment{moments.length === 1 ? "" : "s"}
            </span>
          )}
        </div>
        {/* chevron icon */}
        <svg
          className="size-4 shrink-0 text-muted transition-transform duration-200 ease-snappy group-open:rotate-180"
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

      <div className="px-4 pb-4 space-y-3">
        {/* Summary text */}
        {chapter.summary && (
          <p className="text-sm text-muted leading-relaxed">
            {chapter.summary}
          </p>
        )}

        {/* Clip links */}
        {clipIds.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {clipIds.map((clipId) => (
              <Link
                key={clipId}
                href={`/edit/${jobId}/${clipId}`}
                className="inline-flex items-center gap-1.5 rounded-md bg-surface-2 border border-line px-2.5 py-1 text-xs font-semibold text-ink hover:border-line-strong transition-colors duration-150"
              >
                <span className="size-1.5 rounded-pill bg-muted" aria-hidden />
                Clip #{clipNum(clipId)}
              </Link>
            ))}
          </div>
        )}

        {/* Moments */}
        {moments.length > 0 && (
          <div className="space-y-2">
            {moments.map((m, i) => (
              <MomentChip
                key={i}
                moment={m}
                jobId={jobId}
                clips={clips}
                chapterClipIds={clipIds}
              />
            ))}
          </div>
        )}
      </div>
    </details>
  );
}

// ─── Legend ───────────────────────────────────────────────────────────────────
function Legend() {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-muted">
      {KIND_KEYS.map((k) => (
        <span key={k} className="flex items-center gap-1.5">
          <span
            className={`size-2 rounded-pill ${KIND_COLOR[k].dot}`}
            aria-hidden
          />
          {KIND_COLOR[k].label}
        </span>
      ))}
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────
export function VideoMap({
  jobId,
  clips = [],
}: {
  jobId: string;
  clips?: ClipOut[];
}) {
  const [map, setMap] = useState<VideoMap | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Mobile: collapsed by default; desktop (≥1024px): open.
  const defaultOpen = useMediaQuery("(min-width: 1024px)");

  const poll = (retry = false) => {
    setError(null);
    getVideoMap(jobId, retry)
      .then((data) => {
        setMap(data);
        if (data.status === "pending") {
          timerRef.current = setTimeout(() => poll(false), 2500);
        }
        if (data.status === "failed") {
          setError(data.error ?? "Couldn’t build the video map");
        }
      })
      .catch((err: unknown) => {
        setError(
          err instanceof Error ? err.message : "Failed to load the video map",
        );
      });
  };

  useEffect(() => {
    poll(false);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  const chapters = map?.chapters ?? [];
  const hasContent =
    map?.status === "done" && (map.narrative || chapters.length > 0);

  // Масштаб анализа → ощущение ценности («мы прочитали ВСЁ видео и нашли N моментов»).
  const momentCount = chapters.reduce((n, ch) => n + (ch.moments?.length ?? 0), 0);
  const summaryLine =
    hasContent && (chapters.length > 0 || momentCount > 0)
      ? [
          chapters.length > 0 && `${chapters.length} chapter${chapters.length === 1 ? "" : "s"}`,
          momentCount > 0 && `${momentCount} key moment${momentCount === 1 ? "" : "s"}`,
          clips.length > 0 && `${clips.length} clip${clips.length === 1 ? "" : "s"} cut from them`,
        ]
          .filter(Boolean)
          .join(" · ")
      : null;

  return (
    <div className="mb-6 rounded-lg border border-line bg-surface overflow-hidden">
      {/* Top-level collapsible: closed on mobile, open on desktop */}
      <details open={defaultOpen} className="group">
        <summary
          className="flex cursor-pointer list-none items-center justify-between gap-3 px-5 py-4 text-ink [&::-webkit-details-marker]:hidden"
          style={{ minHeight: "48px" }}
        >
          <div className="min-w-0 flex-1">
            <Eyebrow tone="faint">Video map</Eyebrow>
            <span className="mt-1.5 block font-display text-h3 tracking-tight text-ink">
              Why these clips are worth it
            </span>
            {summaryLine ? (
              <span className="mt-1 block truncate font-mono text-xs tabular-nums text-muted">
                {summaryLine}
              </span>
            ) : (
              <span className="mt-1 block truncate text-xs text-muted">
                The full picture of your video — and where every clip came from.
              </span>
            )}
          </div>
          <svg
            className="size-4 shrink-0 text-muted transition-transform duration-200 ease-snappy group-open:rotate-180"
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
          {/* Pending state */}
          {(!map || map.status === "pending") && !error && (
            <div className="px-5 py-4">
              <PendingSkeleton />
            </div>
          )}

          {/* Error state */}
          {error && (
            <div className="px-5 py-4 space-y-3">
              <p className="text-sm text-bad">{error}</p>
              <button
                onClick={() => poll(true)}
                className="inline-flex h-9 items-center gap-2 rounded-md bg-surface-2 border border-line px-3.5 text-sm font-semibold text-ink hover:border-line-strong transition-colors duration-150"
              >
                Retry
              </button>
            </div>
          )}

          {/* Empty state (done but no narrative/chapters) */}
          {map?.status === "done" &&
            !map.narrative &&
            chapters.length === 0 &&
            !error && (
              <div className="px-5 py-4">
                <p className="text-sm text-muted">No video map yet.</p>
              </div>
            )}

          {/* Done state. (The header subtitle already frames what this is; no second
              restated paragraph, no decorative coral rule.) */}
          {hasContent && (
            <div className="px-5 py-4 space-y-5">
              {/* Narrative */}
              {map!.narrative && (
                <p className="text-sm text-muted leading-relaxed">
                  {parseNarrative(map!.narrative, jobId, clips)}
                </p>
              )}

              {/* Chapters accordion */}
              {chapters.length > 0 && (
                <div className="rounded-lg border border-line overflow-hidden">
                  <div className="flex items-center justify-between px-4 py-2.5 bg-surface-2 border-b border-line">
                    <Eyebrow tone="faint">Chapters</Eyebrow>
                    <Legend />
                  </div>
                  {chapters.map((ch, i) => (
                    <ChapterItem
                      key={i}
                      chapter={ch}
                      jobId={jobId}
                      clips={clips}
                    />
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </details>
    </div>
  );
}
