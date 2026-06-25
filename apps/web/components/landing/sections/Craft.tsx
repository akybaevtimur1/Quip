import { CRAFT } from "@/lib/landingContent";
import { Container, Section } from "../components/primitives";
import { Reveal } from "../components/Reveal";

const RATIOS = [
  { label: "9:16", cls: "h-[88px] w-[50px]" },
  { label: "1:1", cls: "h-[68px] w-[68px]" },
  { label: "4:5", cls: "h-[80px] w-[64px]" },
  { label: "16:9", cls: "h-[50px] w-[88px]" },
];

export function Craft() {
  const { heading, features } = CRAFT;
  return (
    <Section id="craft">
      <Container>
        <Reveal className="max-w-[38rem]">
          <h2 className="text-[clamp(28px,3.6vw,44px)] font-bold leading-[1.08] tracking-[-0.025em] text-ink">
            {heading}
          </h2>
        </Reveal>

        <Reveal delay={0.05} className="mt-12">
          <div className="grid overflow-hidden rounded-[18px] border border-line sm:grid-cols-2">
            {features.map((f, i) => (
              <div
                key={f.title}
                className={`flex flex-col p-7 sm:p-8 ${i > 0 ? "border-t border-line" : ""} sm:border-t-0 ${
                  i >= 2 ? "sm:border-t" : ""
                } ${i % 2 === 1 ? "sm:border-l" : ""} border-line`}
              >
                <h3 className="text-[1.25rem] font-semibold tracking-[-0.015em] text-ink">{f.title}</h3>
                <p className="mt-2.5 max-w-[40ch] text-[15px] leading-relaxed text-muted">{f.body}</p>

                {/* visual variation: real captioned clip for captions, ratio diagram for ratios */}
                {f.title === "Captions that pop" && (
                  <div className="mt-auto flex items-end gap-3 pt-6">
                    <div className="relative aspect-[9/16] w-[78px] overflow-hidden rounded-[8px] border border-line bg-bg">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src="/clips/poster-1.jpg"
                        alt="A Quip clip with the active word burned in, highlighted in coral"
                        className="size-full object-cover"
                      />
                    </div>
                    <div className="relative aspect-[9/16] w-[78px] overflow-hidden rounded-[8px] border border-line bg-bg">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src="/clips/poster-2.jpg"
                        alt="A Quip clip showing word-by-word captions"
                        className="size-full object-cover"
                      />
                    </div>
                  </div>
                )}
                {f.title === "Your hook, four ratios" && (
                  <div className="mt-auto flex flex-wrap items-end gap-5 pt-8">
                    {RATIOS.map((r) => (
                      <div key={r.label} className="flex flex-col items-center gap-2.5">
                        <span
                          className={`relative flex items-start justify-center overflow-hidden rounded-[6px] border border-line-strong bg-surface-2 pt-2 shadow-[inset_0_1px_0_rgba(242,239,233,0.05)] ${r.cls}`}
                        >
                          {/* the branded hook plate sits on top */}
                          <span className="h-1 w-1/2 rounded-full bg-muted/50" aria-hidden />
                        </span>
                        <span className="num font-mono text-[11px] tracking-[0.06em] text-muted">{r.label}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </Reveal>
      </Container>
    </Section>
  );
}
