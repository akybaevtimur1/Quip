import { Container } from "@/components/ui/Container";
import { Numeral } from "@/components/ui/Numeral";
import { Reveal } from "@/components/ui/Reveal";
import { Section } from "@/components/ui/Section";
import { cn } from "@/lib/cn";
import { SectionHeading } from "./SectionHeading";

const steps = [
  {
    n: "01",
    title: "Paste a link or upload",
    body: "Drop a YouTube link or a file — podcast, interview, stream, or lecture. Up to 90 minutes.",
  },
  {
    n: "02",
    title: "Quip finds & explains",
    body: "It transcribes, picks the strongest moments, writes a hook, scores confidence, and reports why each one works.",
    lead: true,
  },
  {
    n: "03",
    title: "Polish & post",
    body: "Smooth 9:16 reframe that follows the speaker, juicy captions, your style. Export and post with intent.",
  },
];

export function HowItWorks() {
  return (
    <Section id="how-it-works" space="tight">
      <Container>
        <Reveal>
          <SectionHeading
            eyebrow="01 / The pipeline"
            title="Long video in. Clips you can trust out."
            lead="Three steps, a couple of minutes. No timeline scrubbing, no guessing which moment to cut."
          />
        </Reveal>

        {/* timeline spine — a hairline track with mono-numeral nodes and a coral tick
            parked on the analysis step (the work that defines the product) */}
        <Reveal>
          <ol className="mt-16 grid gap-12 sm:mt-20 sm:grid-cols-3 sm:gap-0">
            {steps.map((s, i) => (
              <li key={s.n} className="group relative sm:px-7 first:sm:pl-0 last:sm:pr-0">
                {/* the spine: a continuous hairline behind the nodes (desktop) */}
                {i < steps.length - 1 && (
                  <span
                    aria-hidden
                    className="absolute left-[7px] top-12 hidden h-[calc(100%-3rem)] w-px bg-line sm:left-0 sm:top-[7px] sm:h-px sm:w-full"
                  />
                )}
                {/* node */}
                <span
                  aria-hidden
                  className={cn(
                    "absolute left-0 top-1 size-3.5 rounded-pill border-2 bg-bg sm:top-0",
                    s.lead ? "border-accent" : "border-line-strong",
                  )}
                >
                  {s.lead && (
                    <span className="absolute inset-0.5 rounded-pill bg-accent" />
                  )}
                </span>

                <div className="pl-7 sm:pl-0 sm:pt-9">
                  <Numeral
                    className={cn(
                      "text-sm",
                      s.lead ? "text-accent" : "text-faint",
                    )}
                  >
                    {s.n}
                  </Numeral>
                  <h3
                    className={cn(
                      "mt-3 font-display text-ink",
                      s.lead ? "text-h2" : "text-h3",
                    )}
                  >
                    {s.title}
                  </h3>
                  <p className="mt-3 max-w-xs text-sm leading-relaxed text-muted">{s.body}</p>
                </div>
              </li>
            ))}
          </ol>
        </Reveal>
      </Container>
    </Section>
  );
}
