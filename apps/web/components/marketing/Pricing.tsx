import { Container } from "@/components/ui/Container";
import { Reveal } from "@/components/ui/Reveal";
import { Section } from "@/components/ui/Section";
import { PricingCards } from "./PricingCards";
import { SectionHeading } from "./SectionHeading";

export function Pricing() {
  return (
    <Section id="pricing" space="tight">
      <Container>
        <Reveal>
          <SectionHeading
            align="center"
            eyebrow="05 / Pricing"
            title="Simple plans. No credit casino."
            lead="One credit is one video, up to 60 minutes. No tokens to ration, no surprise paywalls — your limit is shown up front, and pay-as-you-go credits never expire."
          />
        </Reveal>
        <div className="mt-14">
          <PricingCards />
        </div>
      </Container>
    </Section>
  );
}
