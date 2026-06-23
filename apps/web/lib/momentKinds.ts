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
    chip: "bg-peak/12 border-peak/30",
    label: "Emotional",
  },
  quote: {
    dot: "bg-quote",
    chip: "bg-quote/12 border-quote/30",
    label: "Quote",
  },
  insight: {
    dot: "bg-thought",
    chip: "bg-thought/12 border-thought/30",
    label: "Insight",
  },
  funny: {
    dot: "bg-warn",
    chip: "bg-warn/12 border-warn/30",
    label: "Funny",
  },
};

export const KIND_KEYS = Object.keys(KIND_COLOR) as Array<keyof typeof KIND_COLOR>;

/** Returns the color entry for a moment kind, falling back to "insight". */
export function kindColor(kind: string) {
  return KIND_COLOR[kind] ?? KIND_COLOR["insight"];
}
