import Link from "next/link";
import { MobileMenu } from "@/components/marketing/MobileMenu";
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

          <MobileMenu links={links} />
        </div>
      </Container>
    </header>
  );
}
