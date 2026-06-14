import { ReasoningCard } from "@/components/marketing/ReasoningCard";
import { Container } from "@/components/ui/Container";
import { Reveal } from "@/components/ui/Reveal";
import { Section } from "@/components/ui/Section";
import { SectionHeading } from "./SectionHeading";

const dims = [
  { label: "Hook", color: "text-hook", body: "A scroll-stopping top line, written for that exact moment." },
  { label: "Why it works", color: "text-ink", body: "The real reason — open loop, payoff, tension — in one sentence." },
  { label: "Confidence", color: "text-ok", body: "An honest score, so you know which clip to post first." },
  { label: "Moment type", color: "text-quote", body: "Hook, emotional peak, complete thought, or strong quote." },
];

export function WhyQuip() {
  return (
    <Section id="why" className="relative overflow-hidden">
      <div
        aria-hidden
        className="pointer-events-none absolute right-[-10%] top-1/3 size-[520px] rounded-full bg-[radial-gradient(circle,rgba(255,90,61,.06),transparent_64%)]"
      />
      <Container className="relative grid items-center gap-14 lg:grid-cols-2 lg:gap-16">
        <div>
          <Reveal>
            <SectionHeading
              title={
                <>
                  Every clip comes with <span className="text-accent">its reasons.</span>
                </>
              }
              lead="Most AI clippers hand you thirty clips and a shrug. Quip hands you fewer — each with a hook, a confidence score, the moment type, and a plain reason it'll land. You post with intent, not hope."
            />
          </Reveal>
          <div className="mt-10 space-y-6">
            {dims.map((d, i) => (
              <Reveal key={d.label} delay={i * 70}>
                <div className="flex gap-4">
                  <span className="mt-1.5 h-4 w-px shrink-0 bg-line-strong" aria-hidden />
                  <div>
                    <p className={`font-mono text-eyebrow uppercase ${d.color}`}>{d.label}</p>
                    <p className="mt-1.5 text-sm leading-relaxed text-muted">{d.body}</p>
                  </div>
                </div>
              </Reveal>
            ))}
          </div>
        </div>

        {/* stacked reasons, different types & confidences */}
        <Reveal delay={120} className="relative mx-auto w-full max-w-md">
          <div className="space-y-4">
            <ReasoningCard
              type="strong_quote"
              confidence={94}
              why="A vulnerable admission in the first 2 seconds opens a loop the viewer needs closed."
              className="lg:ml-8"
            />
            <ReasoningCard
              type="emotional_peak"
              confidence={88}
              why="Voice breaks on the word that matters — emotion is the most shareable signal there is."
            />
            <ReasoningCard
              type="hook"
              confidence={73}
              why="A bold claim with a number. Strong, but it leans on the payoff arriving fast."
              className="lg:ml-12"
            />
          </div>
        </Reveal>
      </Container>
    </Section>
  );
}
