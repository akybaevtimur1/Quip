import { cn } from "@/lib/cn";

// The instrument-label voice: a small mono-uppercase kicker. Single source for section
// labels / panel headers / kickers — retires the hand-rolled text-[9px]/[10px]/[11px]
// uppercase strings scattered across the app so every label reads metronomically.
export type EyebrowTone = "muted" | "faint" | "ink" | "accent";

const toneClass: Record<EyebrowTone, string> = {
  muted: "text-muted",
  faint: "text-faint",
  ink: "text-ink",
  accent: "text-accent",
};

export function Eyebrow({
  children,
  tone = "muted",
  className,
  as: Tag = "span",
}: {
  children: React.ReactNode;
  tone?: EyebrowTone;
  className?: string;
  as?: "span" | "div" | "p" | "h2" | "h3";
}) {
  return (
    <Tag className={cn("font-mono text-eyebrow uppercase", toneClass[tone], className)}>{children}</Tag>
  );
}
