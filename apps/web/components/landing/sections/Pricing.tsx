import { PRICING } from "@/lib/landingContent";
import { Container, Eyebrow, Section } from "../components/primitives";
import { PrimaryCTA, GhostCTA } from "../components/CTA";
import { Reveal } from "../components/Reveal";
import { Check } from "@phosphor-icons/react/dist/ssr";

export function Pricing() {
  const { heading, sub, plans, payg, footnote } = PRICING;
  return (
    <Section id="pricing">
      <Container>
        <Reveal className="max-w-[44rem]">
          <Eyebrow>{PRICING.eyebrow}</Eyebrow>
          <h2 className="mt-5 text-[clamp(30px,4vw,48px)] font-bold leading-[1.06] tracking-[-0.025em] text-ink">
            {heading}
          </h2>
          <p className="mt-5 text-[1.0625rem] leading-relaxed text-muted">{sub}</p>
        </Reveal>

        <div className="mt-14 grid gap-4 md:grid-cols-3">
          {plans.map((plan, i) => {
            const pro = plan.recommended;
            return (
              <Reveal key={plan.id} delay={i * 0.06}>
                <div
                  className={`lift relative flex h-full flex-col overflow-hidden rounded-[16px] border p-7 sm:p-8 ${
                    pro
                      ? "border-accent-line bg-surface-2 shadow-[inset_0_1px_0_rgba(255,90,61,0.12)]"
                      : "border-line bg-surface"
                  }`}
                >
                  {pro && <span className="absolute inset-x-0 top-0 h-[2px] bg-accent" aria-hidden />}

                  <div className="flex items-center justify-between">
                    <h3 className="text-[1.125rem] font-semibold tracking-[-0.01em] text-ink">{plan.name}</h3>
                    {pro && (
                      <span className="rounded-pill border border-accent-line bg-accent-tint px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-accent">
                        Recommended
                      </span>
                    )}
                  </div>
                  <p className="mt-1.5 text-[13.5px] text-muted">{plan.blurb}</p>

                  <div className="mt-6 flex items-baseline gap-1.5">
                    <span className={`num font-mono text-[42px] font-medium tracking-[-0.02em] ${pro ? "text-accent" : "text-ink"}`}>
                      {plan.price}
                    </span>
                    <span className="font-mono text-[13px] text-muted">{plan.cadence}</span>
                  </div>
                  <p className="mt-2 font-mono text-[12px] uppercase tracking-[0.08em] text-faint">{plan.allowance}</p>

                  <ul className="mt-7 flex flex-1 flex-col gap-3">
                    {plan.features.map((feat) => (
                      <li key={feat} className="flex gap-2.5 text-[14px] leading-snug text-muted">
                        <Check
                          weight="bold"
                          className={`mt-0.5 size-3.5 shrink-0 ${pro ? "text-accent" : "text-faint"}`}
                        />
                        {feat}
                      </li>
                    ))}
                  </ul>

                  <div className="mt-8">
                    {pro ? (
                      <PrimaryCTA href={plan.href} arrow={false} className="w-full">
                        {plan.cta}
                      </PrimaryCTA>
                    ) : (
                      <GhostCTA href={plan.href} className="w-full">
                        {plan.cta}
                      </GhostCTA>
                    )}
                  </div>
                </div>
              </Reveal>
            );
          })}
        </div>

        {/* pay-as-you-go strip */}
        <Reveal delay={0.06} className="mt-4">
          <div className="lift flex flex-col items-start justify-between gap-4 rounded-[14px] border border-line bg-surface px-7 py-5 sm:flex-row sm:items-center">
            <div className="flex items-baseline gap-3">
              <span className="text-[15px] font-semibold text-ink">{payg.name}</span>
              <span className="num font-mono text-[20px] font-medium text-ink">{payg.price}</span>
              <span className="font-mono text-[12px] text-muted">{payg.unit}</span>
            </div>
            <p className="text-[13.5px] text-muted">{payg.note}</p>
          </div>
        </Reveal>

        <p className="mt-6 text-center font-mono text-[12px] tracking-[0.04em] text-faint">{footnote}</p>
      </Container>
    </Section>
  );
}
