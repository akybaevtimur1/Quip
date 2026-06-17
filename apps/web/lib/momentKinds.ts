// Shared kind→color map for VideoMap.tsx and TopicStrip.tsx.
// Tokens reference CSS vars defined in globals.css.
export const KIND_COLOR: Record<
  string,
  { dot: string; chip: string; label: string }
> = {
  tension: {
    dot: "bg-accent",
    chip: "bg-accent-tint border-accent-line",
    label: "Tension",
  },
  emotional: {
    dot: "bg-peak",
    chip: "bg-[rgba(192,107,255,0.12)] border-[rgba(192,107,255,0.3)]",
    label: "Emotional",
  },
  quote: {
    dot: "bg-quote",
    chip: "bg-[rgba(77,141,255,0.12)] border-[rgba(77,141,255,0.3)]",
    label: "Quote",
  },
  insight: {
    dot: "bg-thought",
    chip: "bg-[rgba(25,189,139,0.12)] border-[rgba(25,189,139,0.3)]",
    label: "Insight",
  },
  funny: {
    dot: "bg-warn",
    chip: "bg-[rgba(245,179,46,0.12)] border-[rgba(245,179,46,0.3)]",
    label: "Funny",
  },
};

export const KIND_KEYS = Object.keys(KIND_COLOR) as Array<keyof typeof KIND_COLOR>;

/** Returns the color entry for a moment kind, falling back to "insight". */
export function kindColor(kind: string) {
  return KIND_COLOR[kind] ?? KIND_COLOR["insight"];
}
