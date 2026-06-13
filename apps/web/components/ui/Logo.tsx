import Link from "next/link";
import { cn } from "@/lib/cn";

/** Quip wordmark: coral mark + Onest-extrabold wordmark. Coral is the one
 *  brand color (also the hook plate burned into every exported clip). */
export function Logo({
  className,
  href = "/",
  size = "md",
}: {
  className?: string;
  href?: string | null;
  size?: "sm" | "md";
}) {
  const inner = (
    <span className="inline-flex items-center gap-2">
      <span
        className={cn(
          "grid shrink-0 place-items-center rounded-md bg-accent text-white",
          "shadow-[0_1px_0_rgba(255,255,255,.25)_inset]",
          size === "sm" ? "size-6" : "size-7",
        )}
        aria-hidden
      >
        <svg viewBox="0 0 24 24" fill="none" className={size === "sm" ? "size-3.5" : "size-4"}>
          <path d="M9 7.2v9.6l7.2-4.8L9 7.2Z" fill="currentColor" />
        </svg>
      </span>
      <span
        className={cn(
          "font-display font-extrabold tracking-tight text-ink",
          size === "sm" ? "text-base" : "text-lg",
        )}
      >
        Quip
      </span>
    </span>
  );

  if (href) {
    return (
      <Link href={href} aria-label="Quip — home" className={cn("inline-flex items-center", className)}>
        {inner}
      </Link>
    );
  }
  return <span className={cn("inline-flex items-center", className)}>{inner}</span>;
}
