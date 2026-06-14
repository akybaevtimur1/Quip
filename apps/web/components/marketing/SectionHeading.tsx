import { cn } from "@/lib/cn";

export function SectionHeading({
  title,
  lead,
  align = "left",
  className,
}: {
  title: React.ReactNode;
  lead?: React.ReactNode;
  align?: "left" | "center";
  className?: string;
}) {
  return (
    <div className={cn(align === "center" ? "mx-auto max-w-2xl text-center" : "max-w-2xl", className)}>
      <h2 className="font-display text-h2 text-ink sm:text-display-lg">{title}</h2>
      {lead && <p className="mt-4 text-lead text-muted">{lead}</p>}
    </div>
  );
}
