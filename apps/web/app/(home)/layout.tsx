import type { Metadata } from "next";

/*
  The marketing home is self-contained: its Nav + Footer live in the page itself
  (ported "Readout" landing). So this route-group layout adds only the landing's
  film-grain overlay (.grain, a fixed pointer-events-none ::after defined in
  globals.css). The marketing sub-pages (pricing / terms / privacy / use-case)
  stay under app/(marketing) with the shared MarketingNav + Footer, untouched.

  Route-segment metadata for "/" (brief Step 9): the landing's own title +
  description + OG/Twitter, layered over the root layout's global metadata
  (metadataBase, icons, og:image). Kept em-dash-free per the house brand rule.
*/
const TITLE = "Quip: Know why your clips are worth posting";
const DESCRIPTION =
  "Quip turns long videos into short vertical clips, and tells you why each one will land. Explainable AI clips with a hook, a confidence score, and the reason it works.";

export const metadata: Metadata = {
  title: { absolute: TITLE },
  description: DESCRIPTION,
  alternates: { canonical: "/" },
  openGraph: { title: TITLE, description: DESCRIPTION },
  twitter: { title: TITLE, description: DESCRIPTION },
};

export default function HomeLayout({ children }: { children: React.ReactNode }) {
  return <div className="grain">{children}</div>;
}
