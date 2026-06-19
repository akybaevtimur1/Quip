import { Analytics } from "@vercel/analytics/next";
import { SpeedInsights } from "@vercel/speed-insights/next";
import type { Metadata } from "next";
import { IBM_Plex_Mono, Onest } from "next/font/google";
import { YandexMetrika } from "@/components/analytics/YandexMetrika";
import { FeedbackWidget } from "@/components/app/FeedbackWidget";
import { NavProgress } from "@/components/ui/NavProgress";
import { siteConfig } from "@/lib/site";
import "./globals.css";

// Quip UI fonts. Onest (display + body) matches the live brand at quip.ink;
// IBM Plex Mono carries timecodes / confidence scores / prices (tabular figures).
const onest = Onest({
  variable: "--font-onest",
  subsets: ["latin", "cyrillic"],
  display: "swap",
});
const plexMono = IBM_Plex_Mono({
  variable: "--font-plex-mono",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL(siteConfig.url),
  title: {
    default: `${siteConfig.name} — ${siteConfig.tagline}`,
    template: `%s · ${siteConfig.name}`,
  },
  description: siteConfig.description,
  applicationName: siteConfig.name,
  keywords: [
    "AI video clipper",
    "podcast to shorts",
    "repurpose long videos",
    "vertical clips",
    "explainable AI clips",
    "clip generator",
  ],
  authors: [{ name: siteConfig.name }],
  openGraph: {
    type: "website",
    siteName: siteConfig.name,
    title: `${siteConfig.name} — ${siteConfig.tagline}`,
    description: siteConfig.description,
    url: siteConfig.url,
    // Default landing copy is English; Russian use-case pages set ru_RU themselves.
    locale: "en_US",
    alternateLocale: ["ru_RU"],
  },
  twitter: {
    card: "summary_large_image",
    title: `${siteConfig.name} — ${siteConfig.tagline}`,
    description: siteConfig.description,
    creator: siteConfig.twitterHandle,
  },
  robots: { index: true, follow: true },
  // Search-engine ownership verification. Set the env vars in Vercel once
  // (Google Search Console + Yandex.Webmaster give you the token). Yandex.Webmaster
  // is a P0 for the Russian market — Yandex is ~73% of RU search. Undefined env =
  // tag omitted (no empty meta).
  verification: {
    google: siteConfig.googleVerification,
    yandex: siteConfig.yandexVerification,
  },
  // Favicon / app icon come from app/icon.png + app/apple-icon.png (Next file convention).
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${onest.variable} ${plexMono.variable} h-full`}
      suppressHydrationWarning
    >
      <body className="min-h-full bg-bg text-ink antialiased">
        {/* Mark JS active before paint so scroll-reveal only hides content when it
            can actually animate it back in (no-JS / crawlers see everything). */}
        <script
          dangerouslySetInnerHTML={{ __html: "document.documentElement.classList.add('js')" }}
        />
        <NavProgress />
        {children}
        <FeedbackWidget />
        {/* Vercel Web Analytics — НИЧЕГО не рисует, только шлёт pageview/событие в Vercel
            (смотреть на дашборде проекта, вкладка Analytics). На Vercel надо один раз включить
            Analytics в настройках проекта; в локальном dev — no-op. */}
        <Analytics />
        {/* Vercel Speed Insights — измеряет производительность страниц на реальных устройствах
            пользователей (Core Web Vitals). Включается в настройках проекта на Vercel; в dev — no-op. */}
        <SpeedInsights />
        {/* Yandex.Metrica — поведенческие факторы для ранжирования в Яндексе (Вебвизор). */}
        <YandexMetrika />
      </body>
    </html>
  );
}
