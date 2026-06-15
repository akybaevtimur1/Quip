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

  // Programmatic SEO landing pages (one per high-intent query cluster).
  const useCasePages: MetadataRoute.Sitemap = USE_CASES.map((u) => ({
    url: `${base}/use-case/${u.slug}`,
    lastModified: new Date(),
    changeFrequency: "monthly",
    priority: 0.8,
  }));

  return [...core, ...useCasePages];
}
