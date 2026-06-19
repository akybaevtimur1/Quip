import type { MetadataRoute } from "next";
import { siteConfig } from "@/lib/site";
import { USE_CASES } from "@/lib/useCases";

export default function sitemap(): MetadataRoute.Sitemap {
  const base = siteConfig.url;
  // Only indexable, canonical pages belong here. /login + /signup are
  // `robots: noindex` (auth surfaces), and /terms + /privacy are noindex too —
  // listing a noindexed URL in the sitemap is a contradictory crawl signal.
  const core: MetadataRoute.Sitemap = [
    { url: base, lastModified: new Date(), changeFrequency: "weekly", priority: 1 },
    { url: `${base}/pricing`, changeFrequency: "monthly", priority: 0.8 },
  ];

  // Programmatic SEO landing pages — one per high-intent query cluster, BILINGUAL.
  // Each use-case has an EN page (/use-case/<slug>) and a RU page (/ru/use-case/<slug>).
  // We list BOTH and declare the hreflang pair via `alternates.languages` (en / ru /
  // x-default) so the sitemap matches the in-page <link rel="alternate" hreflang> tags.
  const useCasePages: MetadataRoute.Sitemap = USE_CASES.flatMap((u) => {
    const enUrl = `${base}/use-case/${u.slug}`;
    const ruUrl = `${base}/ru/use-case/${u.slug}`;
    const languages = { en: enUrl, ru: ruUrl, "x-default": enUrl };
    return [
      {
        url: enUrl,
        lastModified: new Date(),
        changeFrequency: "monthly" as const,
        priority: 0.8,
        alternates: { languages },
      },
      {
        url: ruUrl,
        lastModified: new Date(),
        changeFrequency: "monthly" as const,
        priority: 0.8,
        alternates: { languages },
      },
    ];
  });

  return [...core, ...useCasePages];
}
