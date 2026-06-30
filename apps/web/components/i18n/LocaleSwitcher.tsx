"use client";

import { useLocale } from "next-intl";
import { useRouter } from "next/navigation";
import { useTransition } from "react";
import { cn } from "@/lib/cn";
import { LOCALE_COOKIE, LOCALES, type Locale, resolveLocale } from "@/i18n/locale";

/**
 * Compact EN / RU segmented control. Cookie mode: it writes the `NEXT_LOCALE` cookie
 * (1-year, SameSite=Lax) and `router.refresh()`es so the server re-renders the tree
 * with the new locale — no URL change, so it never collides with the `/ru/use-case`
 * SEO routes or the Supabase auth redirects. Mirrors the SourceForm "Auto / Custom"
 * segmented control so it reads as native chrome.
 */
const LABELS: Record<Locale, string> = { en: "EN", ru: "RU" };

/** Persist the chosen locale in the NEXT_LOCALE cookie (1 year, site-wide, Lax: survives
 *  reloads, sent on top-level navigations). Module scope so the cookie write isn't a
 *  component-body mutation (react-hooks/immutability). */
function persistLocale(locale: Locale) {
  document.cookie = `${LOCALE_COOKIE}=${locale}; path=/; max-age=${60 * 60 * 24 * 365}; samesite=lax`;
}

export function LocaleSwitcher({ className }: { className?: string }) {
  const active = resolveLocale(useLocale());
  const router = useRouter();
  const [pending, startTransition] = useTransition();

  function choose(locale: Locale) {
    if (locale === active) return;
    persistLocale(locale);
    startTransition(() => router.refresh());
  }

  return (
    <div
      className={cn(
        "inline-flex rounded-md border border-line bg-surface p-0.5",
        pending && "opacity-70",
        className,
      )}
      role="group"
      aria-label="Language"
    >
      {LOCALES.map((locale) => (
        <button
          key={locale}
          type="button"
          onClick={() => choose(locale)}
          disabled={pending}
          aria-pressed={active === locale}
          className={cn(
            "rounded-sm px-2 py-1 font-mono text-[12px] font-medium uppercase tracking-[0.04em] transition disabled:opacity-50",
            active === locale
              ? "bg-surface-3 text-ink shadow-[0_0_0_1px_var(--color-line-strong)]"
              : "text-muted hover:text-ink",
          )}
        >
          {LABELS[locale]}
        </button>
      ))}
    </div>
  );
}
