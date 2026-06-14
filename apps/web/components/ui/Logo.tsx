import Image from "next/image";
import Link from "next/link";
import { cn } from "@/lib/cn";

/** Quip wordmark: the brand Q mark (charcoal ring + coral play) + Onest-extrabold
 *  wordmark. Same mark as the favicon and the hook plate burned into every clip. */
export function Logo({
  className,
  href = "/",
  size = "md",
}: {
  className?: string;
  href?: string | null;
  size?: "sm" | "md";
}) {
  const px = size === "sm" ? 24 : 30;
  const inner = (
    <span className="inline-flex items-center gap-2">
      <Image
        src="/icon.png"
        alt=""
        width={px}
        height={px}
        className={cn("shrink-0", size === "sm" ? "size-6" : "size-[30px]")}
        aria-hidden
      />
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
