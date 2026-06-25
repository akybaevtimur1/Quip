import { Check, X } from "@phosphor-icons/react/dist/ssr";
import { COMPARISON, CUT_PROOF } from "@/lib/landingContent";
import { Container, Section } from "../components/primitives";
import { ConfidenceGauge } from "../components/Confidence";
import { InlineClip } from "../components/InlineClip";
import { Reveal } from "../components/Reveal";

export function Comparison() {
  const { heading, sub, rows } = COMPARISON;
  return (
    <Section id="compare">
      <Container>
        <Reveal className="max-w-[44rem]">
          <h2 className="text-[clamp(28px,3.6vw,44px)] font-bold leading-[1.08] tracking-[-0.025em] text-ink">
            {heading}
          </h2>
          <p className="mt-4 text-[1.0625rem] text-muted">{sub}</p>
        </Reveal>

        {/* the cut: one kept clip vs the moments that scored too low to ship */}
        <Reveal delay={0.05} className="mt-12">
          <div className="grid items-center gap-10 rounded-[18px] border border-line bg-surface p-5 sm:p-7 lg:grid-cols-[minmax(0,40fr)_minmax(0,60fr)] lg:gap-12">
            <div className="flex items-center gap-5">
              <div className="relative aspect-[9/16] w-[120px] shrink-0 overflow-hidden rounded-[10px] border border-accent-line bg-bg shadow-[0_0_0_1px_var(--color-accent-line),0_18px_50px_-20px_rgba(255,90,61,0.45)]">
                <InlineClip
                  src="/clips/clip-1.mp4"
                  poster="/clips/poster-1.jpg"
                  label="The clip that made the cut"
                  className="size-full object-cover"
                />
              </div>
              <div>
                <span className="inline-flex items-center gap-1.5 rounded-pill border border-accent-line bg-accent-tint px-2.5 py-1 font-mono text-[10.5px] uppercase tracking-[0.1em] text-accent">
                  <Check weight="bold" className="size-3" />
                  {CUT_PROOF.kept.label}
                </span>
                <ConfidenceGauge value={CUT_PROOF.kept.score} variant="card" className="mt-3" />
                <p className="mt-3 max-w-[24ch] text-[13px] leading-snug text-muted">
                  One video gave 23 candidates. This is the one worth posting first.
                </p>
              </div>
            </div>

            <div>
              <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-faint">Scored too low to ship</span>
              <ul className="mt-4 flex flex-col gap-3.5">
                {CUT_PROOF.rejected.map((r) => (
                  <li key={r.label} className="flex items-center gap-4">
                    <span className="num w-7 shrink-0 text-right font-mono text-[15px] text-bad/90">{r.score}</span>
                    <div className="relative h-1.5 w-20 shrink-0 overflow-hidden rounded-full bg-surface-3">
                      <div
                        className="absolute inset-y-0 left-0 rounded-full bg-bad/55"
                        style={{ width: `${r.score}%` }}
                      />
                    </div>
                    <span className="text-[14px] text-muted">{r.label}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </Reveal>

        {/* head to head: Quip column reads as the winner (lifted + coral), them dimmed */}
        <Reveal delay={0.05} className="mt-10">
          <div className="overflow-hidden rounded-[18px] border border-line">
            {/* header */}
            <div className="grid grid-cols-[1.1fr_1fr_1fr]">
              <div className="px-5 py-4 sm:px-6" />
              <div className="relative border-x border-line bg-surface-2 px-5 py-4 sm:px-6">
                <span className="absolute inset-x-0 top-0 h-[2px] bg-accent" aria-hidden />
                <span className="flex items-center gap-2 font-mono text-[12px] uppercase tracking-[0.12em] text-ink">
                  <Check weight="bold" className="size-3.5 text-accent" />
                  {COMPARISON.cols.quip}
                </span>
              </div>
              <div className="px-5 py-4 font-mono text-[12px] uppercase tracking-[0.12em] text-faint sm:px-6">
                {COMPARISON.cols.them}
              </div>
            </div>
            {/* rows */}
            {rows.map((r) => (
              <div key={r.k} className="grid grid-cols-[1.1fr_1fr_1fr] border-t border-line text-[14px]">
                <div className="px-5 py-4 text-muted sm:px-6">{r.k}</div>
                <div className="flex items-start gap-2.5 border-x border-line bg-surface-2 px-5 py-4 font-medium text-ink sm:px-6">
                  {/* neutral ink check: the lifted surface-2 column + coral header already mark
                      the winner. Per-row coral would over-spend the scarce accent (DESIGN.md). */}
                  <Check weight="bold" className="mt-0.5 size-3.5 shrink-0 text-ink" />
                  <span>{r.quip}</span>
                </div>
                <div className="flex items-start gap-2.5 px-5 py-4 text-faint sm:px-6">
                  <X weight="bold" className="mt-0.5 size-3.5 shrink-0 text-faint" />
                  <span>{r.them}</span>
                </div>
              </div>
            ))}
          </div>
        </Reveal>
      </Container>
    </Section>
  );
}
