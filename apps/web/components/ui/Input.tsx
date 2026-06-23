import { cn } from "@/lib/cn";

// Resting/focus border stays on the neutral ladder (line → line-strong); the coral
// signal is the GLOBAL :focus-visible ring only, so the scarce accent isn't spent on
// every keystroke. `error` wires aria-invalid + a bad-tinted hairline.
type InputProps = React.InputHTMLAttributes<HTMLInputElement> & { error?: boolean };

export function Input({ className, error, disabled, ...props }: InputProps) {
  return (
    <input
      aria-invalid={error || undefined}
      disabled={disabled}
      className={cn(
        "h-11 w-full rounded-md border bg-surface-2 px-3.5 text-[0.95rem] text-ink",
        "placeholder:text-faint transition-colors duration-200 ease-snappy",
        error
          ? "border-bad/60 hover:border-bad"
          : "border-line hover:border-line-strong focus:border-line-strong",
        disabled && "cursor-not-allowed opacity-50",
        className,
      )}
      {...props}
    />
  );
}

export function Label({ className, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    <label
      className={cn("mb-1.5 block text-sm font-medium text-muted", className)}
      {...props}
    />
  );
}
