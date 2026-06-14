import { Check, Minus } from "lucide-react";
import { Container } from "@/components/ui/Container";
import { Logo } from "@/components/ui/Logo";
import { Reveal } from "@/components/ui/Reveal";
import { Section } from "@/components/ui/Section";
import { SectionHeading } from "./SectionHeading";

const rows: { dim: string; quip: string; them: string }[] = [
  { dim: "Clips per video", quip: "A few, ranked by confidence", them: "30+ to scroll through" },
  { dim: "Why post each one", quip: "Hook, score, reason & type", them: "No idea, you guess" },
  { dim: "Vertical reframe", quip: "Follows the speaker, zero flash frames", them: "Jumpy, often off-center" },
  { dim: "Captions", quip: "Active word pops, your style", them: "Generic, one look" },
  { dim: "Pricing", quip: "One credit = one video, shown up front", them: "Credit casino + surprise paywalls" },
  { dim: "The result", quip: "Post with intent", them: "Post and hope" },
];

export function Comparison() {
  return (
    <Section className="border-y border-line bg-surface/40">
      <Container>
        <Reveal>
          <SectionHeading
            title="More clips was never the problem."
            lead="The bottleneck isn't quantity. It's knowing which moment is worth your audience's attention, and Quip optimizes for that."
          />
        </Reveal>

        <Reveal delay={80}>
          <div className="mt-12 overflow-hidden rounded-xl border border-line">
            {/* header */}
            <div className="grid grid-cols-[1fr_1.2fr_1.2fr] border-b border-line bg-bg sm:grid-cols-[1.2fr_1.4fr_1.4fr]">
              <div className="p-4 sm:p-5" />
              <div className="flex items-center gap-2 border-l border-line p-4 sm:p-5">
                <Logo href={null} size="sm" />
              </div>
              <div className="border-l border-line p-4 text-sm font-medium text-muted sm:p-5">
                Volume clippers
              </div>
            </div>
            {/* rows */}
            {rows.map((r, i) => (
              <div
                key={r.dim}
                className={`grid grid-cols-[1fr_1.2fr_1.2fr] sm:grid-cols-[1.2fr_1.4fr_1.4fr] ${
                  i % 2 ? "bg-bg/40" : "bg-bg"
                }`}
              >
                <div className="p-4 text-sm font-medium text-faint sm:p-5">{r.dim}</div>
                <div className="flex items-start gap-2.5 border-l border-line p-4 text-sm text-ink sm:p-5">
                  <Check className="mt-0.5 size-4 shrink-0 text-accent" aria-hidden />
                  <span>{r.quip}</span>
                </div>
                <div className="flex items-start gap-2.5 border-l border-line p-4 text-sm text-muted sm:p-5">
                  <Minus className="mt-0.5 size-4 shrink-0 text-faint" aria-hidden />
                  <span>{r.them}</span>
                </div>
              </div>
            ))}
          </div>
        </Reveal>
      </Container>
    </Section>
  );
}
