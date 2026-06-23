"use client";

import { Check } from "lucide-react";
import { useId } from "react";
import { cn } from "@/lib/cn";

// Accessible, token-only checkbox. A real <input type="checkbox"> drives state
// (keyboard + form semantics intact); it's visually hidden (`peer sr-only`) and a
// styled box renders the coral check. Global :focus-visible supplies the ring.
type CheckboxProps = Omit<React.InputHTMLAttributes<HTMLInputElement>, "type" | "size"> & {
  /** Optional inline label rendered to the right of the box. */
  label?: React.ReactNode;
  /** Wrapper className (the <label>); use to space it in a row. */
  className?: string;
};

export function Checkbox({ label, className, id, disabled, ...props }: CheckboxProps) {
  const autoId = useId();
  const inputId = id ?? autoId;
  return (
    <label
      htmlFor={inputId}
      className={cn(
        "group inline-flex items-center gap-2 text-sm text-muted select-none",
        disabled ? "cursor-not-allowed opacity-50" : "cursor-pointer",
        className,
      )}
    >
      <input id={inputId} type="checkbox" disabled={disabled} className="peer sr-only" {...props} />
      <span
        aria-hidden
        className={cn(
          // checked = ink fill (engaged), not coral — keeps the scarce accent scarce.
          "grid size-[18px] shrink-0 place-items-center rounded-sm border border-line-strong bg-surface-2",
          "transition duration-200 ease-snappy [&>svg]:opacity-0 peer-checked:[&>svg]:opacity-100",
          "peer-checked:border-ink peer-checked:bg-ink",
          "peer-focus-visible:shadow-[0_0_0_2px_var(--color-bg),0_0_0_4px_var(--color-accent-line)]",
          !disabled && "group-hover:border-line-strong peer-checked:group-hover:bg-ink/90",
        )}
      >
        <Check
          className="size-3 text-bg transition-opacity duration-150"
          strokeWidth={3.5}
          aria-hidden
        />
      </span>
      {label != null && <span className="leading-snug">{label}</span>}
    </label>
  );
}
