import Link from "next/link";
import { Container } from "@/components/ui/Container";
import { Logo } from "@/components/ui/Logo";

const cols: { title: string; links: { href: string; label: string }[] }[] = [
  {
    title: "Product",
    links: [
      { href: "/#how-it-works", label: "How it works" },
      { href: "/#why", label: "Why Quip" },
      { href: "/#pricing", label: "Pricing" },
      { href: "/#faq", label: "FAQ" },
    ],
  },
  {
    title: "Get started",
    links: [
      { href: "/signup", label: "Create account" },
      { href: "/login", label: "Sign in" },
      { href: "/dashboard", label: "Open the app" },
    ],
  },
  {
    title: "Legal",
    links: [
      { href: "/terms", label: "Terms" },
      { href: "/privacy", label: "Privacy" },
    ],
  },
];

export function Footer() {
  return (
    <footer className="border-t border-line">
      <Container className="grid gap-12 py-16 sm:grid-cols-2 lg:grid-cols-[1.4fr_repeat(3,1fr)]">
        <div className="max-w-xs">
          <Logo />
          <p className="mt-4 text-sm leading-relaxed text-muted">
            Fewer clips, but you know why to post them. Explainable AI clips from your long videos.
          </p>
        </div>
        {cols.map((col) => (
          <div key={col.title}>
            <h2 className="font-mono text-eyebrow uppercase text-faint">{col.title}</h2>
            <ul className="mt-4 space-y-3">
              {col.links.map((l) => (
                <li key={l.href}>
                  <Link
                    href={l.href}
                    className="text-sm text-muted transition-colors hover:text-ink"
                  >
                    {l.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </Container>
      <Container className="flex flex-col items-center justify-between gap-3 border-t border-line py-6 sm:flex-row">
        <p className="text-xs text-faint">© {new Date().getFullYear()} Quip. All rights reserved.</p>
        <p className="text-xs text-faint">Honest pricing. No credit casino. No surprise paywalls.</p>
      </Container>
    </footer>
  );
}
