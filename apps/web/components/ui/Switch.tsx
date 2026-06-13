"use client";

import { useId } from "react";
import { cn } from "@/lib/cn";

// Accessible token-only toggle. A visually-hidden checkbox owns state and keyboard
// (space toggles, tab focuses); the coral track + sliding knob are presentation.
// Use for binary on/off where the *effect is immediate* (vs. Checkbox for form-y
// opt-ins). Global :focus-visible draws the ring on the input via peer-focus-visible.
type SwitchProps = Omit<React.InputHTMLAttributes<HTMLInputElement>, "type" | "size"> & {
  label?: React.ReactNode;
  className?: string;
};

export function Switch({ label, className, id, disabled, ...props }: SwitchProps) {
  const autoId = useId();
  const inputId = id ?? autoId;
  return (
    <label
      htmlFor={inputId}
      className={cn(
        "group inline-flex items-center gap-2.5 text-sm text-muted select-none",
        disabled ? "cursor-not-allowed opacity-50" : "cursor-pointer",
        className,
      )}
    >
      <input id={inputId} type="checkbox" role="switch" disabled={disabled} className="peer sr-only" {...props} />
      <span
        aria-hidden
        className={cn(
          "relative h-[22px] w-[38px] shrink-0 rounded-pill border border-line-strong bg-surface-3",
          "transition-colors duration-200 ease-snappy",
          "peer-checked:border-accent peer-checked:bg-accent",
          "peer-focus-visible:shadow-[0_0_0_2px_var(--color-bg),0_0_0_4px_var(--color-accent-line)]",
          "after:absolute after:left-[2px] after:top-1/2 after:size-4 after:-translate-y-1/2 after:rounded-pill after:bg-ink",
          "after:transition-transform after:duration-200 after:ease-snappy after:content-['']",
          "peer-checked:after:translate-x-4 peer-checked:after:bg-bg",
        )}
      />
      {label != null && <span className="leading-snug">{label}</span>}
    </label>
  );
}
