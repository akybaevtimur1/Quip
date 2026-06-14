import type { Metadata } from "next";
import { IBM_Plex_Mono, Onest } from "next/font/google";
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
  },
  twitter: {
    card: "summary_large_image",
    title: `${siteConfig.name} — ${siteConfig.tagline}`,
    description: siteConfig.description,
    creator: siteConfig.twitterHandle,
  },
  robots: { index: true, follow: true },
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
      </body>
    </html>
  );
}
