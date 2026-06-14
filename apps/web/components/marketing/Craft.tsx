import { Captions, Crop, ScanFace, Sparkles } from "lucide-react";
import { Container } from "@/components/ui/Container";
import { Reveal } from "@/components/ui/Reveal";
import { Section } from "@/components/ui/Section";
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
    icon: Sparkles,
    title: "Your hook, four ratios",
    body: "A branded hook plate on top, and one clip in 9:16, 1:1, 4:5 or 16:9 for every platform.",
  },
];

export function Craft() {
  return (
    <Section id="craft">
      <Container>
        <Reveal>
          <SectionHeading
            title="The cut is the easy part. We sweat the rest."
            lead="Reframe, captions, hooks, aspect ratios — the details that decide whether a clip looks pro or looks auto-generated."
          />
        </Reveal>

        <Reveal>
          <div className="mt-12 grid gap-4 sm:grid-cols-2">
            {features.map((f) => (
              <div
                key={f.title}
                className="flex gap-4 rounded-xl border border-line bg-surface p-6 transition-colors duration-200 hover:border-line-strong"
              >
                <span className="grid size-10 shrink-0 place-items-center rounded-md border border-line bg-surface-2 text-accent">
                  <f.icon className="size-5" aria-hidden />
                </span>
                <div>
                  <h3 className="font-display text-h3 text-ink">{f.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-muted">{f.body}</p>
                </div>
              </div>
            ))}
          </div>
        </Reveal>
      </Container>
    </Section>
  );
}
