import { Loader2 } from "lucide-react";
import { cn } from "@/lib/cn";

// Token-sized spinner wrapper so the 20+ ad-hoc Loader2 usages share one size/voice.
export type SpinnerSize = "sm" | "md" | "lg";

const sizeClass: Record<SpinnerSize, string> = {
  sm: "size-4",
  md: "size-5",
  lg: "size-6",
};

export function Spinner({ size = "md", className }: { size?: SpinnerSize; className?: string }) {
  return <Loader2 className={cn("animate-spin text-muted", sizeClass[size], className)} aria-hidden />;
}
