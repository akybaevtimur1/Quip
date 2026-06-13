import { Menu } from "lucide-react";
import Link from "next/link";
import { buttonVariants } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";
import { Logo } from "@/components/ui/Logo";

const links = [
  { href: "#how-it-works", label: "How it works" },
  { href: "#why", label: "Why Quip" },
  { href: "#pricing", label: "Pricing" },
  { href: "#faq", label: "FAQ" },
];

/** Sticky marketing nav. RSC; mobile menu is a native <details> (zero JS, a11y). */
export function MarketingNav() {
  return (
    <header className="sticky top-0 z-50 border-b border-line/70 bg-bg/75 backdrop-blur-xl">
      <Container className="flex h-16 items-center justify-between gap-6">
        <Logo />

        <nav aria-label="Primary" className="hidden items-center gap-8 md:flex">
          {links.map((l) => (
            <a
              key={l.href}
              href={l.href}
              className="text-sm text-muted transition-colors duration-200 hover:text-ink"
            >
              {l.label}
            </a>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          <Link
            href="/login"
            className="hidden rounded-md px-3 py-2 text-sm text-muted transition-colors hover:text-ink sm:inline-flex"
          >
            Sign in
          </Link>
          <Link href="/signup" className={buttonVariants({ variant: "primary", size: "sm" })}>
            Try it free
          </Link>

          {/* mobile menu (native, no JS) */}
          <details className="group relative md:hidden">
            <summary
              className="flex size-9 cursor-pointer list-none items-center justify-center rounded-md border border-line text-muted [&::-webkit-details-marker]:hidden"
              aria-label="Open menu"
            >
              <Menu className="size-5" />
            </summary>
            <div className="absolute right-0 top-11 w-56 rounded-lg border border-line bg-surface p-2 shadow-[0_24px_60px_-28px_rgba(0,0,0,.9)]">
              {links.map((l) => (
                <a
                  key={l.href}
                  href={l.href}
                  className="block rounded-md px-3 py-2.5 text-sm text-muted transition-colors hover:bg-surface-2 hover:text-ink"
                >
                  {l.label}
                </a>
              ))}
              <Link
                href="/login"
                className="mt-1 block rounded-md px-3 py-2.5 text-sm text-muted transition-colors hover:bg-surface-2 hover:text-ink"
              >
                Sign in
              </Link>
            </div>
          </details>
        </div>
      </Container>
    </header>
  );
}
