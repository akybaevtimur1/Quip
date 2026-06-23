import { cn } from "@/lib/cn";

// Max-width content column with responsive gutters. `default` keeps the 1200px app width
// (back-compat); `wide` gives a roomier 1400px for instrument workspaces; `prose` caps a
// reading measure so body copy is never set at 1200px.
export type ContainerSize = "default" | "wide" | "prose";

const sizeClass: Record<ContainerSize, string> = {
  default: "max-w-[1200px]",
  wide: "max-w-[1400px]",
  prose: "max-w-[68ch]",
};

export function Container({
  className,
  children,
  size = "default",
}: {
  className?: string;
  children: React.ReactNode;
  size?: ContainerSize;
}) {
  return (
    <div className={cn("mx-auto w-full px-5 sm:px-8", sizeClass[size], className)}>{children}</div>
  );
}
