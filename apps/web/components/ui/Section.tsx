import { cn } from "@/lib/cn";

// Marketing section with intentional vertical rhythm. Three deliberate densities give the
// page cadence contrast instead of one metronomic beat (a subtle template tell).
export type SectionSpace = "tight" | "default" | "loose";

const spaceClass: Record<SectionSpace, string> = {
  tight: "py-14 sm:py-20",
  default: "py-20 sm:py-28",
  loose: "py-28 sm:py-36",
};

export function Section({
  id,
  className,
  children,
  as: Tag = "section",
  space = "default",
}: {
  id?: string;
  className?: string;
  children: React.ReactNode;
  as?: "section" | "div";
  space?: SectionSpace;
}) {
  return (
    <Tag id={id} className={cn(spaceClass[space], className)}>
      {children}
    </Tag>
  );
}
