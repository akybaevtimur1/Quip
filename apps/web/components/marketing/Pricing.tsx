import { Container } from "@/components/ui/Container";
import { Reveal } from "@/components/ui/Reveal";
import { Section } from "@/components/ui/Section";
import { PricingCards } from "./PricingCards";
import { SectionHeading } from "./SectionHeading";

export function Pricing() {
  return (
    <Section id="pricing">
      <Container>
        <Reveal>
          <SectionHeading
            align="center"
            eyebrow="Pricing"
            title="Simple plans. No credit casino."
            lead="Pay for source minutes, the thing that actually costs money. No tokens to ration, no surprise paywalls — you always know your limit up front."
          />
        </Reveal>
        <div className="mt-14">
          <PricingCards />
        </div>
      </Container>
    </Section>
  );
}
