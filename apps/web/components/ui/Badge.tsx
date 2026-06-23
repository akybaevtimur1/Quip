import { cn } from "@/lib/cn";

// Small status / clip-type chip keyed to the functional tokens (hook/peak/thought/quote)
// and semantics (ok/warn/bad/accent). One primitive so a color never means two things
// across CoWatch dots, ReasonChip, VideoMap legend, timeline and status pills.
// Class strings are literal (not interpolated) so Tailwind can statically extract them.
export type BadgeTone =
  | "hook"
  | "peak"
  | "thought"
  | "quote"
  | "ok"
  | "warn"
  | "bad"
  | "accent"
  | "neutral";

const toneClass: Record<BadgeTone, string> = {
  hook: "bg-hook/12 text-hook border-hook/25",
  peak: "bg-peak/12 text-peak border-peak/25",
  thought: "bg-thought/12 text-thought border-thought/25",
  quote: "bg-quote/12 text-quote border-quote/25",
  ok: "bg-ok/12 text-ok border-ok/25",
  warn: "bg-warn/12 text-warn border-warn/25",
  bad: "bg-bad/12 text-bad border-bad/25",
  accent: "bg-accent-tint text-accent border-accent-line",
  neutral: "bg-surface-2 text-muted border-line",
};

const dotClass: Record<BadgeTone, string> = {
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

export function Badge({
  tone = "neutral",
  dot = false,
  className,
  children,
}: {
  tone?: BadgeTone;
  dot?: boolean;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-pill border px-2.5 py-0.5 font-mono text-eyebrow uppercase",
        toneClass[tone],
        className,
      )}
    >
      {dot && <span className={cn("size-1.5 shrink-0 rounded-pill", dotClass[tone])} aria-hidden />}
      {children}
    </span>
  );
}
