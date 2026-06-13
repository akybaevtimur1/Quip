import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/cn";

// Token-skinned native <select>. We keep the native element (full keyboard +
// platform a11y + mobile pickers) and only style the trigger: remove the OS arrow,
// draw our own coral-on-hover chevron, match Input's surface/hairline/radius.
// Global :focus-visible supplies the ring.
type SelectProps = React.SelectHTMLAttributes<HTMLSelectElement>;

export function Select({ className, children, disabled, ...props }: SelectProps) {
  return (
    <span className="relative inline-flex w-full items-center">
      <select
        disabled={disabled}
        className={cn(
          "h-10 w-full appearance-none rounded-sm border border-line bg-surface-2 pl-3 pr-9 text-sm text-ink",
          "transition-colors duration-200 ease-snappy outline-none",
          "hover:border-line-strong focus:border-accent/60",
          "disabled:cursor-not-allowed disabled:opacity-50",
          // native option list inherits OS colors; keep text readable there too
          "[&>option]:bg-surface [&>option]:text-ink",
          className,
        )}
        {...props}
      >
        {children}
      </select>
      <ChevronDown
        className={cn(
          "pointer-events-none absolute right-3 size-4 text-muted transition-colors",
          !disabled && "peer-focus:text-ink",
        )}
        aria-hidden
      />
    </span>
  );
}
