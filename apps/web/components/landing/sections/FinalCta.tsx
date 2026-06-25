import { FINAL_CTA, ROUTES } from "@/lib/landingContent";
import { Container } from "../components/primitives";
import { PrimaryCTA, GhostCTA } from "../components/CTA";
import { Reveal } from "../components/Reveal";

export function FinalCta({ authed = false }: { authed?: boolean }) {
  return (
    <section className="relative overflow-hidden py-28 md:py-36">
      {/* the one place coral atmosphere returns, low and centered, decaying fast */}
      <div
        className="pointer-events-none absolute inset-x-0 bottom-0 h-[60%] opacity-80"
        style={{
          background: "radial-gradient(50% 120% at 50% 100%, rgba(255,90,61,0.10), transparent 70%)",
        }}
        aria-hidden
      />
      <Container className="relative">
        <Reveal className="mx-auto max-w-[40rem] text-center">
          <h2 className="text-[clamp(34px,5vw,60px)] font-extrabold leading-[1.02] tracking-[-0.03em] text-ink">
            {FINAL_CTA.heading}
          </h2>
          <p className="mx-auto mt-6 max-w-[48ch] text-[1.0625rem] leading-relaxed text-muted">{FINAL_CTA.sub}</p>

          <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
            <PrimaryCTA href={authed ? ROUTES.app : ROUTES.signup} size="lg">
              {authed ? "Open the app" : FINAL_CTA.primary}
            </PrimaryCTA>
            <GhostCTA href="#pricing" size="lg">
              {FINAL_CTA.secondary}
            </GhostCTA>
          </div>

          <p className="mt-7 font-mono text-[12px] uppercase tracking-[0.08em] text-faint">{FINAL_CTA.trust}</p>
        </Reveal>
      </Container>
    </section>
  );
}
