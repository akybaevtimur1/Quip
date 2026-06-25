import { buildHomeJsonLd } from "@/lib/jsonld";
import { getOptionalUser } from "@/lib/supabase/server";
import { Comparison } from "@/components/landing/sections/Comparison";
import { CostAnchor } from "@/components/landing/sections/CostAnchor";
import { Craft } from "@/components/landing/sections/Craft";
import { Demo } from "@/components/landing/sections/Demo";
import { Faq } from "@/components/landing/sections/Faq";
import { FinalCta } from "@/components/landing/sections/FinalCta";
import { Footer } from "@/components/landing/sections/Footer";
import { Hero } from "@/components/landing/sections/Hero";
import { HowItWorks } from "@/components/landing/sections/HowItWorks";
import { Nav } from "@/components/landing/sections/Nav";
import { Pricing } from "@/components/landing/sections/Pricing";
import { WhyQuip } from "@/components/landing/sections/WhyQuip";

/*
  Home / marketing landing ("Readout" direction). Server Component so the single
  auth seam is read here: `authed` flows into Nav, Hero, and FinalCta only. When
  logged in their CTAs become "Open the app / Dashboard" (/dashboard), otherwise
  "Try it free / Paste a video link" (/signup). getOptionalUser is dual-mode safe
  (returns null without touching cookies until Supabase is configured).
*/
export default async function Page() {
  const authed = Boolean(await getOptionalUser());

  return (
    <>
      <script
        type="application/ld+json"
        // Static, server-controlled data (site/plans/faq constants, no user input).
        // `<` is escaped so the JSON can never break out of the <script> context.
        dangerouslySetInnerHTML={{
          __html: JSON.stringify(buildHomeJsonLd()).replace(/</g, "\\u003c"),
        }}
      />
      <Nav authed={authed} />
      <main className="relative">
        <Hero authed={authed} />
        <Demo />
        <CostAnchor />
        <HowItWorks />
        <WhyQuip />
        <Craft />
        <Comparison />
        <Pricing />
        <Faq />
        <FinalCta authed={authed} />
      </main>
      <Footer />
    </>
  );
}
