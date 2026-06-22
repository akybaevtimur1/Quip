"use client";

import { useRef } from "react";
import { mmss } from "@/lib/format";

// ────────────────────────────────────────────────────────────────────────────
// CoWatch — "watch the AI read your video" view shown DURING processing (Part 4).
//
// The source plays immediately (the user's own video) and the moments the AI flags surface as
// quote chips ON the video — the real line it caught + a tag — rising in as they're found. No
// abstract timeline bar: the eye stays on the content, and each marker carries meaning (the
// actual phrase), not just a color. PURELY VISUAL: these never influence clip selection.
// Presentational only — the container polls the worker and feeds `moments` in (newest last).
// ────────────────────────────────────────────────────────────────────────────

export type Moment = {
  t: number; // seconds from source start
  kind: "question" | "stat" | "emphasis" | "beat";
  intensity: number; // 0..1
  text?: string; // the real phrase the AI caught (chip body); empty → tag only
};

const KIND: Record<Moment["kind"], { dot: string; label: string }> = {
  question: { dot: "bg-sky-400", label: "Question" },
  emphasis: { dot: "bg-accent", label: "Big moment" },
  stat: { dot: "bg-emerald-400", label: "Number" },
  beat: { dot: "bg-amber-400", label: "Beat" },
};

const momentKey = (m: Moment) => `${m.kind}-${m.t}`;

export function CoWatch({
  src,
  moments,
  stageLabel,
  elapsed,
}: {
  /** Source video URL (ideally the local uploaded File via object URL → instant, no CORS). */
  src: string;
  /** Detected markers so far (grows as the worker finds more); newest LAST. */
  moments: Moment[];
  /** Current stage copy, e.g. "Transcribing" / "Finding the moments worth posting". */
  stageLabel: string;
  /** Elapsed seconds (mm:ss shown in the header). */
  elapsed: number;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  // The two most recent finds — newest is the prominent one, the prior sits above it, faded,
  // giving a gentle sense of a stream without cluttering the frame.
  const recent = moments.slice(-2);

  return (
    <div className="w-full max-w-3xl">
      <div className="mb-4 flex items-baseline justify-between gap-4">
        <h2 className="font-display text-2xl font-bold">Reading your video…</h2>
        <span className="font-mono text-sm text-muted">{mmss(elapsed)}</span>
      </div>

      <div className="relative overflow-hidden rounded-2xl border border-line bg-black">
        <video
          ref={videoRef}
          src={src}
          autoPlay
          muted
          loop
          playsInline
          className="aspect-video w-full object-contain"
        />

        {/* quote chips — the AI surfacing the real lines it catches, on the video */}
        <div className="pointer-events-none absolute inset-x-0 bottom-14 flex flex-col items-start gap-2 px-4">
          {recent.map((m, i) => {
            const newest = i === recent.length - 1;
            return (
              <div
                key={momentKey(m)}
                className={`max-w-[80%] rounded-xl border border-white/10 bg-black/60 px-3 py-2 backdrop-blur-md motion-safe:animate-[riseIn_360ms_var(--ease-snappy)] ${
                  newest ? "opacity-100" : "scale-95 opacity-45"
                }`}
              >
                <span className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-white/80">
                  <span className={`size-2 rounded-full ${KIND[m.kind].dot}`} />
                  {KIND[m.kind].label}
                </span>
                {m.text && (
                  <p className="mt-0.5 text-[15px] font-semibold leading-snug text-white">
                    “{m.text}”
                  </p>
                )}
              </div>
            );
          })}
        </div>

        {/* stage + count strip */}
        <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-center gap-2 bg-gradient-to-t from-black/75 to-transparent px-4 py-3">
          <span className="size-2 animate-pulse rounded-full bg-accent" />
          <span className="text-sm font-medium text-white/90">{stageLabel}</span>
          <span className="ml-auto font-mono text-xs text-white/60">
            {moments.length} moment{moments.length === 1 ? "" : "s"} found
          </span>
        </div>
      </div>

      <p className="mt-3 text-center text-xs text-muted">
        Your clips appear here as soon as they’re cut — hooks and scores first, video as it renders.
      </p>
    </div>
  );
}
