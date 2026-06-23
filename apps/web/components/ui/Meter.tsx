import { cn } from "@/lib/cn";

// Thin instrument gauge: a hairline track with a value-keyed fill (value 0..1).
// Replaces the ad-hoc full-width rounded quota bars with one calibrated readout.
// Default height is a slim rail; pass h-0.5 for the 2px score tick-meter.
export type MeterTone = "accent" | "warn" | "bad" | "ok" | "neutral";

const fillClass: Record<MeterTone, string> = {
  accent: "bg-accent",
  warn: "bg-warn",
  bad: "bg-bad",
  ok: "bg-ok",
  neutral: "bg-line-strong",
};

export function Meter({
  value,
  tone = "neutral",
  className,
  "aria-label": ariaLabel,
}: {
  value: number;
  tone?: MeterTone;
  className?: string;
  "aria-label"?: string;
}) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  return (
    <div
      role="progressbar"
      aria-valuenow={Math.round(pct)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={ariaLabel}
      className={cn("h-1 w-full overflow-hidden rounded-pill bg-surface-3", className)}
    >
      <div
        className={cn("h-full rounded-pill transition-[width] duration-500 ease-snappy", fillClass[tone])}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
