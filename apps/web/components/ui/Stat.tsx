import { cn } from "@/lib/cn";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { Meter, type MeterTone } from "@/components/ui/Meter";

// THE instrument readout — Quip's signature. A big mono tabular value under a mono
// eyebrow, with an optional thin gauge beneath. The one canonical way to render a
// confidence score, credit balance, count, duration or price across the whole app —
// so the defining number is a reusable component, never re-hand-rolled (which is how
// the design drifts into "coincidence" instead of "signature").
export type StatSize = "sm" | "md" | "lg" | "xl";
export type StatTone = "ink" | "accent" | "warn" | "bad" | "ok" | "muted";

const valueSize: Record<StatSize, string> = {
  sm: "text-2xl",
  md: "text-[2rem]",
  lg: "text-[2.75rem]",
  xl: "text-display-lg sm:text-display-xl",
};

const valueTone: Record<StatTone, string> = {
  ink: "text-ink",
  accent: "text-accent",
  warn: "text-warn",
  bad: "text-bad",
  ok: "text-ok",
  muted: "text-muted",
};

export function Stat({
  label,
  value,
  suffix,
  size = "md",
  tone = "ink",
  meter,
  meterTone = "neutral",
  align = "left",
  className,
}: {
  /** Mono uppercase eyebrow label, rendered above the value. */
  label?: React.ReactNode;
  /** The number itself (rendered in mono tabular). */
  value: React.ReactNode;
  /** Small muted mono suffix after the value (e.g. "/100", "min", "/mo"). */
  suffix?: React.ReactNode;
  size?: StatSize;
  tone?: StatTone;
  /** 0..1 → renders the thin gauge beneath the value. */
  meter?: number;
  meterTone?: MeterTone;
  align?: "left" | "right";
  className?: string;
}) {
  return (
    <div className={cn(align === "right" && "text-right", className)}>
      {label != null && (
        <Eyebrow tone="faint" className="block">
          {label}
        </Eyebrow>
      )}
      <div className={cn("mt-1.5 flex items-baseline gap-1.5", align === "right" && "justify-end")}>
        <span
          className={cn(
            "font-mono font-semibold leading-none tabular-nums tracking-tight",
            valueSize[size],
            valueTone[tone],
          )}
        >
          {value}
        </span>
        {suffix != null && (
          <span className="font-mono text-sm tabular-nums text-muted">{suffix}</span>
        )}
      </div>
      {meter != null && <Meter value={meter} tone={meterTone} className="mt-2.5 h-0.5" aria-label={typeof label === "string" ? label : undefined} />}
    </div>
  );
}
