import { Container } from "@/components/ui/Container";
import { Reveal } from "@/components/ui/Reveal";
import { Section } from "@/components/ui/Section";
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
    body: "It transcribes, picks the strongest moments, writes a hook, scores confidence, and tells you why each one works.",
  },
  {
    n: "03",
    title: "Polish & post",
    body: "Smooth 9:16 reframe that follows the speaker, juicy captions, your style. Export and post with intent.",
  },
];

export function HowItWorks() {
  return (
    <Section id="how-it-works">
      <Container>
        <Reveal>
          <SectionHeading
            title="Long video in. Clips you can trust out."
            lead="Three steps, a couple of minutes. No timeline scrubbing, no guessing which moment to cut."
          />
        </Reveal>
        <Reveal>
          <div className="mt-14 grid gap-px overflow-hidden rounded-xl border border-line bg-line sm:grid-cols-3">
            {steps.map((s) => (
              <div
                key={s.n}
                className="group relative bg-bg p-7 transition-colors duration-200 hover:bg-surface sm:p-8"
              >
                <span className="font-mono text-sm tabular-nums text-accent">{s.n}</span>
                <h3 className="mt-5 font-display text-h3 text-ink">{s.title}</h3>
                <p className="mt-3 text-sm leading-relaxed text-muted">{s.body}</p>
              </div>
            ))}
          </div>
        </Reveal>
      </Container>
    </Section>
  );
}
