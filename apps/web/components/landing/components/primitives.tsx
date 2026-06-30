import type { ReactNode } from "react";
import type { MomentType } from "@/lib/landingContent";

export function Container({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={`container-page ${className}`}>{children}</div>;
}

/* Section kicker: a short coral tick + a brighter mono label. Reads as an
   intentional instrument channel-label, not a faint code comment. Rationed to a
   few key sections; its lone coral tick is the section's one coral mark per fold. */
export function Eyebrow({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-3 ${className}`}>
      <span aria-hidden className="h-px w-7 bg-accent" />
      <span className="font-mono text-[11.5px] font-medium uppercase tracking-[0.18em] text-muted">
        {children}
      </span>
    </span>
  );
}

/* The lone coral "syntax highlight" chip wrapping one headline word. */
export function WordChip({ children }: { children: ReactNode }) {
  return (
    <span className="relative inline-block whitespace-nowrap rounded-[6px] bg-accent px-[0.22em] pb-[0.02em] text-bg">
      {children}
    </span>
  );
}

/* Functional moment-type badge. Lives ONLY inside framed product surfaces. */
const BADGE_STYLE: Record<MomentType, string> = {
  hook: "text-hook border-hook/35 bg-hook/10",
  peak: "text-peak border-peak/35 bg-peak/10",
  thought: "text-thought border-thought/35 bg-thought/10",
  quote: "text-quote border-quote/35 bg-quote/10",
};

export function TypeBadge({
  type,
  label,
  className = "",
}: {
  type: MomentType;
  /** Localized moment-type label (from getLandingContent / clip.typeLabel). */
  label: string;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center rounded-pill border px-2 py-[3px] font-mono text-[10px] font-medium uppercase tracking-[0.12em] ${BADGE_STYLE[type]} ${className}`}
    >
      {label}
    </span>
  );
}

/* Section wrapper with consistent vertical rhythm + anchor id. */
export function Section({
  id,
  children,
  className = "",
  pad = "py-28 md:py-40",
}: {
  id?: string;
  children: ReactNode;
  className?: string;
  pad?: string;
}) {
  return (
    <section id={id} className={`relative ${pad} ${className}`}>
      {children}
    </section>
  );
}
