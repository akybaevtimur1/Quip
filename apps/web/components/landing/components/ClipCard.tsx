import type { Clip } from "@/lib/landingContent";
import { InlineClip } from "./InlineClip";
import { ConfidenceGauge } from "./Confidence";
import { TypeBadge } from "./primitives";

/*
  A clip rendered as an instrument readout: the real 9:16 captioned output on the left,
  the verdict column (timecode, hook, confidence, reason) on the right. Active state lifts
  one rung up the warm surface ladder, never by spending coral on selection.
*/
export function ClipCard({ clip, active = false }: { clip: Clip; active?: boolean }) {
  return (
    <div
      className={`lift flex gap-4 rounded-card border p-3 ${
        active ? "border-line-strong bg-surface-2" : "border-line bg-surface"
      }`}
    >
      <div className="relative aspect-[9/16] w-[104px] shrink-0 overflow-hidden rounded-[8px] border border-line bg-bg">
        {clip.src ? (
          <InlineClip
            src={clip.src}
            poster={clip.poster}
            label={`Quip clip: ${clip.hook}`}
            className="size-full object-cover"
          />
        ) : (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={clip.poster}
            alt={`Quip vertical clip, captioned: ${clip.caption ?? clip.hook}`}
            className="size-full object-cover"
          />
        )}
        <span className="absolute left-1.5 top-1.5">
          <TypeBadge type={clip.type} />
        </span>
      </div>

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="font-mono text-[11px] uppercase tracking-[0.1em] text-faint">
          Clip {clip.id} · {clip.timecode}
        </div>
        <p className="mt-1.5 text-[15px] font-semibold leading-snug tracking-[-0.01em] text-ink">{clip.hook}</p>
        <p className="mt-1.5 text-[13px] leading-snug text-muted">{clip.reason}</p>
        <div className="mt-auto pt-3">
          <ConfidenceGauge value={clip.confidence} variant="inline" track={false} accent={active} />
        </div>
      </div>
    </div>
  );
}
