import type { MetadataRoute } from "next";
import { siteConfig } from "@/lib/site";

export default function sitemap(): MetadataRoute.Sitemap {
  const base = siteConfig.url;
  // Only indexable, canonical pages belong here. /login + /signup are
  // `robots: noindex` (auth surfaces), and /terms + /privacy are noindex too —
  // listing a noindexed URL in the sitemap is a contradictory crawl signal.
  return [
    { url: base, lastModified: new Date(), changeFrequency: "weekly", priority: 1 },
    { url: `${base}/pricing`, changeFrequency: "monthly", priority: 0.8 },
  ];
}
