/** Minimal classNames joiner — filters falsy values, joins with spaces.
 *  Dependency-free (no clsx/tailwind-merge); we author non-conflicting classes. */
export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}
