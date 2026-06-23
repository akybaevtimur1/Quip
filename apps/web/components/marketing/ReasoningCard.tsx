import { ReasonChip } from "@/components/ReasonChip";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { Meter, type MeterTone } from "@/components/ui/Meter";
import { Numeral } from "@/components/ui/Numeral";
import { cn } from "@/lib/cn";
import type { ClipType } from "@/lib/types";

/** The explainability wedge, made visual: clip-type + confidence (mono tabular) +
 *  "why it works" + the score meter. Confidence uses semantic color (green = high)
 *  so the number reads as honest instrument data; coral stays for actions. The
 *  score + meter is the recurring readout motif echoed across the app.
 *
 *  `floating` (Hero/FinalCta): a translucent overlay that sits ON the clip media — a
 *  blur + one soft shadow lifts it off the frame for legibility. In-flow (default,
 *  e.g. WhyQuip's stack): a solid surface-ladder panel where the hairline carries
 *  structure, NOT a drop shadow. */
export function ReasoningCard({
  type,
  confidence,
  why,
  floating = false,
  className,
}: {
  type: ClipType;
  confidence: number;
  why: string;
  floating?: boolean;
  className?: string;
}) {
  const tone = confidence >= 80 ? "text-ok" : confidence >= 60 ? "text-warn" : "text-muted";
  const meterTone: MeterTone = confidence >= 80 ? "ok" : confidence >= 60 ? "warn" : "neutral";

  return (
    <div
      className={cn(
        "rounded-lg border border-line p-4",
        floating
          ? "bg-surface/90 backdrop-blur-md shadow-[0_28px_64px_-26px_rgba(0,0,0,.85)]"
          : "bg-surface-2",
        className,
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <ReasonChip type={type} />
        <span className="flex items-baseline gap-1.5">
          <Eyebrow tone="faint">Conf</Eyebrow>
          <Numeral className={cn("text-sm font-semibold", tone)}>{confidence}</Numeral>
          <Numeral className="text-xs text-faint">/100</Numeral>
        </span>
      </div>
      <p className="mt-3 text-sm leading-relaxed text-muted">
        <span className="font-semibold text-ink">Why it works:</span> {why}
      </p>
      <Meter
        value={confidence / 100}
        tone={meterTone}
        className="mt-3 h-1"
        aria-label={`Confidence ${confidence} of 100`}
      />
    </div>
  );
}
