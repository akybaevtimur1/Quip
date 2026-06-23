import { Captions, Crop, Ratio, ScanFace } from "lucide-react";
import { ClipMockup } from "@/components/marketing/ClipMockup";
import { Container } from "@/components/ui/Container";
import { Reveal } from "@/components/ui/Reveal";
import { Section } from "@/components/ui/Section";
import { Split } from "@/components/ui/Split";
import { SectionHeading } from "./SectionHeading";

const features = [
  {
    icon: ScanFace,
    title: "Follows the speaker",
    body: "Active-speaker detection keeps the right face centered — even in multi-cam interviews.",
  },
  {
    icon: Crop,
    title: "No flash frames",
    body: "Frame-accurate scene detection. The crop only moves on real cuts, never a jarring jump mid-shot.",
  },
  {
    icon: Captions,
    title: "Captions that pop",
    body: "The active word flares as it's spoken, burned in pixel-for-pixel — the preview is the export.",
  },
  {
    icon: Ratio,
    title: "Your hook, four ratios",
    body: "A branded hook plate on top, and one clip in 9:16, 1:1, 4:5 or 16:9 for every platform.",
  },
];

export function Craft() {
  return (
    <Section id="craft" space="loose">
      <Container>
        <Reveal>
          <SectionHeading
            eyebrow="03 / The craft"
            title="The cut is the easy part. We sweat the rest."
            lead="Reframe, captions, hooks, aspect ratios — the details that decide whether a clip looks pro or looks auto-generated."
          />
        </Reveal>

        {/* show the craft: a real 9:16 render beside hairline-divided claim rows */}
        <Split variant="main-rail" gap="gap-10 lg:gap-16" className="mt-14 items-center">
          <Reveal>
            <dl className="divide-y divide-line border-t border-line">
              {features.map((f) => (
                <div key={f.title} className="flex items-start gap-4 py-6">
                  <f.icon className="mt-0.5 size-5 shrink-0 text-muted" aria-hidden />
                  <div>
                    <dt className="font-display text-h3 text-ink">{f.title}</dt>
                    <dd className="mt-1.5 max-w-xl text-sm leading-relaxed text-muted">{f.body}</dd>
                  </div>
                </div>
              ))}
            </dl>
          </Reveal>

          <Reveal delay={120} className="mx-auto w-full max-w-[300px] lg:max-w-none">
            <ClipMockup
              hook="The mistake that cost me 3 years"
              subtitle="so i "
              emphasis="rebuilt"
              subtitleTail=" the whole thing"
            />
          </Reveal>
        </Split>
      </Container>
    </Section>
  );
}
