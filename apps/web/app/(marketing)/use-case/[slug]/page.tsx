import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getUseCase, USE_CASES } from "@/lib/useCases";
import { buildUseCaseMetadata, UseCasePageBody } from "../shared";

// Programmatic SEO landing pages — one real, content-rich page per high-intent query
// cluster (see lib/useCases.ts). This is the EN route (default, for Google); the RU
// route lives at /ru/use-case/[slug]. Both reuse the shared renderer + metadata helper.
// Statically generated at build; unknown slugs 404. hreflang ties the EN/RU pair
// together (declared in buildUseCaseMetadata): en / ru / x-default.

type Params = { params: Promise<{ slug: string }> };

/** Pre-render every EN use-case page at build (fast, fully crawlable HTML). */
export function generateStaticParams() {
  return USE_CASES.map((u) => ({ slug: u.slug }));
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { slug } = await params;
  return buildUseCaseMetadata(slug, "en");
}

export default async function UseCasePage({ params }: Params) {
  const { slug } = await params;
  if (!getUseCase(slug)) notFound();
  return <UseCasePageBody slug={slug} locale="en" />;
}
