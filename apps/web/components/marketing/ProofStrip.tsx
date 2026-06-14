import { Container } from "@/components/ui/Container";
import { Reveal } from "@/components/ui/Reveal";

// Cost anchoring: what repurposing costs the usual way vs. starting on Quip.
// Ranges are grounded in 2025-26 market rates (freelance short clips ~$100-500;
// short-form editor retainers ~$500-3000/mo). Competitor numbers are dimmed (the
// "expensive" path); Quip's is the coral accent.
const ITEMS: { metric: string; note: string; accent?: boolean }[] = [
  { metric: "$500–3,000", note: "editor retainer / mo" },
  { metric: "$50–500", note: "per freelance clip" },
  { metric: "$0", note: "to start on Quip", accent: true },
];

export function ProofStrip() {
  return (
    <section className="border-y border-line bg-surface">
      <Container className="py-11">
        <Reveal>
          <dl className="grid grid-cols-1 gap-0 text-center sm:grid-cols-3 sm:gap-6">
            {ITEMS.map((it) => (
              <div
                key={it.note}
                className="flex items-center justify-center gap-4 border-b border-line py-5 last:border-b-0 sm:flex-col sm:gap-2 sm:border-b-0 sm:py-3"
              >
                <dd
                  className={`font-display text-3xl font-bold leading-none tracking-tight tabular-nums sm:text-display-lg ${
                    it.accent ? "text-accent" : "text-faint"
                  }`}
                >
                  {it.metric}
                </dd>
                <dt className="text-sm font-medium text-faint sm:text-[13px]">{it.note}</dt>
              </div>
            ))}
          </dl>
        </Reveal>
      </Container>
    </section>
  );
}
