import { cn } from "@/lib/cn";

/** Marketing section with consistent vertical rhythm. */
export function Section({
  id,
  className,
  children,
  as: Tag = "section",
}: {
  id?: string;
  className?: string;
  children: React.ReactNode;
  as?: "section" | "div";
}) {
  return (
    <Tag id={id} className={cn("py-20 sm:py-28", className)}>
      {children}
    </Tag>
  );
}
