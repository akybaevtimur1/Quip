import type { Metadata } from "next";
import { Comparison } from "@/components/marketing/Comparison";
import { Faq } from "@/components/marketing/Faq";
import { PricingCards } from "@/components/marketing/PricingCards";
import { Container } from "@/components/ui/Container";
import { Eyebrow } from "@/components/ui/Eyebrow";

export const metadata: Metadata = {
  title: "Pricing",
  description:
    "Simple, honest pricing for Quip. One credit is one video (up to 60 min). Free, Starter ($10/mo), and Pro ($25/mo), plus pay-as-you-go at $2 a video. No surprise paywalls.",
  alternates: { canonical: "/pricing" },
};

export default function PricingPage() {
  return (
    <>
      <Container className="pt-16 text-center sm:pt-24">
        <Eyebrow>Pricing</Eyebrow>
        <h1 className="mx-auto mt-5 max-w-2xl font-display text-display-lg text-ink sm:text-display-xl">
          Pricing that respects your wallet.
        </h1>
        <p className="mx-auto mt-4 max-w-lg text-lead text-muted">
          One credit is one video, up to 60 minutes. No tokens to ration, no surprise paywalls, no
          dark patterns. Start free.
        </p>
      </Container>
      <Container className="pb-8 pt-14">
        <PricingCards />
      </Container>
      <Comparison />
      <Faq />
    </>
  );
}
