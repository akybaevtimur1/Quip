"use client";

import { Check, Gauge, Loader2, Pencil, Sparkles } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ExportMenu } from "@/components/ExportMenu";
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
}: {
  jobId: string;
  clip: ClipOut;
  selected: boolean;
  onToggle: () => void;
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

  // Resting opacity once mounted (pending/selected/idle). Before mount we force
  // opacity-0 for the fade-in; afterwards the resting value takes over.
  const restOpacity = pending ? "opacity-90" : selected ? "opacity-100" : "opacity-55 hover:opacity-80";

  return (
    <article
      className={`flex flex-col rounded-lg border bg-surface transition duration-200 ease-snappy ${
        pending ? "border-line" : selected ? "border-accent/60 ring-1 ring-accent/30" : "border-line"
      } ${
        mounted ? `translate-y-0 scale-100 ${restOpacity}` : "translate-y-1 scale-95 opacity-0"
      }`}
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
                : "border-line-strong bg-bg/70 text-transparent backdrop-blur hover:border-accent/60 hover:text-white/30"
            }`}
          >
            <Check className="size-4" strokeWidth={3} />
          </button>
        )}
      </div>

      {/* ── meta: структурный reasoning (объяснимость = наш отличитель) ──
          flex-1 so every card body fills the equal-height grid cell; the action row below is
          pinned with mt-auto and the variable text is line-clamped → the button never "jumps"
          between cards and doesn't jitter as a clip flips rendering→ready. */}
      <div className="flex flex-1 flex-col gap-2.5 p-3">
        <div className="flex items-center justify-between">
          <span className="font-mono text-xs text-muted">{clipRange(clip.start, clip.end)}</span>
          <span
            className="inline-flex items-center gap-1 font-mono text-sm font-semibold text-ink"
            title="AI confidence that this clip works as a short"
          >
            <Gauge className="size-3.5 text-muted" />
            {displayScore.toFixed(2)}
          </span>
        </div>

        {/* хук-заголовок (топ-текст клипа) — clamp to 2 lines so a long hook can't push the
            footer down on one card relative to its neighbours. */}
        {clip.hook && (
          <p className="flex items-start gap-1.5 text-[15px] font-bold leading-tight text-ink">
            <Sparkles className="mt-0.5 size-4 shrink-0 text-accent" />
            <span className="line-clamp-2">«{clip.hook}»</span>
          </p>
        )}

        {/* почему сработает (структурно, не один blob) — clamp to 3 lines for equal body height */}
        <div className="space-y-1">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">
            Why it works
          </p>
          <p className="line-clamp-3 text-sm leading-snug text-ink">{clip.why_works ?? clip.reason}</p>
        </div>

        {clip.transcript && (
          <p className="line-clamp-2 text-xs leading-snug text-muted">«{clip.transcript}»</p>
        )}

        {/* actions — mt-auto pins this row to the card bottom regardless of body length, so the
            button aligns across all cards and stays put through rendering→ready. */}
        {pending ? (
          // No export / edit until the clip is rendered (no video file yet). A muted
          // "Rendering…" affordance keeps the card's footer height stable.
          <div className="mt-auto flex items-center justify-center gap-1.5 rounded-sm border border-line bg-surface-2 px-3 py-2 text-sm font-semibold text-muted">
            <Loader2 className="size-4 animate-spin" />
            Rendering…
          </div>
        ) : (
          <div className="mt-auto flex gap-2 pt-1">
            {/* Меню экспорта (с субтитрами / без / .srt) — открывается ВВЕРХ, чтобы не
                перекрываться соседними карточками грида. На гриде нет «Рендер» → «С субтитрами»
                рендерится на лету из текущего edit-state (bakedUrl не передаём — D1). */}
            <ExportMenu
              jobId={jobId}
              clipId={clip.id}
              align="left"
              placement="up"
              className="flex-1"
            />
            {/* Страница-редактор: возврат через «← Все клипы» (/?job=) или Back —
                грид восстанавливается deep-link'ом, ничего не теряется. */}
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
    </article>
  );
}
