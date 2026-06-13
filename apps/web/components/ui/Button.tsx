import { Loader2 } from "lucide-react";
import { cn } from "@/lib/cn";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "accent";
export type ButtonSize = "sm" | "md" | "lg";

const base =
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md font-semibold " +
  "select-none transition duration-200 ease-snappy focus-visible:outline-none " +
  "disabled:pointer-events-none disabled:opacity-50 active:translate-y-0";

const variantClass: Record<ButtonVariant, string> = {
  // primary CTA: near-white on dark (matches quip.ink, AA-safe). Coral stays a
  // scarce accent (mark, highlight, hook plate), never load-bearing button text.
  primary:
    "bg-ink text-bg shadow-[0_1px_0_rgba(255,255,255,.35)_inset,0_12px_34px_-16px_rgba(0,0,0,.7)] " +
    "hover:bg-white hover:-translate-y-px",
  secondary:
    "bg-surface-2 text-ink border border-line hover:border-line-strong hover:bg-surface-3 hover:-translate-y-px",
  ghost: "text-muted hover:text-ink hover:bg-surface-2",
  // coral CTA for in-product moments (run, apply, retry). White-on-coral passes AA;
  // use sparingly per DESIGN.md (one or two per view). Lifts on hover, settles on press.
  accent:
    "bg-accent text-white shadow-[0_1px_0_rgba(255,255,255,.18)_inset,0_12px_34px_-18px_rgba(255,90,61,.6)] " +
    "hover:bg-accent-2 hover:-translate-y-px",
};

const sizeClass: Record<ButtonSize, string> = {
  sm: "h-9 px-3.5 text-sm",
  md: "h-11 px-5 text-[0.95rem]",
  lg: "h-[3.25rem] px-6 text-base",
};

/** Shared styling for buttons and link-buttons (apply to <button> or <Link>). */
export function buttonVariants(opts: { variant?: ButtonVariant; size?: ButtonSize } = {}): string {
  const { variant = "primary", size = "md" } = opts;
  return cn(base, variantClass[variant], sizeClass[size]);
}

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
};

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  className,
  children,
  disabled,
  ...props
}: ButtonProps) {
  return (
    <button
      className={cn(buttonVariants({ variant, size }), className)}
      disabled={disabled ?? loading}
      aria-busy={loading || undefined}
      {...props}
    >
      {loading && <Loader2 className="size-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
}
