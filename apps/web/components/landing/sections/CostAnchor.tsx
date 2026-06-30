import { getLocale } from "next-intl/server";
import { resolveLocale } from "@/i18n/locale";
import { getLandingContent } from "@/lib/landingContent";
import { Container } from "../components/primitives";
import { Reveal } from "../components/Reveal";

export async function CostAnchor() {
  const costAnchor = getLandingContent(resolveLocale(await getLocale())).costAnchor;
  return (
    <section aria-label="What clip editing usually costs" className="py-6">
      <Container>
        <Reveal>
          <div className="grid grid-cols-1 divide-y divide-line overflow-hidden rounded-card border border-line bg-surface sm:grid-cols-3 sm:divide-x sm:divide-y-0">
            {costAnchor.cells.map((c) => (
              <div key={c.label} className="flex flex-col gap-1 px-6 py-6">
                <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-faint">{c.label}</span>
                <div className="flex items-baseline gap-2">
                  <span
                    className={`num font-mono text-[30px] font-medium tracking-[-0.02em] ${
                      c.accent ? "text-accent" : "text-ink"
                    }`}
                  >
                    {c.value}
                  </span>
                  <span className="font-mono text-[12px] uppercase tracking-[0.1em] text-muted">{c.unit}</span>
                </div>
              </div>
            ))}
          </div>
        </Reveal>
      </Container>
    </section>
  );
}
