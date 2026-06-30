import { getTranslations } from "next-intl/server";
import type { Clip } from "@/lib/landingContent";
import { InlineClip } from "./InlineClip";
import { ConfidenceGauge } from "./Confidence";
import { TypeBadge } from "./primitives";

/*
  A clip rendered as an instrument readout: the real 9:16 captioned output on the left,
  the verdict column (timecode, hook, confidence, reason) on the right. Active state lifts
  one rung up the warm surface ladder, never by spending coral on selection.

  Server component (rendered by the async WhyQuip section, passed as a child into the
  client Reveal). The bilingual landing copy lives in landingContent.ts, but the card
  CHROME (the "Clip NN / MM" label + a11y strings) comes from next-intl via getTranslations,
  same cookie-resolved locale as the rest of the funnel.
*/
export async function ClipCard({ clip, active = false }: { clip: Clip; active?: boolean }) {
  const t = await getTranslations("landingDemo");
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
            label={t("clipAria", { hook: clip.hook })}
            className="size-full object-cover"
          />
        ) : (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={clip.poster}
            alt={t("clipAlt", { caption: clip.caption ?? clip.hook })}
            className="size-full object-cover"
          />
        )}
        <span className="absolute left-1.5 top-1.5">
          <TypeBadge type={clip.type} label={clip.typeLabel} />
        </span>
      </div>

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="font-mono text-[11px] uppercase tracking-[0.1em] text-faint">
          {t("clipLabel", { id: clip.id, timecode: clip.timecode })}
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
