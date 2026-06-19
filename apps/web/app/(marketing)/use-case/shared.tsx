import type { Metadata } from "next";
import Link from "next/link";
import { buttonVariants } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";
import { Reveal } from "@/components/ui/Reveal";
import { Section } from "@/components/ui/Section";
import { buildUseCaseJsonLd } from "@/lib/jsonld";
import { siteConfig } from "@/lib/site";
import { getOptionalUser } from "@/lib/supabase/server";
import {
  getUseCase,
  getUseCaseContent,
  type Locale,
  USE_CASES,
  localeUseCasePath,
} from "@/lib/useCases";

// Shared renderer + metadata for the bilingual programmatic SEO use-case pages.
// Two routes reuse this with a `locale`:
//   - EN (default, Google):  app/(marketing)/use-case/[slug]/page.tsx        → "en"
//   - RU (Yandex):           app/(marketing)/ru/use-case/[slug]/page.tsx     → "ru"
// hreflang ties the pair together (en / ru / x-default) so each engine serves the
// right language. The root <html lang> stays "en" globally (App Router sets it once
// in the root layout); the RU page still signals Russian via hreflang + og:locale
// ru_RU + JSON-LD inLanguage ru + Russian content, which is what crawlers actually use.

/** Per-locale page chrome (everything that isn't use-case copy). */
const CHROME: Record<Locale, {
  howItWorks: string;
  whyQuip: string;
  faq: string;
  moreUseCases: string;
  pricing: string;
  noCard: string;
  noCardEmphasis: string;
  ctaOpen: string;
  ctaTry: string;
}> = {
  en: {
    howItWorks: "How it works",
    whyQuip: "Why Quip",
    faq: "FAQ",
    moreUseCases: "More use cases",
    pricing: "Pricing",
    noCardEmphasis: "No card required.",
    noCard: "2 free videos every month.",
    ctaOpen: "Open app",
    ctaTry: "Try it free",
  },
  ru: {
    howItWorks: "Как это работает",
    whyQuip: "Почему Quip",
    faq: "Частые вопросы",
    moreUseCases: "Ещё кейсы",
    pricing: "Тарифы",
    noCardEmphasis: "Без карты.",
    noCard: "2 видео бесплатно каждый месяц.",
    ctaOpen: "Открыть приложение",
    ctaTry: "Попробовать бесплатно",
  },
};

/** Build metadata for a use-case page in the given locale.
 *  Emits canonical (own path) + hreflang alternates (en / ru / x-default) + og:locale.
 *  Returns {} for unknown slugs (the page itself notFound()s). */
export async function buildUseCaseMetadata(
  slug: string,
  locale: Locale,
): Promise<Metadata> {
  const uc = getUseCase(slug);
  if (!uc) return {};
  const content = getUseCaseContent(uc, locale);

  const enPath = localeUseCasePath(uc.slug, "en");
  const ruPath = localeUseCasePath(uc.slug, "ru");
  const ownPath = locale === "ru" ? ruPath : enPath;

  return {
    title: { absolute: content.title },
    description: content.metaDescription,
    alternates: {
      // Each page is canonical to itself; the hreflang cluster ties the pair together.
      canonical: ownPath,
      // Next resolves these root-relative paths against metadataBase → absolute
      // <link rel="alternate" hreflang=…> tags. x-default points at the EN page.
      languages: {
        en: enPath,
        ru: ruPath,
        "x-default": enPath,
      },
    },
    openGraph: {
      type: "website",
      siteName: siteConfig.name,
      title: content.title,
      description: content.metaDescription,
      url: `${siteConfig.url}${ownPath}`,
      locale: locale === "ru" ? "ru_RU" : "en_US",
      alternateLocale: locale === "ru" ? ["en_US"] : ["ru_RU"],
    },
    twitter: {
      card: "summary_large_image",
      title: content.title,
      description: content.metaDescription,
    },
    robots: { index: true, follow: true },
  };
}

/** Shared page body for a use-case in the given locale. Caller (route) resolves
 *  params + handles notFound; this renders the resolved use-case. */
export async function UseCasePageBody({
  slug,
  locale,
}: {
  slug: string;
  locale: Locale;
}) {
  // Caller already guarantees the slug exists (route notFound()s otherwise),
  // but re-resolve here so this component is self-contained and type-safe.
  const uc = getUseCase(slug);
  if (!uc) return null;
  const content = getUseCaseContent(uc, locale);
  const t = CHROME[locale];

  const authed = Boolean(await getOptionalUser());
  const ctaHref = authed ? "/dashboard" : "/signup";
  const ctaLabel = authed ? t.ctaOpen : t.ctaTry;
  // Sibling pages for internal linking (crawl depth + link equity). Links stay
  // within the current locale so the crawl graph doesn't cross languages.
  const related = USE_CASES.filter((u) => u.slug !== uc.slug).slice(0, 3);
  // Pricing is EN-only (no /ru/pricing variant exists), so both locales link to /pricing.
  const pricingHref = "/pricing";

  return (
    <>
      <script
        type="application/ld+json"
        // Static, server-controlled data (no user input). `<` escaped so the JSON
        // can't break out of the <script> context.
        dangerouslySetInnerHTML={{
          __html: JSON.stringify(buildUseCaseJsonLd(uc, locale)).replace(/</g, "\\u003c"),
        }}
      />

      {/* Hero */}
      <Section className="pb-10 pt-16 sm:pb-14 sm:pt-24">
        <Container>
          <Reveal className="max-w-3xl">
            <p className="font-mono text-sm uppercase tracking-wide text-accent">Quip</p>
            <h1 className="mt-4 font-display text-display-lg text-ink sm:text-display-xl">
              {content.h1}
            </h1>
            <p className="mt-5 max-w-2xl text-lead text-muted">{content.intro}</p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Link href={ctaHref} className={buttonVariants({ variant: "primary", size: "lg" })}>
                {ctaLabel}
                <span aria-hidden>→</span>
              </Link>
              <Link href={pricingHref} className={buttonVariants({ variant: "secondary", size: "lg" })}>
                {t.pricing}
              </Link>
            </div>
            {!authed && (
              <p className="mt-6 text-sm text-faint">
                <span className="font-medium text-muted">{t.noCardEmphasis}</span> {t.noCard}
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
              {t.howItWorks}
            </h2>
          </Reveal>
          <Reveal>
            <div className="mt-12 grid gap-px overflow-hidden rounded-xl border border-line bg-line sm:grid-cols-3">
              {content.steps.map((s, i) => (
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
              {t.whyQuip}
            </h2>
          </Reveal>
          <Reveal>
            <div className="mt-12 grid gap-6 sm:grid-cols-3">
              {content.benefits.map((b) => (
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
            <h2 className="max-w-2xl font-display text-h2 text-ink sm:text-display-lg">{t.faq}</h2>
          </Reveal>
          <Reveal>
            <dl className="mt-10 max-w-3xl divide-y divide-line border-y border-line">
              {content.faq.map((f) => (
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
            <h2 className="font-display text-h2 text-ink sm:text-display-lg">{content.ctaTitle}</h2>
            <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
              <Link href={ctaHref} className={buttonVariants({ variant: "primary", size: "lg" })}>
                {ctaLabel}
                <span aria-hidden>→</span>
              </Link>
            </div>
          </Reveal>

          {/* Internal links to sibling use-cases (same locale). */}
          <Reveal className="mx-auto mt-16 max-w-3xl">
            <p className="text-center text-sm text-faint">{t.moreUseCases}</p>
            <div className="mt-5 grid gap-3 sm:grid-cols-3">
              {related.map((r) => (
                <Link
                  key={r.slug}
                  href={localeUseCasePath(r.slug, locale)}
                  className="rounded-lg border border-line bg-surface p-4 text-sm text-muted transition-colors hover:border-line-strong hover:text-ink"
                >
                  {getUseCaseContent(r, locale).h1}
                </Link>
              ))}
            </div>
          </Reveal>
        </Container>
      </Section>
    </>
  );
}
