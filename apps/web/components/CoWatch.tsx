"use client";

import { useRef } from "react";
import type { BadgeTone } from "@/components/ui/Badge";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { Numeral } from "@/components/ui/Numeral";
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

// Map each detected kind onto a palette token (no off-palette sky/emerald/amber):
// question→quote, stat→thought, beat→warn, emphasis→accent (the one "big moment" signal).
const KIND: Record<Moment["kind"], { tone: BadgeTone; label: string }> = {
  question: { tone: "quote", label: "Question" },
  emphasis: { tone: "accent", label: "Big moment" },
  stat: { tone: "thought", label: "Number" },
  beat: { tone: "warn", label: "Beat" },
};

// Token-keyed dot color for the on-video chips (white text on black, so the chip body
// can't use Badge's tinted variant — only the dot carries the kind color). Literal
// strings so Tailwind extracts them.
const DOT: Record<BadgeTone, string> = {
  hook: "bg-hook",
  peak: "bg-peak",
  thought: "bg-thought",
  quote: "bg-quote",
  ok: "bg-ok",
  warn: "bg-warn",
  bad: "bg-bad",
  accent: "bg-accent",
  neutral: "bg-muted",
};
const dotClass = (tone: BadgeTone) => DOT[tone];

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
      <div className="mb-4 flex items-end justify-between gap-4 border-b border-line pb-3">
        <div>
          <Eyebrow tone="accent">Reading source</Eyebrow>
          <h2 className="mt-1.5 font-display text-h3 text-ink">Watching the AI read your video</h2>
        </div>
        <div className="text-right" aria-live="polite">
          <Eyebrow tone="faint" className="block">
            Elapsed
          </Eyebrow>
          <Numeral className="mt-1 block text-base text-muted">{mmss(elapsed)}</Numeral>
        </div>
      </div>

      <div className="relative overflow-hidden rounded-lg border border-line bg-black">
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
                className={`max-w-[80%] rounded-lg border border-white/10 bg-black/60 px-3 py-2 backdrop-blur-md motion-safe:animate-[riseIn_360ms_var(--ease-snappy)] ${
                  newest ? "opacity-100" : "scale-95 opacity-45"
                }`}
              >
                <span className="flex items-center gap-1.5 font-mono text-eyebrow uppercase text-white/80">
                  <span className={`size-1.5 shrink-0 rounded-pill ${dotClass(KIND[m.kind].tone)}`} />
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
        <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-center gap-2.5 bg-gradient-to-t from-black/80 to-transparent px-4 py-3">
          <span className="size-1.5 shrink-0 animate-pulse rounded-pill bg-accent" />
          <span className="font-mono text-eyebrow uppercase text-white/90">{stageLabel}</span>
          <span className="ml-auto font-mono tabular-nums text-xs text-white/60">
            {moments.length} moment{moments.length === 1 ? "" : "s"}
          </span>
        </div>
      </div>

      <p className="mt-3 text-xs leading-relaxed text-muted">
        Clips appear here as they’re cut — hook and score first, video as each one renders.
      </p>
    </div>
  );
}
