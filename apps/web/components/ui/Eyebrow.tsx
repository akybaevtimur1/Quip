import { cn } from "@/lib/cn";

/** Small mono uppercase label with a coral dot — section kicker. */
export function Eyebrow({
  children,
  className,
  dot = true,
}: {
  children: React.ReactNode;
  className?: string;
  dot?: boolean;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-pill border border-line bg-surface px-3 py-1.5",
        "font-mono text-eyebrow uppercase text-muted",
        className,
      )}
    >
      {dot && (
        <span
          className="size-1.5 rounded-pill bg-accent shadow-[0_0_10px_1px_var(--color-accent)]"
          aria-hidden
        />
      )}
      {children}
    </span>
  );
}
