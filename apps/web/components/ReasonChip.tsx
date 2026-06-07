import type { ClipType } from "@/lib/types";

// Цвет чипа кодирует тип момента (функциональные цвета). Классы — литералы,
// чтобы Tailwind их увидел при сборке.
const MAP: Record<ClipType, { label: string; cls: string }> = {
  hook: { label: "Hook", cls: "text-hook bg-hook/15 border-hook/40" },
  emotional_peak: { label: "Peak", cls: "text-peak bg-peak/15 border-peak/40" },
  complete_thought: { label: "Thought", cls: "text-thought bg-thought/15 border-thought/40" },
  strong_quote: { label: "Quote", cls: "text-quote bg-quote/15 border-quote/40" },
};

export function ReasonChip({ type }: { type: ClipType }) {
  const c = MAP[type];
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${c.cls}`}
    >
      {c.label}
    </span>
  );
}
