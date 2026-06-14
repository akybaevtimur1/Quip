import { Plus } from "lucide-react";
import { Container } from "@/components/ui/Container";
import { Reveal } from "@/components/ui/Reveal";
import { Section } from "@/components/ui/Section";
import { FAQ } from "@/lib/faq";
import { SectionHeading } from "./SectionHeading";

export function Faq() {
  return (
    <Section id="faq">
      <Container className="grid gap-12 lg:grid-cols-[0.8fr_1.2fr] lg:gap-16">
        <Reveal>
          <SectionHeading title="Questions, answered straight." />
        </Reveal>
        <Reveal delay={80}>
          <div className="divide-y divide-line overflow-hidden rounded-xl border border-line">
            {FAQ.map((item) => (
              <details key={item.q} className="group bg-surface/50 open:bg-surface">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-4 p-5 text-ink [&::-webkit-details-marker]:hidden">
                  <span className="font-display text-base font-semibold sm:text-lg">{item.q}</span>
                  <Plus
                    className="size-5 shrink-0 text-muted transition-transform duration-200 ease-snappy group-open:rotate-45 group-open:text-accent"
                    aria-hidden
                  />
                </summary>
                <p className="px-5 pb-5 text-sm leading-relaxed text-muted">{item.a}</p>
              </details>
            ))}
          </div>
        </Reveal>
      </Container>
    </Section>
  );
}
