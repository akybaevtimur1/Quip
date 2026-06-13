import { ReasonChip } from "@/components/ReasonChip";
import { cn } from "@/lib/cn";
import type { ClipType } from "@/lib/types";

/** The explainability wedge, made visual: clip-type + confidence (tabular) +
 *  "why it works" + a confidence bar. Confidence uses semantic color (green =
 *  high) so the number reads as honest instrument data; coral stays for actions. */
export function ReasoningCard({
  type,
  confidence,
  why,
  className,
}: {
  type: ClipType;
  confidence: number;
  why: string;
  className?: string;
}) {
  const tone = confidence >= 80 ? "text-ok" : confidence >= 60 ? "text-warn" : "text-muted";
  const bar = confidence >= 80 ? "bg-ok" : confidence >= 60 ? "bg-warn" : "bg-faint";

  return (
    <div
      className={cn(
        "rounded-lg border border-line bg-surface/90 p-4 backdrop-blur-md",
        "shadow-[0_28px_64px_-26px_rgba(0,0,0,.85)]",
        className,
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <ReasonChip type={type} />
        <span className="font-mono text-xs tabular-nums text-muted">
          Confidence <span className={cn("font-semibold", tone)}>{confidence}%</span>
        </span>
      </div>
      <p className="mt-3 text-sm leading-relaxed text-muted">
        <span className="font-semibold text-ink">Why it works:</span> {why}
      </p>
      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-surface-3">
        <div className={cn("h-full rounded-full", bar)} style={{ width: `${confidence}%` }} />
      </div>
    </div>
  );
}
