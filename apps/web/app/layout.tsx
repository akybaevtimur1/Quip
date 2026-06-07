import type { Metadata } from "next";
import { IBM_Plex_Mono, Onest, Unbounded } from "next/font/google";
import "./globals.css";

// Шрифты лендинга: Unbounded (дисплей), Onest (текст), IBM Plex Mono (тайм-коды/метрики).
const unbounded = Unbounded({ variable: "--font-unbounded", subsets: ["latin"], display: "swap" });
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
  title: "ClipFlow",
  description: "Нарезка вертикальных клипов из видео",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="ru"
      className={`${unbounded.variable} ${onest.variable} ${plexMono.variable} h-full`}
    >
      <body className="min-h-full bg-bg text-ink antialiased">{children}</body>
    </html>
  );
}
