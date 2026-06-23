import Link from "next/link";
import { ClipMockup } from "@/components/marketing/ClipMockup";
import { ReasoningCard } from "@/components/marketing/ReasoningCard";
import { buttonVariants } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { Numeral } from "@/components/ui/Numeral";
import { Reveal } from "@/components/ui/Reveal";
import { Stat } from "@/components/ui/Stat";
import { getOptionalUser } from "@/lib/supabase/server";

export async function Hero() {
  const authed = Boolean(await getOptionalUser());
  return (
    <section className="relative overflow-hidden">
      {/* one restrained coral bloom — the single ambient signal on the page */}
      <div
        aria-hidden
        className="pointer-events-none absolute -left-40 -top-40 size-[640px] rounded-full bg-[radial-gradient(circle,rgba(255,90,61,.10),transparent_62%)]"
      />

      <Container className="relative grid items-center gap-14 py-16 sm:py-24 lg:grid-cols-[1.02fr_.98fr] lg:gap-14 lg:py-28">
        {/* left: message */}
        <div className="max-w-xl">
          <Reveal>
            <Eyebrow tone="faint" className="flex items-center gap-2">
              <span className="h-px w-6 bg-line-strong" aria-hidden />
              Explainable clip instrument
            </Eyebrow>
          </Reveal>
          <Reveal delay={80}>
            <h1 className="mt-5 font-display text-display-lg text-ink sm:text-display-xl lg:text-display-2xl">
              Don&rsquo;t just get clips. <span className="text-accent">Know why</span>{" "}
              they&rsquo;re worth posting.
            </h1>
          </Reveal>
          <Reveal delay={120}>
            <p className="mt-6 max-w-md text-lead text-muted">
              Drop a podcast, interview, or stream. Quip finds the moments, cuts clean vertical
              clips, and reports the reason each one will land — a hook, a confidence score, and the
              cut explained.
            </p>
          </Reveal>
          <Reveal delay={180}>
            <div className="mt-9 flex flex-wrap items-center gap-3">
              <Link
                href={authed ? "/dashboard" : "/signup"}
                className={buttonVariants({ variant: "primary", size: "lg" })}
              >
                {authed ? "Open the app" : "Paste a video link"}
                <span aria-hidden>→</span>
              </Link>
              <Link
                href="#how-it-works"
                className={buttonVariants({ variant: "secondary", size: "lg" })}
              >
                See how it works
              </Link>
            </div>
          </Reveal>
          {!authed && (
            <Reveal delay={240}>
              <Eyebrow as="p" tone="faint" className="mt-7">
                No card · <Numeral>2</Numeral> free videos / month
              </Eyebrow>
            </Reveal>
          )}
        </div>

        {/* right: the analysis readout — clip + score + reason as one unit.
            The clip sits right; the hero score (top-left) and the reason (bottom-left)
            frame it diagonally so the FIRST thing read is the instrument's verdict. */}
        <Reveal delay={140} className="relative mx-auto w-full max-w-[420px] lg:mx-0 lg:ml-auto">
          <div className="relative">
            <ClipMockup
              image="/clips/hero-clip.webp"
              priority
              className="ml-auto w-[68%] sm:w-[62%] lg:w-[66%]"
            />

            {/* the verdict — hero-scale score, the first reading you see */}
            <div className="absolute -left-2 top-4 w-[46%] rounded-lg border border-line bg-surface/90 p-4 backdrop-blur-md shadow-[0_28px_64px_-26px_rgba(0,0,0,.85)] sm:-left-3 sm:top-6 lg:-left-8">
              <Stat
                label="Confidence"
                value={94}
                suffix="/100"
                size="lg"
                tone="ok"
                meter={0.94}
                meterTone="ok"
              />
            </div>

            <ReasoningCard
              floating
              className="absolute -bottom-6 left-0 w-[82%] sm:left-[6%] sm:w-[76%] lg:-left-4 lg:w-[80%]"
              type="strong_quote"
              confidence={94}
              why="A vulnerable admission in the first 2 seconds opens a loop the viewer needs closed."
            />
          </div>
        </Reveal>
      </Container>
    </section>
  );
}
