import { cn } from "@/lib/cn";

/** Surface card with a hairline border. Elevation = surface + border (no shadow).
 *  `interactive` adds hover lift + press settle for clickable cards. `selected` locks it
 *  in with a coral ring (the "selection by ring, not dimming" rule). */
export function Card({
  className,
  children,
  interactive = false,
  selected = false,
}: {
  className?: string;
  children: React.ReactNode;
  interactive?: boolean;
  selected?: boolean;
}) {
  return (
    <div
      className={cn(
        "rounded-lg border bg-surface",
        selected ? "border-accent-line ring-1 ring-accent-line" : "border-line",
        interactive &&
          "transition duration-200 ease-snappy hover:-translate-y-0.5 hover:border-line-strong hover:bg-surface-2 active:translate-y-0",
        className,
      )}
    >
      {children}
    </div>
  );
}
