import { cn } from "@/lib/cn";

// Inline mono numeral — tabular figures + slashed zero (via .font-mono in globals).
// Use for every timecode, duration, %, price, score so numbers align by construction
// (the "mono numerals as signature" rule, enforced instead of remembered).
export function Numeral({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <span className={cn("font-mono tabular-nums", className)}>{children}</span>;
}
