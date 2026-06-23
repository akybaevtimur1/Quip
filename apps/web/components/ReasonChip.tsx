import { Badge, type BadgeTone } from "@/components/ui/Badge";
import type { ClipType } from "@/lib/types";

// Clip-type chip — the color encodes the moment type (hook/peak/thought/quote tokens).
// Rebuilt on the shared Badge so the chip shape/voice is identical everywhere a clip
// type appears (grid card, editor, video map).
const MAP: Record<ClipType, { label: string; tone: BadgeTone }> = {
  hook: { label: "Hook", tone: "hook" },
  emotional_peak: { label: "Peak", tone: "peak" },
  complete_thought: { label: "Thought", tone: "thought" },
  strong_quote: { label: "Quote", tone: "quote" },
};

export function ReasonChip({ type }: { type: ClipType }) {
  const c = MAP[type];
  return <Badge tone={c.tone}>{c.label}</Badge>;
}
