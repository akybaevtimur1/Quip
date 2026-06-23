import { cn } from "@/lib/cn";

// Calibrated empty state: optional glyph + title + line + one action. Left-aligned by
// default (for in-rail empties); pass align="center" for full-canvas voids. Gives every
// "nothing here yet" moment one voice instead of a dead muted sentence.
export function EmptyState({
  icon,
  title,
  description,
  action,
  align = "left",
  className,
}: {
  icon?: React.ReactNode;
  title?: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
  align?: "left" | "center";
  className?: string;
}) {
  return (
    <div
      className={cn("flex flex-col gap-2", align === "center" && "items-center text-center", className)}
    >
      {icon != null && <div className="text-muted">{icon}</div>}
      {title != null && <p className="text-sm font-semibold text-ink">{title}</p>}
      {description != null && (
        <p className="max-w-sm text-sm leading-relaxed text-muted">{description}</p>
      )}
      {action != null && <div className="mt-1">{action}</div>}
    </div>
  );
}
