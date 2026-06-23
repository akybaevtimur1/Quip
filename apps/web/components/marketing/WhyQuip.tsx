import { ReasoningCard } from "@/components/marketing/ReasoningCard";
import { Container } from "@/components/ui/Container";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { Reveal } from "@/components/ui/Reveal";
import { Section } from "@/components/ui/Section";
import { Split } from "@/components/ui/Split";
import { cn } from "@/lib/cn";
import { SectionHeading } from "./SectionHeading";

// Each readout row carries a token tick keyed to what the dimension MEANS: clip-type
// tokens (hook/quote), semantic (ok), and a neutral mark for the plain "why" row. The
// label itself stays a neutral mono Eyebrow; the colored tick does the encoding. Class
// strings are literal so Tailwind extracts them statically.
type DimTone = "hook" | "ok" | "quote" | "neutral";
const tickColor: Record<DimTone, string> = {
  hook: "bg-hook",
  ok: "bg-ok",
  quote: "bg-quote",
  neutral: "bg-line-strong",
};

const dims: { label: string; tone: DimTone; body: string }[] = [
  { label: "Hook", tone: "hook", body: "A scroll-stopping top line, written for that exact moment." },
  {
    label: "Why it works",
    tone: "neutral",
    body: "The real reason — open loop, payoff, tension — in one sentence.",
  },
  { label: "Confidence", tone: "ok", body: "An honest score, so you know which clip to post first." },
  { label: "Moment type", tone: "quote", body: "Hook, emotional peak, complete thought, or strong quote." },
];

export function WhyQuip() {
  return (
    <Section id="why">
      <Container>
        <Split variant="balanced" gap="gap-14 lg:gap-16" className="items-center">
          <div>
            <Reveal>
              <SectionHeading
                eyebrow="02 / Why it works"
                title={
                  <>
                    Every clip comes with <span className="text-accent">its reasons.</span>
                  </>
                }
                lead="Most AI clippers hand you thirty clips and a shrug. Quip hands you fewer — each with a hook, a confidence score, the moment type, and a plain reason it'll land. You post with intent, not hope."
              />
            </Reveal>

            {/* a readout ledger: hairline-divided claim rows, not a card stack */}
            <Reveal delay={80}>
              <dl className="mt-10 divide-y divide-line border-y border-line">
                {dims.map((d) => (
                  <div
                    key={d.label}
                    className="grid grid-cols-[8rem_1fr] items-baseline gap-4 py-4 sm:grid-cols-[10rem_1fr]"
                  >
                    <dt className="flex items-center gap-2.5">
                      <span
                        aria-hidden
                        className={cn("size-1.5 shrink-0 rounded-pill", tickColor[d.tone])}
                      />
                      <Eyebrow tone="ink">{d.label}</Eyebrow>
                    </dt>
                    <dd className="text-sm leading-relaxed text-muted">{d.body}</dd>
                  </div>
                ))}
              </dl>
            </Reveal>
          </div>

          {/* stacked reasons, different types & confidences — staggered, not in one fade */}
          <div className="relative mx-auto w-full max-w-md space-y-4">
            <Reveal>
              <ReasoningCard
                type="strong_quote"
                confidence={94}
                why="A vulnerable admission in the first 2 seconds opens a loop the viewer needs closed."
                className="lg:ml-8"
              />
            </Reveal>
            <Reveal delay={90}>
              <ReasoningCard
                type="emotional_peak"
                confidence={88}
                why="Voice breaks on the word that matters — emotion is the most shareable signal there is."
              />
            </Reveal>
            <Reveal delay={180}>
              <ReasoningCard
                type="hook"
                confidence={73}
                why="A bold claim with a number. Strong, but it leans on the payoff arriving fast."
                className="lg:ml-12"
              />
            </Reveal>
          </div>
        </Split>
      </Container>
    </Section>
  );
}
