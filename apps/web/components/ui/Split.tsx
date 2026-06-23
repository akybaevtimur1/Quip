import { cn } from "@/lib/cn";

// Asymmetric rail + canvas layout — the calibrated-workspace alternative to the
// centered-card stack. Stacks on mobile, splits at lg. Class strings are literal so
// Tailwind can statically extract the arbitrary grid templates.
export type SplitVariant = "main-rail" | "rail-main" | "wide-narrow" | "balanced";

const variantCols: Record<SplitVariant, string> = {
  // content + a focused right rail (dashboard / account)
  "main-rail": "lg:grid-cols-[minmax(0,1fr)_340px]",
  // a left rail + the working canvas
  "rail-main": "lg:grid-cols-[300px_minmax(0,1fr)]",
  // wide content + a narrow secondary column
  "wide-narrow": "lg:grid-cols-[minmax(0,1fr)_300px]",
  "balanced": "lg:grid-cols-2",
};

export function Split({
  variant = "main-rail",
  gap = "gap-8 lg:gap-12",
  className,
  children,
}: {
  variant?: SplitVariant;
  gap?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return <div className={cn("grid items-start", variantCols[variant], gap, className)}>{children}</div>;
}
