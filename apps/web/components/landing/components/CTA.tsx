import type { ReactNode } from "react";
import { ArrowRight } from "@phosphor-icons/react/dist/ssr";

// emil: press feedback via scale(0.97); strong ease-out; transform/opacity only.
const base =
  "group inline-flex items-center justify-center gap-2 rounded-[10px] font-sans font-medium transition-[transform,background-color,border-color] duration-200 ease-[var(--ease-out)] hover:-translate-y-px active:scale-[0.97] active:translate-y-0 focus-visible:outline-none";

const sizes = {
  md: "h-11 px-5 text-[15px]",
  lg: "h-12 px-6 text-[15px]",
};

/* Primary action. Coral fill, near-black text (AA-safe ~7:1), the one action that matters. */
export function PrimaryCTA({
  children,
  href,
  size = "md",
  arrow = true,
  className = "",
}: {
  children: ReactNode;
  href: string;
  size?: keyof typeof sizes;
  arrow?: boolean;
  className?: string;
}) {
  return (
    <a
      href={href}
      className={`${base} ${sizes[size]} bg-accent text-bg hover:bg-[var(--color-accent-2)] ${className}`}
    >
      {children}
      {arrow && (
        <ArrowRight
          weight="bold"
          className="size-4 transition-transform duration-150 ease-[var(--ease-snappy)] group-hover:translate-x-0.5"
        />
      )}
    </a>
  );
}

/* Secondary action. Transparent, hairline border, surface-lift on hover. Never spends coral. */
export function GhostCTA({
  children,
  href,
  size = "md",
  className = "",
}: {
  children: ReactNode;
  href: string;
  size?: keyof typeof sizes;
  className?: string;
}) {
  return (
    <a
      href={href}
      className={`${base} ${sizes[size]} border border-line-strong bg-transparent text-ink hover:bg-surface ${className}`}
    >
      {children}
    </a>
  );
}
