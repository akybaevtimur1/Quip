import type { Metadata } from "next";
import { Comparison } from "@/components/marketing/Comparison";
import { Craft } from "@/components/marketing/Craft";
import { Faq } from "@/components/marketing/Faq";
import { FinalCta } from "@/components/marketing/FinalCta";
import { Hero } from "@/components/marketing/Hero";
import { HowItWorks } from "@/components/marketing/HowItWorks";
import { Pricing } from "@/components/marketing/Pricing";
import { WhyQuip } from "@/components/marketing/WhyQuip";
import { buildHomeJsonLd } from "@/lib/jsonld";

export const metadata: Metadata = {
  alternates: { canonical: "/" },
};

export default function HomePage() {
  return (
    <>
      <script
        type="application/ld+json"
        // Static, server-controlled data (site/plans/faq constants — no user input).
        // `<` is escaped so the JSON can never break out of the <script> context.
        dangerouslySetInnerHTML={{
          __html: JSON.stringify(buildHomeJsonLd()).replace(/</g, "\\u003c"),
        }}
      />
      <Hero />
      <HowItWorks />
      <WhyQuip />
      <Craft />
      <Comparison />
      <Pricing />
      <Faq />
      <FinalCta />
    </>
  );
}
