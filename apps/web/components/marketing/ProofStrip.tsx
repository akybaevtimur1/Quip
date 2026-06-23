import { Container } from "@/components/ui/Container";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { Numeral } from "@/components/ui/Numeral";
import { Reveal } from "@/components/ui/Reveal";
import { cn } from "@/lib/cn";

// Cost anchoring: what repurposing costs the usual way vs. starting on Quip.
// Ranges are grounded in 2025-26 market rates (freelance short clips ~$100-500;
// short-form editor retainers ~$500-3000/mo). Competitor numbers are dimmed (the
// "expensive" path); Quip's is the single coral reading.
const ITEMS: { metric: string; note: string; accent?: boolean }[] = [
  { metric: "$500–3,000", note: "editor retainer / mo" },
  { metric: "$50–500", note: "per freelance clip" },
  { metric: "$0", note: "to start on Quip", accent: true },
];

export function ProofStrip() {
  return (
    <section className="border-y border-line bg-surface">
      <Container className="py-10">
        <Reveal>
          <dl className="grid grid-cols-1 divide-y divide-line sm:grid-cols-3 sm:divide-x sm:divide-y-0">
            {ITEMS.map((it) => (
              <div
                key={it.note}
                className="flex items-center justify-between gap-4 py-5 sm:flex-col sm:items-start sm:gap-2 sm:px-6 sm:py-2 sm:first:pl-0 sm:last:pr-0"
              >
                <dd
                  className={cn(
                    "font-mono text-display-lg font-semibold leading-none tabular-nums tracking-tight",
                    it.accent ? "text-accent" : "text-faint",
                  )}
                >
                  <Numeral>{it.metric}</Numeral>
                </dd>
                <Eyebrow as="dt" tone={it.accent ? "muted" : "faint"}>
                  {it.note}
                </Eyebrow>
              </div>
            ))}
          </dl>
        </Reveal>
      </Container>
    </section>
  );
}
