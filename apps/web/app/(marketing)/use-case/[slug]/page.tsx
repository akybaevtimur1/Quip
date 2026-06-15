import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { buttonVariants } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";
import { Reveal } from "@/components/ui/Reveal";
import { Section } from "@/components/ui/Section";
import { buildUseCaseJsonLd } from "@/lib/jsonld";
import { siteConfig } from "@/lib/site";
import { getOptionalUser } from "@/lib/supabase/server";
import { getUseCase, USE_CASES } from "@/lib/useCases";

// Programmatic SEO landing pages — one real, content-rich page per high-intent
// query cluster (see lib/useCases.ts). Statically generated at build; unknown slugs
// 404. Russian-first; we declare og:locale ru_RU and inLanguage ru, and DON'T fake an
// EN hreflang alternate (none exists yet — that comes with the /ru i18n refactor).

type Params = { params: Promise<{ slug: string }> };

/** Pre-render every use-case page at build (fast, fully crawlable HTML). */
export function generateStaticParams() {
  return USE_CASES.map((u) => ({ slug: u.slug }));
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { slug } = await params;
  const uc = getUseCase(slug);
  if (!uc) return {};

  const path = `/use-case/${uc.slug}`;
  return {
    title: { absolute: uc.title },
    description: uc.metaDescription,
    alternates: { canonical: path },
    openGraph: {
      type: "website",
      siteName: siteConfig.name,
      title: uc.title,
      description: uc.metaDescription,
      url: `${siteConfig.url}${path}`,
      locale: uc.lang === "ru" ? "ru_RU" : "en_US",
    },
    twitter: {
      card: "summary_large_image",
      title: uc.title,
      description: uc.metaDescription,
    },
    robots: { index: true, follow: true },
  };
}

export default async function UseCasePage({ params }: Params) {
  const { slug } = await params;
  const uc = getUseCase(slug);
  if (!uc) notFound();

  const authed = Boolean(await getOptionalUser());
  const ctaHref = authed ? "/dashboard" : "/signup";
  const ctaLabel = authed ? "Открыть приложение" : "Попробовать бесплатно";
  // Sibling pages for internal linking (crawl depth + link equity).
  const related = USE_CASES.filter((u) => u.slug !== uc.slug).slice(0, 3);

  return (
    <>
      <script
        type="application/ld+json"
        // Static, server-controlled data (no user input). `<` escaped so the JSON
        // can't break out of the <script> context.
        dangerouslySetInnerHTML={{
          __html: JSON.stringify(buildUseCaseJsonLd(uc)).replace(/</g, "\\u003c"),
        }}
      />

      {/* Hero */}
      <Section className="pb-10 pt-16 sm:pb-14 sm:pt-24">
        <Container>
          <Reveal className="max-w-3xl">
            <p className="font-mono text-sm uppercase tracking-wide text-accent">Quip</p>
            <h1 className="mt-4 font-display text-display-lg text-ink sm:text-display-xl">{uc.h1}</h1>
            <p className="mt-5 max-w-2xl text-lead text-muted">{uc.intro}</p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Link href={ctaHref} className={buttonVariants({ variant: "primary", size: "lg" })}>
                {ctaLabel}
                <span aria-hidden>→</span>
              </Link>
              <Link href="/pricing" className={buttonVariants({ variant: "secondary", size: "lg" })}>
                Тарифы
              </Link>
            </div>
            {!authed && (
              <p className="mt-6 text-sm text-faint">
                <span className="font-medium text-muted">Без карты.</span> 2 видео в месяц бесплатно.
              </p>
            )}
          </Reveal>
        </Container>
      </Section>

      {/* How it works */}
      <Section className="py-16 sm:py-20">
        <Container>
          <Reveal>
            <h2 className="max-w-2xl font-display text-h2 text-ink sm:text-display-lg">
              Как это работает
            </h2>
          </Reveal>
          <Reveal>
            <div className="mt-12 grid gap-px overflow-hidden rounded-xl border border-line bg-line sm:grid-cols-3">
              {uc.steps.map((s, i) => (
                <div key={s.title} className="bg-bg p-7 sm:p-8">
                  <span className="font-mono text-sm tabular-nums text-accent">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <h3 className="mt-5 font-display text-h3 text-ink">{s.title}</h3>
                  <p className="mt-3 text-sm leading-relaxed text-muted">{s.body}</p>
                </div>
              ))}
            </div>
          </Reveal>
        </Container>
      </Section>

      {/* Benefits */}
      <Section className="py-16 sm:py-20">
        <Container>
          <Reveal>
            <h2 className="max-w-2xl font-display text-h2 text-ink sm:text-display-lg">
              Почему Quip
            </h2>
          </Reveal>
          <Reveal>
            <div className="mt-12 grid gap-6 sm:grid-cols-3">
              {uc.benefits.map((b) => (
                <div key={b.title} className="rounded-xl border border-line bg-surface p-7">
                  <h3 className="font-display text-h3 text-ink">{b.title}</h3>
                  <p className="mt-3 text-sm leading-relaxed text-muted">{b.body}</p>
                </div>
              ))}
            </div>
          </Reveal>
        </Container>
      </Section>

      {/* FAQ — rendered static (crawlable) + emitted as FAQPage JSON-LD above. */}
      <Section className="py-16 sm:py-20">
        <Container>
          <Reveal>
            <h2 className="max-w-2xl font-display text-h2 text-ink sm:text-display-lg">
              Частые вопросы
            </h2>
          </Reveal>
          <Reveal>
            <dl className="mt-10 max-w-3xl divide-y divide-line border-y border-line">
              {uc.faq.map((f) => (
                <div key={f.q} className="py-6">
                  <dt className="font-display text-h3 text-ink">{f.q}</dt>
                  <dd className="mt-2 text-sm leading-relaxed text-muted">{f.a}</dd>
                </div>
              ))}
            </dl>
          </Reveal>
        </Container>
      </Section>

      {/* Final CTA */}
      <Section className="relative overflow-hidden">
        <div
          aria-hidden
          className="pointer-events-none absolute left-1/2 top-1/2 size-[680px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-[radial-gradient(circle,rgba(255,90,61,.10),transparent_60%)]"
        />
        <Container className="relative">
          <Reveal className="mx-auto max-w-2xl text-center">
            <h2 className="font-display text-h2 text-ink sm:text-display-lg">{uc.ctaTitle}</h2>
            <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
              <Link href={ctaHref} className={buttonVariants({ variant: "primary", size: "lg" })}>
                {ctaLabel}
                <span aria-hidden>→</span>
              </Link>
            </div>
          </Reveal>

          {/* Internal links to sibling use-cases */}
          <Reveal className="mx-auto mt-16 max-w-3xl">
            <p className="text-center text-sm text-faint">Ещё сценарии</p>
            <div className="mt-5 grid gap-3 sm:grid-cols-3">
              {related.map((r) => (
                <Link
                  key={r.slug}
                  href={`/use-case/${r.slug}`}
                  className="rounded-lg border border-line bg-surface p-4 text-sm text-muted transition-colors hover:border-line-strong hover:text-ink"
                >
                  {r.h1}
                </Link>
              ))}
            </div>
          </Reveal>
        </Container>
      </Section>
    </>
  );
}
