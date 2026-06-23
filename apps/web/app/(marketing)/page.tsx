import type { Metadata } from "next";
import { Comparison } from "@/components/marketing/Comparison";
import { Craft } from "@/components/marketing/Craft";
import { Faq } from "@/components/marketing/Faq";
import { FinalCta } from "@/components/marketing/FinalCta";
import { Hero } from "@/components/marketing/Hero";
import { HowItWorks } from "@/components/marketing/HowItWorks";
import { Pricing } from "@/components/marketing/Pricing";
import { ProofStrip } from "@/components/marketing/ProofStrip";
import { QuipStudio } from "@/components/marketing/QuipStudio";
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
      {/* the page climax: show the instrument working before we explain it */}
      <QuipStudio />
      {/* edge-to-edge cost band — sits on the surface ladder, top hairline only */}
      <ProofStrip />
      <HowItWorks />
      <WhyQuip />
      <Craft />
      <Comparison />
      <Faq />
      {/* Pricing sits low, right before the closing CTA — visitors see the plans
          before we ask them to start free. */}
      <Pricing />
      <FinalCta />
    </>
  );
}
