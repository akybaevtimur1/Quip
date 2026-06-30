import { getLocale, getTranslations } from "next-intl/server";
import { resolveLocale } from "@/i18n/locale";
import { getLandingContent, ROUTES } from "@/lib/landingContent";
import { Container, WordChip, TypeBadge } from "../components/primitives";
import { PrimaryCTA, GhostCTA } from "../components/CTA";
import { ConfidenceGauge } from "../components/Confidence";
import { InlineClip } from "../components/InlineClip";

export async function Hero({ authed = false }: { authed?: boolean }) {
  const { hero, heroClip, openApp } = getLandingContent(resolveLocale(await getLocale()));
  const t = await getTranslations("heroReadout");
  return (
    <section id="top" className="relative overflow-hidden pt-28 pb-20 md:pt-32 md:pb-28">
      {/* instrument graticule, faded, never coral */}
      <div
        className="graticule pointer-events-none absolute inset-0 opacity-40 [mask-image:radial-gradient(120%_80%_at_70%_0%,#000_0%,transparent_65%)]"
        aria-hidden
      />

      <Container className="relative">
        <div className="grid items-center gap-y-14 lg:grid-cols-[minmax(0,48fr)_minmax(0,52fr)] lg:gap-x-14">
          {/* LEFT - value prop */}
          <div className="max-w-[37rem]">
            <h1 className="text-[clamp(36px,4.6vw,56px)] font-extrabold leading-[1.04] tracking-[-0.03em] text-ink">
              {hero.headlinePre}
              <br />
              {hero.headlineMid}
              <WordChip>{hero.headlineAccent}</WordChip>
              {hero.headlinePost}
            </h1>
            <p className="mt-6 max-w-[44ch] text-[1.0625rem] leading-relaxed text-muted">{hero.sub}</p>

            <div className="mt-9 flex flex-wrap items-center gap-3">
              <PrimaryCTA href={authed ? ROUTES.app : ROUTES.signup} size="lg">
                {authed ? openApp : hero.primary}
              </PrimaryCTA>
              <GhostCTA href="#how-it-works" size="lg">
                {hero.secondary}
              </GhostCTA>
            </div>

            <p className="mt-6 font-mono text-[12px] uppercase tracking-[0.08em] text-faint">{hero.trust}</p>
          </div>

          {/* RIGHT - live product readout */}
          <HeroReadout
            clip={heroClip}
            labels={{ status: t("status"), avg: t("avg"), confidence: t("confidence") }}
          />
        </div>
      </Container>
    </section>
  );
}

function HeroReadout({
  clip,
  labels,
}: {
  clip: ReturnType<typeof getLandingContent>["heroClip"];
  labels: { status: string; avg: string; confidence: string };
}) {
  return (
    <div className="rounded-[16px] border border-line-strong bg-surface/70 p-5 shadow-[inset_0_1px_0_rgba(242,239,233,0.05)] backdrop-blur-sm sm:p-7">
      {/* one quiet header line: real, informative, no live-theater */}
      <div className="flex items-center justify-between font-mono text-[11px] uppercase tracking-[0.12em] text-faint">
        <span>{labels.status}</span>
        <span>{labels.avg}</span>
      </div>

      {/* clip + the reading, sitting directly on the panel (no nested box) */}
      <div className="mt-6 grid grid-cols-[auto_minmax(0,1fr)] gap-6 sm:gap-8">
        <div className="relative aspect-[9/16] w-[150px] shrink-0 overflow-hidden rounded-[10px] border border-line bg-bg sm:w-[172px]">
          <InlineClip
            src={clip.src!}
            poster={clip.poster}
            label={`Quip clip: ${clip.hook}`}
            className="size-full object-cover"
          />
          <span className="absolute left-2 top-2">
            <TypeBadge type={clip.type} label={clip.typeLabel} />
          </span>
        </div>

        <div className="flex min-w-0 flex-col">
          <span className="font-mono text-[10.5px] uppercase tracking-[0.14em] text-faint">{labels.confidence}</span>
          <ConfidenceGauge value={clip.confidence} variant="hero" className="mt-1.5" />

          <p className="mt-6 text-[15px] font-semibold leading-snug tracking-[-0.01em] text-ink">{clip.hook}</p>
          <p className="mt-2 text-[13px] leading-snug text-muted">{clip.reason}</p>
          <span className="mt-4 font-mono text-[10px] tracking-[0.08em] text-faint">{clip.timecode}</span>
        </div>
      </div>
    </div>
  );
}
