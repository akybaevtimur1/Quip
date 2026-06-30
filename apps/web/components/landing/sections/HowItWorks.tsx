import { getLocale } from "next-intl/server";
import { resolveLocale } from "@/i18n/locale";
import { getLandingContent } from "@/lib/landingContent";
import { Container, Section } from "../components/primitives";
import { Reveal } from "../components/Reveal";

export async function HowItWorks() {
  const { heading, sub, steps } = getLandingContent(resolveLocale(await getLocale())).howItWorks;
  return (
    <Section id="how-it-works">
      <Container>
        <Reveal className="max-w-[40rem]">
          <h2 className="text-[clamp(28px,3.6vw,44px)] font-bold leading-[1.08] tracking-[-0.025em] text-ink">
            {heading}
          </h2>
          <p className="mt-4 text-[1.0625rem] text-muted">{sub}</p>
        </Reveal>

        {/* numbered rail, not three equal cards */}
        <div className="mt-14 grid gap-x-10 gap-y-12 md:grid-cols-3">
          {steps.map((step, i) => (
            <Reveal key={step.n} delay={i * 0.07}>
              <div className="relative">
                <div className="flex items-center gap-4">
                  <span className="num font-mono text-[15px] text-muted">{step.n}</span>
                  <span className="h-px flex-1 bg-line" />
                </div>
                <h3 className="mt-5 text-[1.375rem] font-semibold tracking-[-0.015em] text-ink">{step.title}</h3>
                <p className="mt-2.5 max-w-[34ch] text-[15px] leading-relaxed text-muted">{step.body}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </Container>
    </Section>
  );
}
