"use client";

import Image from "next/image";
import { useEffect, useMemo, useRef, useState } from "react";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { Container } from "@/components/ui/Container";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { Numeral } from "@/components/ui/Numeral";
import { Section } from "@/components/ui/Section";
import { cn } from "@/lib/cn";

// ────────────────────────────────────────────────────────────────────────────
// Quip Studio — an interactive "show, don't tell" demo of the cutting logic.
// Pick a source → the playhead scans it → clips reveal, each with a reason. Hover
// a clip and its origin lights up on the timeline (and vice-versa). Autoplays once
// when scrolled into view; respects reduced-motion. The 4 clip-type colors live
// here (and in reason chips) — coral stays the primary brand elsewhere.
// ────────────────────────────────────────────────────────────────────────────

type ClipType = "hook" | "peak" | "thought" | "quote";

type DemoClip = {
  type: ClipType;
  left: number; // % position of its source moment on the timeline
  width: number; // % width
  time: string;
  title: string;
  text: string;
};

type Sample = { tab: string; file: string; duration: string; marks: [string, string, string]; clips: DemoClip[] };

// ClipType maps 1:1 to the Badge tones (same token names) — reuse the shared chip.
const BADGE_TONE: Record<ClipType, BadgeTone> = {
  hook: "hook",
  peak: "peak",
  thought: "thought",
  quote: "quote",
};
const ZONE_CLS: Record<ClipType, string> = {
  hook: "bg-hook/70",
  peak: "bg-peak/70",
  thought: "bg-thought/70",
  quote: "bg-quote/70",
};

const SAMPLES: Sample[] = [
  {
    tab: "Podcast · 42 min",
    file: "podcast-ep47.mp4",
    duration: "42:18",
    marks: ["00:00", "21:09", "42:18"],
    clips: [
      { type: "hook", left: 7, width: 13, time: "02:14–02:51", title: "Three years I filmed the wrong thing", text: "Strong hook — clear without the episode's context." },
      { type: "peak", left: 34, width: 12, time: "14:02–14:44", title: "The moment I almost quit", text: "Emotional peak — the viewer feels the stakes." },
      { type: "thought", left: 60, width: 12, time: "26:30–27:19", title: "Content isn't a lottery", text: "A complete thought you can watch on its own." },
      { type: "quote", left: 83, width: 11, time: "37:10–37:48", title: "Marketing is the truth", text: "A short quote for Reels or Shorts." },
    ],
  },
  {
    tab: "Interview · 28 min",
    file: "founder-interview.mp4",
    duration: "28:40",
    marks: ["00:00", "14:20", "28:40"],
    clips: [
      { type: "hook", left: 8, width: 12, time: "01:48–02:20", title: "I got fired at 22", text: "A personal hook that needs no backstory." },
      { type: "thought", left: 35, width: 12, time: "09:30–10:11", title: "Skill beats a diploma", text: "A complete thought with a clear point." },
      { type: "peak", left: 61, width: 11, time: "17:05–17:42", title: "I almost gave up", text: "An emotional scene before the payoff." },
      { type: "quote", left: 84, width: 11, time: "24:12–24:50", title: "Do it while it's embarrassing", text: "A short quote with a strong punch." },
    ],
  },
  {
    tab: "Vlog · 19 min",
    file: "creator-vlog.mp4",
    duration: "19:05",
    marks: ["00:00", "09:30", "19:05"],
    clips: [
      { type: "hook", left: 7, width: 12, time: "00:54–01:28", title: "Moved with no money", text: "A quick personal conflict in the first line." },
      { type: "peak", left: 35, width: 12, time: "06:40–07:18", title: "The first month was hell", text: "An emotional piece with clear stakes." },
      { type: "quote", left: 61, width: 12, time: "12:10–12:52", title: "The camera changes everything", text: "A quote you want to pull into a clip." },
      { type: "thought", left: 85, width: 10, time: "16:20–16:55", title: "Routine beats inspiration", text: "A complete point for an educational short." },
    ],
  },
];

type Phase = "idle" | "scanning" | "ready";

export function QuipStudio() {
  const [sampleIdx, setSampleIdx] = useState(0);
  const [phase, setPhase] = useState<Phase>("idle");
  const [linked, setLinked] = useState<number | null>(null);
  const [playhead, setPlayhead] = useState(4);

  const rootRef = useRef<HTMLDivElement>(null);
  const started = useRef(false);
  const timer = useRef<number | null>(null);

  const sample = SAMPLES[sampleIdx];

  // Deterministic waveform bars (no hydration mismatch — pure function of index).
  const bars = useMemo(
    () =>
      Array.from({ length: 56 }, (_, i) => {
        const h = 18 + Math.abs(Math.sin((i + sampleIdx) * 0.47) + Math.sin((i + sampleIdx) * 0.19)) * 34;
        return Math.min(88, Math.round(h));
      }),
    [sampleIdx],
  );

  const reduced = () =>
    typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function clearTimer() {
    if (timer.current !== null) {
      clearTimeout(timer.current);
      timer.current = null;
    }
  }

  function play(instant: boolean) {
    clearTimer();
    setLinked(null);
    if (instant) {
      setPhase("ready");
      return;
    }
    setPhase("scanning");
    setPlayhead(4);
    requestAnimationFrame(() => setPlayhead(94));
    timer.current = window.setTimeout(() => setPhase("ready"), 1900);
  }

  // Autoplay once when scrolled into view.
  useEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting && !started.current) {
            started.current = true;
            play(reduced());
            io.disconnect();
          }
        }
      },
      { threshold: 0.3 },
    );
    io.observe(el);
    return () => io.disconnect();
    // play is a stable closure here; we want this to run once on mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => clearTimer, []);

  function pickSample(i: number) {
    setSampleIdx(i);
    started.current = true;
    play(reduced());
  }

  const stateLabel =
    phase === "scanning" ? "finding moments…" : phase === "ready" ? `${sample.clips.length} clips ready` : "ready to upload";

  return (
    <Section id="demo" className="relative">
      <Container className="relative">
        <div className="mx-auto max-w-2xl text-center">
          <Eyebrow tone="accent" className="inline-flex items-center gap-2">
            <span className="size-1.5 rounded-pill bg-accent" aria-hidden />
            Live cutting logic
          </Eyebrow>
          <h2 className="mt-4 font-display text-h2 text-ink sm:text-display-lg">
            Here&rsquo;s how it cuts &mdash; and <span className="text-accent">why</span> exactly like that.
          </h2>
          <p className="mt-4 text-lead text-muted">
            A live mock of the cutting logic, not a screen recording. Hover a clip to trace it back to
            its moment.
          </p>
        </div>

        <div
          ref={rootRef}
          className="mx-auto mt-12 max-w-4xl overflow-hidden rounded-lg border border-line-strong bg-surface shadow-[0_32px_80px_-32px_rgba(0,0,0,.6)]"
        >
          {/* top bar: title + state + sample tabs */}
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-surface-2 px-5 py-4">
            <div>
              <p className="flex items-center gap-2 text-sm font-semibold text-ink">
                Quip Studio
                <Badge tone="neutral">Concept preview</Badge>
              </p>
              <p className="mt-1.5 flex items-center gap-2">
                <span
                  aria-hidden
                  className={cn(
                    "size-1.5 rounded-pill",
                    phase === "scanning" ? "bg-accent" : phase === "ready" ? "bg-ok" : "bg-line-strong",
                  )}
                />
                <Eyebrow tone="faint">{stateLabel}</Eyebrow>
              </p>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {SAMPLES.map((s, i) => (
                <button
                  key={s.file}
                  type="button"
                  onClick={() => pickSample(i)}
                  aria-pressed={i === sampleIdx}
                  className={cn(
                    "h-8 rounded-md border px-3 text-xs font-semibold outline-none transition-colors duration-180 ease-snappy",
                    "focus-visible:ring-2 focus-visible:ring-ink",
                    i === sampleIdx
                      ? "border-line-strong bg-surface-3 text-ink"
                      : "border-line-strong/60 text-muted hover:bg-surface-3 hover:text-ink",
                  )}
                >
                  {s.tab}
                </button>
              ))}
            </div>
          </div>

          {/* studio body */}
          <div className="flex flex-col gap-4 px-5 py-6">
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <Eyebrow tone="faint">Source</Eyebrow>
              <h3 className="font-mono text-sm text-ink">{sample.file}</h3>
              <Numeral className="ml-auto text-xs text-faint">{sample.duration}</Numeral>
            </div>

            {/* timeline */}
            <div className="relative h-12 overflow-hidden rounded-md border border-line bg-surface-3">
              <div className="flex h-full items-center gap-px px-1.5 opacity-35">
                {bars.map((h, i) => (
                  <span key={i} className="flex-1 rounded-sm bg-muted" style={{ height: `${h}%` }} />
                ))}
              </div>
              {/* clip-source zones (color-coded by type) */}
              {sample.clips.map((c, i) => (
                <button
                  key={i}
                  type="button"
                  onMouseEnter={() => setLinked(i)}
                  onMouseLeave={() => setLinked((v) => (v === i ? null : v))}
                  onClick={() => setLinked((v) => (v === i ? null : i))}
                  aria-label={`${c.type} clip source at ${c.time}`}
                  className={cn(
                    "absolute inset-y-1 grid place-items-center rounded-sm outline-none transition duration-180 ease-snappy",
                    ZONE_CLS[c.type],
                    linked === i
                      ? "ring-2 ring-ink ring-offset-1 ring-offset-surface-3"
                      : "ring-1 ring-inset ring-white/0 hover:ring-white/20 focus-visible:ring-2 focus-visible:ring-ink",
                  )}
                  style={{ left: `${c.left}%`, width: `${c.width}%` }}
                >
                  <span className="font-mono text-[9px] font-bold uppercase tracking-wider text-bg/90">
                    {c.type}
                  </span>
                </button>
              ))}
              {/* scanning playhead — the single live signal; the coral bar is enough,
                  no decorative glow */}
              <span
                aria-hidden
                className="absolute inset-y-0 w-0.5 rounded-pill bg-accent"
                style={{
                  left: `${playhead}%`,
                  opacity: phase === "scanning" ? 1 : 0,
                  transition: "left 1.9s cubic-bezier(.2,.8,.2,1), opacity .3s",
                }}
              />
            </div>
            <div className="flex justify-between">
              {sample.marks.map((m, i) => (
                <Numeral key={i} className="text-[10px] tracking-wide text-faint">
                  {m}
                </Numeral>
              ))}
            </div>

            {/* clip grid */}
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {sample.clips.map((c, i) => (
                <article
                  key={`${sampleIdx}-${i}`}
                  onMouseEnter={() => setLinked(i)}
                  onMouseLeave={() => setLinked((v) => (v === i ? null : v))}
                  onClick={() => setLinked((v) => (v === i ? null : i))}
                  className={cn(
                    "cursor-pointer overflow-hidden rounded-lg border bg-surface-2 transition duration-240 ease-snappy",
                    linked === i
                      ? "border-line-strong ring-1 ring-line-strong -translate-y-0.5"
                      : "border-line hover:border-line-strong",
                  )}
                  style={{
                    transitionDelay: phase === "ready" ? `${i * 90}ms` : "0ms",
                    opacity: phase === "ready" ? 1 : 0,
                    transform: phase === "ready" ? undefined : "translateY(12px)",
                  }}
                >
                  <div className="relative aspect-[9/16]">
                    <Image
                      src={`/clips/clip-${(i % 4) + 1}.webp`}
                      alt=""
                      fill
                      sizes="(min-width: 640px) 200px, 45vw"
                      className="object-cover"
                    />
                    <div className="absolute inset-0 bg-gradient-to-t from-black/75 via-transparent to-black/10" />
                    <Badge tone={BADGE_TONE[c.type]} className="absolute left-2 top-2 backdrop-blur-sm">
                      {c.type}
                    </Badge>
                    <p className="absolute inset-x-2 bottom-2 text-[12px] font-bold leading-tight text-white [text-shadow:0_1px_6px_rgba(0,0,0,.7)]">
                      {c.title}
                    </p>
                  </div>
                  <div className="px-2.5 py-2.5">
                    <Numeral className="block text-[10px] tracking-wide text-faint">{c.time}</Numeral>
                    <p className="mt-1 text-[11px] leading-snug text-muted">{c.text}</p>
                  </div>
                </article>
              ))}
            </div>

            <div className="flex justify-end">
              <button
                type="button"
                onClick={() => pickSample((sampleIdx + 1) % SAMPLES.length)}
                className="rounded-md border border-line-strong px-3 py-1.5 text-xs font-semibold text-muted outline-none transition-colors duration-180 ease-snappy hover:bg-surface-3 hover:text-ink focus-visible:ring-2 focus-visible:ring-ink"
              >
                Another example
              </button>
            </div>
          </div>
        </div>
      </Container>
    </Section>
  );
}
