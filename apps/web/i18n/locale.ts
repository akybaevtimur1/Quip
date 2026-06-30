/**
 * Locale primitives for the RU/EN interface toggle (cookie mode, no `[locale]` URL
 * segment). Pure module — NO `next/headers` / `next-intl/server` imports — so it is
 * safe to import from client components AND unit-test in isolation.
 *
 * Shipped scope (2026-06-30): the core funnel (landing, auth, dashboard shell). The
 * editor + worker-side `JobError` reasons are still English-only (deferred). New
 * user-facing strings go through `next-intl` (`t()`) / the bilingual landing content,
 * never hardcoded mixed RU/EN.
 */

export const LOCALES = ["en", "ru"] as const;
export type Locale = (typeof LOCALES)[number];

/** App default when no (or an unknown) cookie is present — e.g. crawlers, which never
 *  send the cookie, always get English. Keeps the SEO marketing pages English by default. */
export const DEFAULT_LOCALE: Locale = "en";

/** Cookie that carries the chosen locale. `NEXT_LOCALE` is the conventional name
 *  next-intl reads; 1-year, SameSite=Lax, set by the EN/RU switcher. */
export const LOCALE_COOKIE = "NEXT_LOCALE";

/** Type guard: is this value one of our supported locales? */
export function isLocale(value: unknown): value is Locale {
  return typeof value === "string" && (LOCALES as readonly string[]).includes(value);
}

/** Resolve any cookie/header value to a supported locale, falling back to the default
 *  for missing/unknown input. The single chokepoint for "what locale is this request". */
export function resolveLocale(value: string | null | undefined): Locale {
  return isLocale(value) ? value : DEFAULT_LOCALE;
}
