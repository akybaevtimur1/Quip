import { cn } from "@/lib/cn";

/** Surface card with a hairline border. Elevation = surface + border (no shadow).
 *  `interactive` adds hover lift for clickable cards. */
export function Card({
  className,
  children,
  interactive = false,
}: {
  className?: string;
  children: React.ReactNode;
  interactive?: boolean;
}) {
  return (
    <div
      className={cn(
        "rounded-lg border border-line bg-surface",
        interactive &&
          "transition duration-200 ease-snappy hover:-translate-y-0.5 hover:border-line-strong hover:bg-surface-2",
        className,
      )}
    >
      {children}
    </div>
  );
}
