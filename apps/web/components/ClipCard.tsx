"use client";

import { Check, Loader2, Pencil } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ExportMenu } from "@/components/ExportMenu";
import { Card } from "@/components/ui/Card";
import { Numeral } from "@/components/ui/Numeral";
import { clipRange } from "@/lib/format";
import type { ClipOut } from "@/lib/types";
import { ClipPreview } from "./ClipPreview";
import { PendingThumb } from "./PendingThumb";

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

const TONE_GLOW: Record<string, { border: string; shadow: string }> = {
  shocking:     { border: '#2a1515', shadow: '0 0 0 1px rgba(255,70,70,0.14), 0 0 18px rgba(255,70,70,0.09), inset 0 0 28px rgba(255,60,60,0.04)' },
  funny:        { border: '#2a2510', shadow: '0 0 0 1px rgba(250,204,21,0.14), 0 0 18px rgba(250,204,21,0.09), inset 0 0 28px rgba(250,200,20,0.04)' },
  touching:     { border: '#1e1228', shadow: '0 0 0 1px rgba(192,132,252,0.14), 0 0 18px rgba(192,132,252,0.09), inset 0 0 28px rgba(192,132,252,0.04)' },
  relatable:    { border: '#131d13', shadow: '0 0 0 1px rgba(74,222,128,0.14), 0 0 18px rgba(74,222,128,0.09), inset 0 0 28px rgba(74,222,128,0.04)' },
  inspiring:    { border: '#1a1710', shadow: '0 0 0 1px rgba(251,146,60,0.14), 0 0 18px rgba(251,146,60,0.09), inset 0 0 28px rgba(251,146,60,0.04)' },
  controversial:{ border: '#160e20', shadow: '0 0 0 1px rgba(167,139,250,0.14), 0 0 18px rgba(167,139,250,0.09), inset 0 0 28px rgba(167,139,250,0.04)' },
  insightful:   { border: '#101820', shadow: '0 0 0 1px rgba(56,189,248,0.14), 0 0 18px rgba(56,189,248,0.09), inset 0 0 28px rgba(56,189,248,0.04)' },
};

const TONE_EMOJI: Record<string, string> = {
  shocking: '😮', funny: '😂', touching: '🥺',
  relatable: '🙌', inspiring: '🔥', controversial: '🤔', insightful: '💡',
};

function computeSignalBars(clip: ClipOut): { label: string; bars: number }[] {
  const score = clip.score;
  return [
    {
      label: 'Hook',
      bars: score >= 0.85 ? 4 : score >= 0.70 ? 3 : score >= 0.55 ? 2 : 1,
    },
    {
      label: 'Standalone',
      bars: ['hook', 'emotional_peak'].includes(clip.type) ? 4
          : clip.type === 'complete_thought' ? 3
          : clip.type === 'strong_quote' ? 3
          : 2,
    },
    {
      label: 'Energy',
      bars: ['shocking', 'funny', 'controversial'].includes(clip.tone ?? '') ? 4
          : ['inspiring', 'relatable', 'insightful'].includes(clip.tone ?? '') ? 3
          : clip.tone === 'touching' ? 2
          : 1,
    },
    {
      label: 'Speaker',
      bars: (clip.hook?.length ?? 0) > 60 ? 3 + (clip.why_works ? 1 : 0)
          : (clip.hook?.length ?? 0) > 30 ? 2 + (clip.why_works ? 1 : 0)
          : 1 + (clip.why_works ? 1 : 0),
    },
  ].map(s => ({ ...s, bars: Math.min(4, Math.max(1, s.bars)) }));
}

function getScoreTier(score100: number): { textClass: string; gradient: string; glow: string } {
  if (score100 >= 90) return {
    textClass: 'text-emerald-400',
    gradient: 'linear-gradient(90deg, rgba(74,222,128,0.55) 0%, #4ade80 55%, #86efac 100%)',
    glow: '0 0 7px rgba(74,222,128,0.5)',
  };
  if (score100 >= 70) return {
    textClass: 'text-amber-400',
    gradient: 'linear-gradient(90deg, rgba(251,191,36,0.55) 0%, #fbbf24 55%, #fde68a 100%)',
    glow: '0 0 7px rgba(251,191,36,0.5)',
  };
  if (score100 >= 50) return {
    textClass: 'text-orange-400',
    gradient: 'linear-gradient(90deg, rgba(251,146,60,0.55) 0%, #fb923c 55%, #fdba74 100%)',
    glow: '0 0 7px rgba(251,146,60,0.4)',
  };
  return {
    textClass: 'text-rose-400',
    gradient: 'linear-gradient(90deg, rgba(251,113,133,0.55) 0%, #fb7185 55%, #fda4af 100%)',
    glow: '0 0 7px rgba(251,113,133,0.4)',
  };
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
  topClip?: boolean;
}) {
  const pending = !clip.video_url;
  const videoSrc = pending ? "" : resolveUrl(clip.video_url);

  const reduced = prefersReducedMotion();
  const [mounted, setMounted] = useState(reduced);
  const [displayScore, setDisplayScore] = useState(() => (reduced ? clip.score : 0));
  const [open, setOpen] = useState(false);
  const originalStart = useRef(clip.start);
  const originalEnd = useRef(clip.end);
  const [analysisStale, setAnalysisStale] = useState(false);

  useEffect(() => {
    if (prefersReducedMotion()) return;

    const raf = requestAnimationFrame(() => setMounted(true));

    const target = clip.score;
    const duration = 600;
    let start: number | null = null;
    let countRaf = 0;
    const tick = (ts: number) => {
      if (start === null) start = ts;
      const t = Math.min(1, (ts - start) / duration);
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

  useEffect(() => {
    const movedStart = Math.abs(clip.start - originalStart.current) > 5;
    const movedEnd = Math.abs(clip.end - originalEnd.current) > 5;
    setAnalysisStale(movedStart || movedEnd);
  }, [clip.start, clip.end]);

  const score100 = Math.round(displayScore * 100);
  const tier = analysisStale ? null : getScoreTier(score100);
  const glow = (!analysisStale && clip.tone && TONE_GLOW[clip.tone]) || null;
  const emoji = clip.tone && TONE_EMOJI[clip.tone];

  const handleRefresh = async () => {
    try {
      const res = await fetch(
        `${WORKER_BASE}/jobs/${jobId}/clips/${clip.id}/refresh-analysis`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ start: clip.start, end: clip.end }),
        }
      );
      if (!res.ok) return;
      originalStart.current = clip.start;
      originalEnd.current = clip.end;
      setAnalysisStale(false);
    } catch {
      // silently ignore — stale banner stays
    }
  };

  return (
    <Card
      selected={!pending && selected}
      style={{ borderColor: glow?.border, boxShadow: glow?.shadow }}
      className={`flex flex-col overflow-hidden transition duration-200 ease-snappy ${
        pending ? "opacity-90" : "opacity-100"
      } ${mounted ? "translate-y-0 scale-100 opacity-100" : "translate-y-1 scale-95 opacity-0"}`}
    >
      {/* ── video preview ── */}
      <div className="relative">
        {pending ? (
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
        {emoji && !analysisStale && (
          <span
            className="pointer-events-none absolute left-2 top-2 z-40 select-none rounded-md text-[22px] leading-none"
            style={{ padding: '3px 4px', background: 'rgba(0,0,0,0.62)' }}
          >
            {emoji}
          </span>
        )}
        {!pending && (
          <button
            type="button"
            onClick={onToggle}
            aria-pressed={selected}
            aria-label={selected ? "Deselect" : "Select"}
            className={`absolute right-2 top-2 z-40 inline-flex size-7 items-center justify-center rounded-sm border transition duration-150 ease-snappy active:scale-95 ${
              selected
                ? "border-ink bg-ink text-bg"
                : "border-line-strong bg-bg/70 text-transparent backdrop-blur hover:border-line-strong hover:text-ink/40"
            }`}
          >
            <Check className="size-4" strokeWidth={3} />
          </button>
        )}
      </div>

      <div className="flex flex-1 flex-col p-3.5">
        {/* ── score + timecode ── */}
        <div className="flex items-start justify-between gap-3">
          <div className="mb-2.5 min-w-0">
            <div className="flex items-baseline gap-0.5 mb-1.5">
              <span className={`text-[28px] font-extrabold leading-none tabular-nums ${tier?.textClass ?? 'text-surface-3'}`}>
                {score100}
              </span>
              <span className="text-xs text-muted">/100</span>
            </div>
            <div className="h-1 bg-surface-2 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full ${analysisStale ? 'bg-surface-3' : ''}`}
                style={tier ? {
                  width: `${displayScore * 100}%`,
                  background: tier.gradient,
                  boxShadow: tier.glow,
                } : undefined}
              />
            </div>
          </div>
          <Numeral className="shrink-0 pt-0.5 text-xs text-muted">
            {clipRange(clip.start, clip.end)}
          </Numeral>
        </div>

        {/* ── hook ── */}
        {clip.hook && (
          <p className={`mt-3.5 line-clamp-2 text-[15px] font-bold leading-tight ${analysisStale ? 'text-muted/40' : 'text-ink'}`}>
            &ldquo;{clip.hook}&rdquo;
          </p>
        )}

        {/* ── key moment or stale banner ── */}
        {clip.key_quote && !analysisStale && (
          <div className="mt-3 rounded-sm border-l-2 border-emerald-500 bg-emerald-950/40 px-2.5 py-1.5">
            <p className="mb-1 text-[7px] font-bold uppercase tracking-widest text-emerald-500">
              ★ Key moment
            </p>
            <p className="text-[10px] italic leading-relaxed text-emerald-200">
              &ldquo;{clip.key_quote}&rdquo;
            </p>
          </div>
        )}
        {analysisStale && (
          <div className="mt-3 flex items-center justify-between gap-2 rounded-sm border border-line bg-surface-2 px-2 py-1.5">
            <span className="text-[9px] text-muted">Clip moved · AI analysis may be outdated</span>
            <button
              onClick={handleRefresh}
              className="shrink-0 rounded border border-amber-400/20 bg-amber-400/10 px-1.5 py-0.5 text-[9px] font-bold text-amber-400"
            >
              ↻ Refresh
            </button>
          </div>
        )}

        {/* ── accordion ── */}
        <button
          type="button"
          onClick={() => setOpen(o => !o)}
          className="mt-2 text-[10px] text-muted hover:text-ink transition-colors"
        >
          {open ? 'Why this clip ↑' : 'Why this clip ↓'}
        </button>

        {open && (
          <div className="mt-2 space-y-2 border-t border-line pt-2">
            <p className="text-[7.5px] font-bold uppercase tracking-wider text-muted">Quality signals</p>
            <div className="flex gap-2">
              {computeSignalBars(clip).map(({ label, bars }) => (
                <div key={label} className="flex flex-1 flex-col items-center gap-1">
                  <div className="flex h-3.5 items-end gap-0.5">
                    {[4, 7, 11, 14].map((h, i) => (
                      <div
                        key={i}
                        className="w-1 rounded-[1px]"
                        style={{
                          height: h,
                          background: (!analysisStale && i < bars) ? '#4ade80' : '#262626',
                        }}
                      />
                    ))}
                  </div>
                  <span className="text-center text-[7px] text-muted">{label}</span>
                </div>
              ))}
            </div>
            <p className={`border-t border-line pt-2 text-[10.5px] leading-relaxed ${analysisStale ? 'text-muted/30' : 'text-muted'}`}>
              {clip.why_works ?? clip.reason}
            </p>
          </div>
        )}

        {/* ── actions ── */}
        {pending ? (
          <div className="mt-4 flex items-center justify-center gap-1.5 rounded-sm border border-line bg-surface-2 px-3 py-2 text-sm font-semibold text-muted">
            <Loader2 className="size-4 animate-spin" />
            Rendering…
          </div>
        ) : (
          <div className="mt-4 flex gap-2">
            <ExportMenu
              jobId={jobId}
              clipId={clip.id}
              align="left"
              placement="up"
              className="flex-1"
            />
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
