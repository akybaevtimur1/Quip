import { getLocale } from "next-intl/server";
import { resolveLocale } from "@/i18n/locale";
import { getLandingContent } from "@/lib/landingContent";
import { Container, Eyebrow, Section, TypeBadge } from "../components/primitives";
import { InlineClip } from "../components/InlineClip";
import { ConfidenceGauge } from "../components/Confidence";
import { ClipCard } from "../components/ClipCard";
import { Reveal } from "../components/Reveal";

export async function WhyQuip() {
  const { why, clips, heroClip } = getLandingContent(resolveLocale(await getLocale()));
  const featured = clips[1]; // the "strong quote", score 88
  const evidence = [heroClip, clips[2], clips[3]];

  return (
    <Section id="why">
      <Container>
        <Reveal className="max-w-[46rem]">
          <Eyebrow>{why.eyebrow}</Eyebrow>
          <h2 className="mt-5 text-[clamp(30px,4vw,48px)] font-bold leading-[1.06] tracking-[-0.025em] text-ink">
            {why.heading}
          </h2>
          <p className="mt-5 text-[1.0625rem] leading-relaxed text-muted">{why.sub}</p>
        </Reveal>

        {/* anatomy of one verdict: the clip on the left, its four carried reasons on the right */}
        <Reveal delay={0.05} className="mt-14">
          <div className="grid items-center gap-8 rounded-[18px] border border-line-strong bg-surface p-5 shadow-[inset_0_1px_0_rgba(242,239,233,0.06)] sm:p-7 lg:grid-cols-[minmax(0,34fr)_minmax(0,66fr)] lg:gap-12">
            <div className="mx-auto w-full max-w-[260px]">
              <div className="relative aspect-[9/16] overflow-hidden rounded-[12px] border border-line bg-bg">
                <InlineClip
                  src={featured.src!}
                  poster={featured.poster}
                  label={`Quip clip: ${featured.hook}`}
                  className="size-full object-cover"
                />
                <span className="absolute left-2 top-2">
                  <TypeBadge type={featured.type} label={featured.typeLabel} />
                </span>
                <span className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-bg/90 to-transparent px-2.5 pb-2 pt-7 font-mono text-[10px] tracking-[0.06em] text-muted">
                  {featured.timecode}
                </span>
              </div>
            </div>

            <ul className="divide-y divide-line">
              {why.payload.map((item, i) => (
                <li key={item.id} className="grid grid-cols-[2rem_minmax(0,1fr)] gap-x-4 py-4 first:pt-0 last:pb-0">
                  <span className="num font-mono text-[12px] text-faint">{String(i + 1).padStart(2, "0")}</span>
                  <div>
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
                      <span className="text-[15px] font-semibold tracking-[-0.01em] text-ink">{item.label}</span>
                      {item.id === "momentType" && (
                        <TypeBadge type={featured.type} label={featured.typeLabel} />
                      )}
                    </div>
                    <p className="mt-1 text-[14px] leading-relaxed text-muted">{item.body}</p>
                    {item.id === "hook" && (
                      <p className="mt-2 text-[14px] font-medium italic leading-snug text-ink/90">
                        “{featured.hook}”
                      </p>
                    )}
                    {item.id === "whyItWorks" && (
                      <p className="mt-2 text-[14px] leading-snug text-ink/80">{featured.reason}</p>
                    )}
                    {item.id === "confidence" && (
                      <ConfidenceGauge value={featured.confidence} variant="card" className="mt-2" />
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </Reveal>

        {/* evidence: real verdicts with a real spread of scores; only the active one spends coral */}
        <div className="mt-12 grid gap-4 md:grid-cols-3">
          {evidence.map((clip, i) => (
            <Reveal key={clip.id} delay={i * 0.06}>
              <ClipCard clip={clip} active={i === 0} />
            </Reveal>
          ))}
        </div>
      </Container>
    </Section>
  );
}
