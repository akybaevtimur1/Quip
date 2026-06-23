import { Check, Minus } from "lucide-react";
import { Container } from "@/components/ui/Container";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { Logo } from "@/components/ui/Logo";
import { Reveal } from "@/components/ui/Reveal";
import { Section } from "@/components/ui/Section";
import { cn } from "@/lib/cn";
import { SectionHeading } from "./SectionHeading";

const rows: { dim: string; quip: string; them: string }[] = [
  { dim: "Clips per video", quip: "A few, ranked by confidence", them: "30+ to scroll through" },
  { dim: "Why post each one", quip: "Hook, score, reason & type", them: "No idea, you guess" },
  { dim: "Vertical reframe", quip: "Follows the speaker, zero flash frames", them: "Jumpy, often off-center" },
  { dim: "Captions", quip: "Active word pops, your style", them: "Generic, one look" },
  { dim: "Pricing", quip: "One credit = one video, shown up front", them: "Credit casino + surprise paywalls" },
  { dim: "The result", quip: "Post with intent", them: "Post and hope" },
];

const GRID = "sm:grid sm:grid-cols-[1.1fr_1.5fr_1.4fr]";

export function Comparison() {
  return (
    <Section className="border-y border-line bg-surface/40" space="tight">
      <Container>
        <Reveal>
          <SectionHeading
            eyebrow="04 / The difference"
            title="More clips was never the problem."
            lead="The bottleneck isn't quantity. It's knowing which moment is worth your audience's attention — and Quip optimizes for that."
          />
        </Reveal>

        <Reveal delay={80}>
          <div className="mt-12 overflow-hidden rounded-lg border border-line">
            {/* header — table head only from sm: up (on mobile each row is a labeled card) */}
            <div className={cn("hidden border-b border-line bg-surface", GRID)}>
              <div className="p-5" />
              <div className="flex items-center gap-2 border-l border-line bg-bg p-5">
                <Logo href={null} size="sm" />
              </div>
              <div className="border-l border-line p-5">
                <Eyebrow tone="faint">Volume clippers</Eyebrow>
              </div>
            </div>
            {/* rows — stacked card on mobile, 3-col table row from sm: */}
            {rows.map((r) => (
              <div
                key={r.dim}
                className={cn("block border-t border-line first:border-t-0 sm:border-t-0", GRID)}
              >
                <div className="p-5 pb-2 sm:pb-5">
                  <Eyebrow tone="faint">{r.dim}</Eyebrow>
                </div>
                {/* Quip column — the focal side: full-ink copy + coral check, lit surface */}
                <div className="flex items-start gap-2.5 bg-bg px-5 pb-3 text-sm text-ink sm:border-l sm:border-line sm:py-5">
                  <Check className="mt-0.5 size-4 shrink-0 text-accent" aria-hidden />
                  <span>
                    <Eyebrow tone="faint" className="mb-1 block sm:hidden">
                      Quip
                    </Eyebrow>
                    {r.quip}
                  </span>
                </div>
                {/* "them" — dimmed harder: faint copy, faint minus, no lit surface */}
                <div className="flex items-start gap-2.5 px-5 pb-5 text-sm text-faint sm:border-l sm:border-line sm:py-5">
                  <Minus className="mt-0.5 size-4 shrink-0 text-faint" aria-hidden />
                  <span>
                    <Eyebrow tone="faint" className="mb-1 block sm:hidden">
                      Volume clippers
                    </Eyebrow>
                    {r.them}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </Reveal>
      </Container>
    </Section>
  );
}
