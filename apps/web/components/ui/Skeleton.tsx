import { cn } from "@/lib/cn";

// Calm loading placeholder on the warm ladder. The pulse is clamped to ~0 by the global
// reduced-motion rule. Reserve real layout space with one so the pipeline (minutes long)
// reads as "computing precisely" instead of jumping when data lands.
export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn("animate-pulse rounded-md bg-surface-2", className)} />;
}
