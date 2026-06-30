import { cookies } from "next/headers";
import { getRequestConfig } from "next-intl/server";
import { LOCALE_COOKIE, resolveLocale } from "./locale";

/**
 * next-intl request config — COOKIE MODE (no `[locale]` URL segment, no `proxy.ts`).
 *
 * WHY cookie mode: the funnel is auth-gated / noindex and a `[locale]` refactor would
 * collide with the existing `/ru/use-case` SEO routes and the Supabase auth redirects.
 * So instead of a path segment we read the locale from the `NEXT_LOCALE` cookie that the
 * EN/RU switcher writes. Reading `cookies()` here opts the funnel into dynamic rendering,
 * which is already the case (the home page reads the session, the app is auth-gated).
 *
 * Wired into the build by `createNextIntlPlugin('./i18n/request.ts')` in next.config.ts.
 */
export default getRequestConfig(async () => {
  const store = await cookies();
  const locale = resolveLocale(store.get(LOCALE_COOKIE)?.value);

  return {
    locale,
    // Static per-locale catalogs (auth + app shell). The landing keeps its larger,
    // structured copy in lib/landingContent.ts (bilingual, like lib/useCases.ts).
    messages: (await import(`../messages/${locale}.json`)).default,
  };
});
