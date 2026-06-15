import { FAQ } from "@/lib/faq";
import { PLANS } from "@/lib/plans";
import { siteConfig } from "@/lib/site";
import type { UseCase } from "@/lib/useCases";

/** Structured data for the landing page: Organization + SoftwareApplication
 *  (with plan offers) + FAQPage. Rendered as a single ld+json @graph.
 *  `inLanguage` is an array (en + ru) — signals a bilingual product, not monolingual. */
export function buildHomeJsonLd(): Record<string, unknown> {
  return {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Organization",
        "@id": `${siteConfig.url}/#organization`,
        name: siteConfig.name,
        url: siteConfig.url,
        logo: `${siteConfig.url}/icon.png`,
      },
      {
        "@type": "SoftwareApplication",
        name: siteConfig.name,
        applicationCategory: "MultimediaApplication",
        operatingSystem: "Web",
        description: siteConfig.description,
        url: siteConfig.url,
        inLanguage: ["en", "ru"],
        offers: PLANS.map((p) => ({
          "@type": "Offer",
          name: p.name,
          price: p.price,
          priceCurrency: "USD",
        })),
      },
      {
        "@type": "FAQPage",
        mainEntity: FAQ.map((f) => ({
          "@type": "Question",
          name: f.q,
          acceptedAnswer: { "@type": "Answer", text: f.a },
        })),
      },
    ],
  };
}

/** Structured data for a programmatic /use-case/<slug> page:
 *  BreadcrumbList + FAQPage, tied to the site Organization. The per-page FAQ
 *  schema is what lets these pages win FAQ rich results for their query. */
export function buildUseCaseJsonLd(useCase: UseCase): Record<string, unknown> {
  const pageUrl = `${siteConfig.url}/use-case/${useCase.slug}`;
  return {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "BreadcrumbList",
        itemListElement: [
          { "@type": "ListItem", position: 1, name: siteConfig.name, item: siteConfig.url },
          { "@type": "ListItem", position: 2, name: useCase.h1, item: pageUrl },
        ],
      },
      {
        "@type": "FAQPage",
        inLanguage: useCase.lang,
        mainEntity: useCase.faq.map((f) => ({
          "@type": "Question",
          name: f.q,
          acceptedAnswer: { "@type": "Answer", text: f.a },
        })),
      },
    ],
  };
}
