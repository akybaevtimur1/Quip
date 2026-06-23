"use client";

import { Check, Loader2, Pencil } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ExportMenu } from "@/components/ExportMenu";
import { Card } from "@/components/ui/Card";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { Numeral } from "@/components/ui/Numeral";
import { Stat } from "@/components/ui/Stat";
import { clipRange } from "@/lib/format";
import type { ClipOut } from "@/lib/types";
import { ClipPreview } from "./ClipPreview";
import { PendingThumb } from "./PendingThumb";
import { ReasonChip } from "./ReasonChip";

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

const WORKER_BASE = process.env.NEXT_PUBLIC_WORKER_URL ?? "";

export function resolveUrl(videoUrl: string): string {
  if (videoUrl.startsWith("http") || videoUrl.startsWith("/")) return videoUrl;
  return `${WORKER_BASE}/${videoUrl}`;
}

export function ClipCard({
  jobId,
  clip,
  selected,
  onToggle,
  topClip = false,
}: {
  jobId: string;
  clip: ClipOut;
  selected: boolean;
  onToggle: () => void;
  /** The single highest-scoring clip in the grid — gets the one coral score meter (the
   *  scarce "peak reading" signal). Every other card uses a neutral meter. */
  topClip?: boolean;
}) {
  // A clip whose render hasn't finished arrives with an empty video_url: its metadata
  // (hook/reason/score) is final, but it's not yet playable or editable. Show the card so
  // the user sees it's coming — with a skeleton over the video area instead of the player.
  const pending = !clip.video_url;
  const videoSrc = pending ? "" : resolveUrl(clip.video_url);

  // ── arrival animation (per card instance; ClipGrid mounts one <ClipCard key=id>) ──
  // `mounted` drives a one-time fade + scale "pop" on mount via Tailwind transition.
  // `displayScore` counts up 0 → clip.score on first appearance. Both respect
  // prefers-reduced-motion → final values are the INITIAL state (no animation, no
  // synchronous setState in the effect — which the React Compiler lint forbids).
  const reduced = prefersReducedMotion();
  const [mounted, setMounted] = useState(reduced);
  const [displayScore, setDisplayScore] = useState(() => (reduced ? clip.score : 0));

  useEffect(() => {
    if (prefersReducedMotion()) return;

    // Trigger the enter transition on the next frame so the initial (hidden) state paints.
    const raf = requestAnimationFrame(() => setMounted(true));

    // Count the score up over ~600ms with rAF; clean up on unmount.
    const target = clip.score;
    const duration = 600;
    let start: number | null = null;
    let countRaf = 0;
    const tick = (ts: number) => {
      if (start === null) start = ts;
      const t = Math.min(1, (ts - start) / duration);
      // easeOutCubic for a snappy settle.
      const eased = 1 - (1 - t) ** 3;
      setDisplayScore(target * eased);
      if (t < 1) countRaf = requestAnimationFrame(tick);
      else setDisplayScore(target);
    };
    countRaf = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(raf);
      cancelAnimationFrame(countRaf);
    };
  }, [clip.score]);

  // Score reads as a confidence reading out of 100 (mirrors the editor's "% match").
  // Coral meter only for the single top clip; pending clips keep a calm neutral meter.
  const score100 = Math.round(displayScore * 100);
  const meterTone = pending ? "neutral" : topClip ? "accent" : "neutral";

  return (
    <Card
      selected={!pending && selected}
      className={`flex flex-col overflow-hidden transition duration-200 ease-snappy ${
        // Reserve opacity ONLY for genuinely-pending clips; ready clips are full opacity
        // (the grid must read as finished, not disabled — selection is the ring, not dimming).
        pending ? "opacity-90" : "opacity-100"
      } ${mounted ? "translate-y-0 scale-100 opacity-100" : "translate-y-1 scale-95 opacity-0"}`}
    >
      {/* ── video preview: SAME caption engine as the editor (libass + the real ASS),
          so the grid shows the hook + captions exactly like the editor / export ── */}
      <div className="relative">
        {pending ? (
          // Clip still rendering: frame-grab a poster from the preview proxy (falls back to a
          // skeleton until ready). Keeps the 9:16 frame so the grid doesn't reflow when this
          // card flips to its real player.
          <PendingThumb jobId={jobId} clipStart={clip.start} />
        ) : (
          <ClipPreview
            src={videoSrc}
            jobId={jobId}
            clipId={clip.id}
            words={clip.words}
            clipStart={clip.start}
          />
        )}
        <span className="pointer-events-none absolute left-2 top-2 z-40">
          <ReasonChip type={clip.type} />
        </span>
        {/* select button (custom-styled checkbox affordance over the video) — hidden while
            pending: a not-yet-rendered clip can't be selected/downloaded. */}
        {!pending && (
          <button
            type="button"
            onClick={onToggle}
            aria-pressed={selected}
            aria-label={selected ? "Deselect" : "Select"}
            className={`absolute right-2 top-2 z-40 inline-flex size-7 items-center justify-center rounded-sm border transition duration-150 ease-snappy active:scale-95 ${
              selected
                ? "border-accent bg-accent text-white"
                : "border-line-strong bg-bg/70 text-transparent backdrop-blur hover:border-accent/60 hover:text-white/40"
            }`}
          >
            <Check className="size-4" strokeWidth={3} />
          </button>
        )}
      </div>

      {/* ── meta: a spec sheet for the clip — 3 tiers separated by hairlines ──
          flex-1 so every card body fills the equal-height grid cell; the action row below is
          pinned with mt-auto and the variable text is line-clamped → the button never "jumps"
          between cards and doesn't jitter as a clip flips rendering→ready. */}
      <div className="flex flex-1 flex-col p-3.5">
        {/* tier 1 — the signature score Stat + the timecode (the instrument header).
            The score uses the SAME <Stat> motif (value + /100 + thin meter) as everywhere
            a clip's strength is shown, so it's instantly recognizable. Coral value+meter
            ONLY on the single top clip; every other card is calm neutral. */}
        <div className="flex items-start justify-between gap-3">
          <Stat
            className="min-w-0"
            size="sm"
            label="Confidence"
            value={score100}
            suffix="/100"
            tone={topClip && !pending ? "accent" : "ink"}
            meter={displayScore}
            meterTone={meterTone}
          />
          <Numeral className="shrink-0 pt-0.5 text-xs text-muted">
            {clipRange(clip.start, clip.end)}
          </Numeral>
        </div>

        {/* tier 2 — the hook: the one large line that sells the clip. */}
        {clip.hook && (
          <p className="mt-3.5 line-clamp-2 text-[15px] font-bold leading-tight text-ink">
            “{clip.hook}”
          </p>
        )}

        {/* tier 3 — reasoning, a quieter block under a hairline. */}
        <div className="mt-3.5 border-t border-line pt-3">
          <Eyebrow tone="faint">Why it works</Eyebrow>
          <p className="mt-1.5 line-clamp-3 text-sm leading-snug text-muted">
            {clip.why_works ?? clip.reason}
          </p>
          {clip.transcript && (
            <p className="mt-2 line-clamp-2 text-xs leading-snug text-faint">“{clip.transcript}”</p>
          )}
        </div>

        {/* actions — mt-auto pins this row to the card bottom regardless of body length, so the
            button aligns across all cards and stays put through rendering→ready. */}
        {pending ? (
          // No export / edit until the clip is rendered (no video file yet). A muted
          // "Rendering…" affordance keeps the card's footer height stable.
          <div className="mt-4 flex items-center justify-center gap-1.5 rounded-sm border border-line bg-surface-2 px-3 py-2 text-sm font-semibold text-muted">
            <Loader2 className="size-4 animate-spin" />
            Rendering…
          </div>
        ) : (
          <div className="mt-4 flex gap-2">
            {/* Export menu (subtitles / none / .srt) — opens UPWARD so it isn't clipped by
                neighbouring grid cards. No "Render" on the grid → "With subtitles" renders on
                the fly from the current edit-state (no bakedUrl — D1). */}
            <ExportMenu
              jobId={jobId}
              clipId={clip.id}
              align="left"
              placement="up"
              className="flex-1"
            />
            {/* Editor page: return via "← All clips" (/?job=) or Back — the grid is
                restored by deep-link, nothing is lost. */}
            <Link
              href={`/edit/${jobId}/${clip.id}`}
              className="inline-flex items-center justify-center gap-1.5 rounded-sm border border-line bg-surface-2 px-3 py-2 text-sm font-semibold text-ink transition duration-200 ease-snappy hover:-translate-y-px hover:border-line-strong hover:bg-surface-3"
            >
              <Pencil className="size-4" />
              Edit
            </Link>
          </div>
        )}
      </div>
    </Card>
  );
}
