import { cn } from "@/lib/cn";

// Square, tactile icon-only button. Replaces bare hover-color-only text actions
// (scissors / undo / delete) so every clickable glyph has a real hit target,
// surface hover, and press feedback. aria-label is REQUIRED (icon-only a11y).
export type IconButtonTone = "default" | "accent" | "danger";
export type IconButtonSize = "sm" | "md";

const toneClass: Record<IconButtonTone, string> = {
  default: "text-muted hover:text-ink hover:bg-surface-3",
  accent: "text-muted hover:text-accent hover:bg-surface-3",
  danger: "text-muted hover:text-bad hover:bg-bad/10",
};

const sizeClass: Record<IconButtonSize, string> = {
  sm: "size-7",
  md: "size-9",
};

type IconButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  "aria-label": string;
  tone?: IconButtonTone;
  size?: IconButtonSize;
};

export function IconButton({
  tone = "default",
  size = "md",
  className,
  children,
  ...props
}: IconButtonProps) {
  return (
    <button
      type="button"
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-sm",
        "transition duration-150 ease-snappy active:scale-95",
        "disabled:pointer-events-none disabled:opacity-40",
        toneClass[tone],
        sizeClass[size],
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}
