import { getLocale } from "next-intl/server";
import { resolveLocale } from "@/i18n/locale";
import { getLandingContent } from "@/lib/landingContent";
import { Container, Eyebrow, Section } from "../components/primitives";
import { InlineClip } from "../components/InlineClip";
import { Reveal } from "../components/Reveal";

export async function Demo() {
  const demo = getLandingContent(resolveLocale(await getLocale())).demo;
  return (
    <Section id="demo" className="overflow-hidden">
      {/* the page's one permitted coral atmosphere wash, anchored at the top, decaying fast */}
      <div
        className="pointer-events-none absolute inset-x-0 top-0 h-[420px] opacity-70"
        style={{
          background:
            "radial-gradient(60% 100% at 50% 0%, rgba(255,90,61,0.12), rgba(255,90,61,0.04) 38%, transparent 70%)",
        }}
        aria-hidden
      />
      <Container className="relative">
        <Reveal className="max-w-[44rem]">
          <Eyebrow>{demo.eyebrow}</Eyebrow>
          <h2 className="mt-5 text-[clamp(30px,4vw,48px)] font-bold leading-[1.06] tracking-[-0.025em] text-ink">
            {demo.heading}
          </h2>
          <p className="mt-5 max-w-[58ch] text-[1.0625rem] leading-relaxed text-muted">{demo.sub}</p>
        </Reveal>

        {/* pipeline stage strip - hue-free, the moving video carries the proof */}
        <Reveal delay={0.05} className="mt-10">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2 font-mono text-[11px] uppercase tracking-[0.12em]">
            {demo.stages.map((s, i) => (
              <span key={s} className="flex items-center gap-3">
                <span className={i === 0 ? "text-ink" : "text-faint"}>
                  <span className="text-muted">{String(i + 1).padStart(2, "0")}</span> {s}
                </span>
                {i < demo.stages.length - 1 && <span className="text-faint" aria-hidden>{"→"}</span>}
              </span>
            ))}
          </div>
        </Reveal>

        {/* the real run */}
        <Reveal delay={0.1} className="mt-6">
          <div className="overflow-hidden rounded-[18px] border border-line-strong bg-surface p-2 shadow-[inset_0_1px_0_rgba(242,239,233,0.06)] sm:p-3">
            <div className="relative aspect-[1600/822] w-full overflow-hidden rounded-[12px] border border-line bg-bg">
              <InlineClip
                src="/media/demo.mp4"
                poster="/media/demo-poster.jpg"
                label="A real Quip run: upload, find the moments, cut vertical clips"
                className="size-full object-cover"
              />
            </div>
          </div>
        </Reveal>
      </Container>
    </Section>
  );
}
