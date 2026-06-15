/**
 * Single source of truth for site-wide identity / SEO metadata.
 * Consumed by app/layout.tsx (default metadata), sitemap.ts, robots.ts, and JSON-LD.
 * The production URL is env-driven so deploys (quip.ink) don't need a code change.
 */
export const siteConfig = {
  name: "Quip",
  // Founder sets NEXT_PUBLIC_SITE_URL at deploy; quip.ink is the canonical domain.
  url: process.env.NEXT_PUBLIC_SITE_URL ?? "https://quip.ink",
  tagline: "Don't just get clips. Know why they're worth posting.",
  description:
    "Quip turns long videos into short vertical clips — and tells you why each one will land. " +
    "Explainable AI clips with a hook, a confidence score, and the reason it works.",
  // OG image is generated at /opengraph-image (app/opengraph-image.tsx).
  ogImageAlt: "Quip — explainable AI video clips",
  // Support inbox — refunds are handled here (no self-serve refund button by design).
  supportEmail: process.env.NEXT_PUBLIC_SUPPORT_EMAIL ?? "ceo@quip.ink",
  // Founder can fill these in; used only for social cards / JSON-LD if present.
  twitterHandle: process.env.NEXT_PUBLIC_TWITTER_HANDLE ?? undefined,
} as const;

export type SiteConfig = typeof siteConfig;
