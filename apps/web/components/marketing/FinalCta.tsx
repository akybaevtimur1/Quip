import Link from "next/link";
import { ClipMockup } from "@/components/marketing/ClipMockup";
import { ReasoningCard } from "@/components/marketing/ReasoningCard";
import { buttonVariants } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { Numeral } from "@/components/ui/Numeral";
import { Reveal } from "@/components/ui/Reveal";
import { Section } from "@/components/ui/Section";
import { Split } from "@/components/ui/Split";
import { getOptionalUser } from "@/lib/supabase/server";

export async function FinalCta() {
  const authed = Boolean(await getOptionalUser());
  return (
    <Section className="relative overflow-hidden border-t border-line" space="loose">
      {/* the single closing bloom — the only ambient signal at the foot of the page */}
      <div
        aria-hidden
        className="pointer-events-none absolute right-[6%] top-1/2 size-[560px] -translate-y-1/2 rounded-full bg-[radial-gradient(circle,rgba(255,90,61,.09),transparent_62%)]"
      />
      <Container className="relative">
        <Split variant="balanced" gap="gap-14 lg:gap-20" className="items-center">
          <Reveal>
            <Eyebrow tone="accent" className="flex items-center gap-2">
              <span className="h-px w-6 bg-accent-line" aria-hidden />
              The verdict
            </Eyebrow>
            <h2 className="mt-5 font-display text-h2 text-ink sm:text-display-lg">
              Stop guessing which clips to post.
            </h2>
            <p className="mt-5 max-w-md text-lead text-muted">
              Drop in a video and get a handful of clips you can actually stand behind — each with the
              reason it works and a score you can trust.
            </p>
            <div className="mt-9 flex flex-wrap items-center gap-3">
              <Link
                href={authed ? "/dashboard" : "/signup"}
                className={buttonVariants({ variant: "primary", size: "lg" })}
              >
                {authed ? "Open the app" : "Try Quip free"}
                <span aria-hidden>→</span>
              </Link>
              <Link href="#pricing" className={buttonVariants({ variant: "secondary", size: "lg" })}>
                See pricing
              </Link>
            </div>
            {!authed && (
              <Eyebrow as="p" tone="faint" className="mt-7">
                No card · <Numeral>2</Numeral> free videos / month · cancel anytime
              </Eyebrow>
            )}
          </Reveal>

          {/* a concrete reading to close on — the product's actual output, not more copy */}
          <Reveal delay={120} className="relative mx-auto w-full max-w-[380px]">
            <div className="relative">
              <ClipMockup
                hook="The mistake that cost me 3 years"
                subtitle="so i "
                emphasis="rebuilt"
                subtitleTail=" the whole thing"
                className="ml-auto w-[72%]"
              />
              <ReasoningCard
                floating
                className="absolute -bottom-5 left-0 w-[78%]"
                type="emotional_peak"
                confidence={91}
                why="The pause before the answer is the tell — viewers lean in to hear what comes next."
              />
            </div>
          </Reveal>
        </Split>
      </Container>
    </Section>
  );
}
