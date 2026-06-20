"use client";

import { useEffect, useRef, useState } from "react";

// ────────────────────────────────────────────────────────────────────────────
// CoWatch — "watch the AI analyze your video" view shown DURING processing (Part 4).
//
// The source plays immediately (the user's own video), a scan playhead follows it, and
// detected "moments" (cosmetic markers from the worker's heuristic — see preview_moments.py)
// light up on the timeline as they arrive. Markers are PURELY VISUAL: they never influence
// the AI clip selection. Presentational only — the container polls and feeds `moments` in.
// ────────────────────────────────────────────────────────────────────────────

export type Moment = {
  t: number; // seconds from source start
  kind: "question" | "stat" | "emphasis" | "beat";
  intensity: number; // 0..1
};

const KIND: Record<Moment["kind"], { dot: string; label: string }> = {
  question: { dot: "bg-sky-400", label: "Question" },
  emphasis: { dot: "bg-accent", label: "Emphasis" },
  stat: { dot: "bg-emerald-400", label: "Stat" },
  beat: { dot: "bg-amber-400", label: "Beat" },
};

const momentKey = (m: Moment) => `${m.kind}-${m.t}`;

export function CoWatch({
  src,
  moments,
  durationSec,
  stageLabel,
  elapsed,
}: {
  /** Source video URL (ideally the local uploaded File via object URL → instant, no CORS). */
  src: string;
  /** Detected markers so far (grows as the worker finds more). */
  moments: Moment[];
  /** Source duration (seconds) for positioning markers; falls back to the video's own duration. */
  durationSec?: number;
  /** Current stage copy, e.g. "Transcribing" / "Finding the moments worth posting". */
  stageLabel: string;
  /** Elapsed seconds (mm:ss shown in the overlay). */
  elapsed: number;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [pos, setPos] = useState(0); // playhead fraction 0..1
  const [dur, setDur] = useState(durationSec ?? 0);

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    const onTime = () => {
      const d = durationSec || v.duration || 0;
      if (d > 0) setPos(Math.min(1, v.currentTime / d));
    };
    const onMeta = () => setDur(durationSec || v.duration || 0);
    v.addEventListener("timeupdate", onTime);
    v.addEventListener("loadedmetadata", onMeta);
    return () => {
      v.removeEventListener("timeupdate", onTime);
      v.removeEventListener("loadedmetadata", onMeta);
    };
  }, [durationSec]);

  const total = durationSec || dur || 0;
  const mm = Math.floor(elapsed / 60);
  const ss = String(elapsed % 60).padStart(2, "0");

  return (
    <div className="w-full max-w-3xl">
      <div className="mb-4 flex items-baseline justify-between gap-4">
        <h2 className="font-display text-2xl font-bold">Reading your video…</h2>
        <span className="font-mono text-sm text-muted">
          {mm}:{ss}
        </span>
      </div>

      {/* source playing — the user co-watches while the AI works */}
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
        <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-center gap-2 bg-gradient-to-t from-black/70 to-transparent px-4 py-3">
          <span className="size-2 animate-pulse rounded-full bg-accent" />
          <span className="text-sm font-medium text-white/90">{stageLabel}</span>
          <span className="ml-auto font-mono text-xs text-white/60">
            {moments.length} moment{moments.length === 1 ? "" : "s"} found
          </span>
        </div>
      </div>

      {/* timeline: scan playhead + markers lighting up as they're found */}
      <div className="relative mt-4 h-12 rounded-xl border border-line bg-surface-2">
        {/* scan playhead (follows the playing source) */}
        <div
          className="absolute top-0 z-20 h-full w-px bg-accent/80 transition-[left] duration-200 ease-linear"
          style={{ left: `${pos * 100}%` }}
        >
          <span className="absolute -top-1 left-1/2 size-2 -translate-x-1/2 rounded-full bg-accent shadow-[0_0_8px_var(--color-accent,#FF5A3D)]" />
        </div>
        {/* markers */}
        {total > 0 &&
          moments.map((m) => {
            const left = Math.min(100, Math.max(0, (m.t / total) * 100));
            const h = 30 + Math.round(m.intensity * 60); // taller = stronger
            // Each marker mounts once (stable key) → the popIn animation runs once, on arrival.
            // New markers animate; already-shown ones don't re-mount, so they don't re-animate.
            return (
              <div
                key={momentKey(m)}
                title={`${KIND[m.kind].label} · ${m.t.toFixed(1)}s`}
                className="absolute bottom-1 z-10 w-1 -translate-x-1/2 origin-bottom rounded-full motion-safe:animate-[popIn_320ms_ease-out]"
                style={{ left: `${left}%`, height: `${h}%` }}
              >
                <span
                  className={`block size-full rounded-full ${KIND[m.kind].dot}`}
                  style={{ opacity: 0.55 + m.intensity * 0.45 }}
                />
              </div>
            );
          })}
      </div>

      {/* legend */}
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted">
        {(Object.keys(KIND) as Moment["kind"][]).map((k) => (
          <span key={k} className="inline-flex items-center gap-1.5">
            <span className={`size-2 rounded-full ${KIND[k].dot}`} />
            {KIND[k].label}
          </span>
        ))}
        <span className="ml-auto">Your clips appear here as soon as they’re cut.</span>
      </div>
    </div>
  );
}
