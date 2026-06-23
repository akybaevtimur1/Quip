import { cn } from "@/lib/cn";
import { Eyebrow } from "@/components/ui/Eyebrow";

// `eyebrow` adds a mono instrument-label kicker (e.g. "02 / WHY IT WORKS") so sections get
// authored landmarks and cadence instead of all opening on the same flat h2-then-lead beat.
export function SectionHeading({
  eyebrow,
  title,
  lead,
  align = "left",
  className,
}: {
  eyebrow?: React.ReactNode;
  title: React.ReactNode;
  lead?: React.ReactNode;
  align?: "left" | "center";
  className?: string;
}) {
  return (
    <div className={cn(align === "center" ? "mx-auto max-w-2xl text-center" : "max-w-2xl", className)}>
      {eyebrow != null && (
        <Eyebrow tone="faint" className={cn("mb-3 flex items-center gap-2", align === "center" && "justify-center")}>
          {eyebrow}
        </Eyebrow>
      )}
      <h2 className="font-display text-h2 text-ink sm:text-display-lg">{title}</h2>
      {lead && <p className="mt-4 text-lead text-muted">{lead}</p>}
    </div>
  );
}
