import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getUseCase, USE_CASES } from "@/lib/useCases";
import { buildUseCaseMetadata, UseCasePageBody } from "../../../use-case/shared";

// RU route for the bilingual programmatic SEO use-case pages (for Yandex; ~73% of RU
// search). Mirrors the EN route at /use-case/[slug] but renders Russian content and
// signals ru via hreflang + og:locale ru_RU + JSON-LD inLanguage ru. Both routes reuse
// the shared renderer + metadata helper. Statically generated; unknown slugs 404.
//
// NOTE: the root <html lang> stays "en" globally (App Router sets it once in the root
// layout). Per-route lang would need a bigger refactor; search engines rely on
// hreflang + og:locale + JSON-LD inLanguage + the Russian content, all of which say ru.

type Params = { params: Promise<{ slug: string }> };

/** Pre-render every RU use-case page at build (fast, fully crawlable HTML). */
export function generateStaticParams() {
  return USE_CASES.map((u) => ({ slug: u.slug }));
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { slug } = await params;
  return buildUseCaseMetadata(slug, "ru");
}

export default async function RuUseCasePage({ params }: Params) {
  const { slug } = await params;
  if (!getUseCase(slug)) notFound();
  return <UseCasePageBody slug={slug} locale="ru" />;
}
