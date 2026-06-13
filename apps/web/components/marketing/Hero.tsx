import Link from "next/link";
import { ClipMockup } from "@/components/marketing/ClipMockup";
import { ReasoningCard } from "@/components/marketing/ReasoningCard";
import { buttonVariants } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { Reveal } from "@/components/ui/Reveal";

export function Hero() {
  return (
    <section className="relative overflow-hidden">
      {/* restrained atmosphere: warm near-black + coral/amber blooms (Warm Precision, concept C) */}
      <div
        aria-hidden
        className="pointer-events-none absolute -left-40 -top-40 size-[640px] rounded-full bg-[radial-gradient(circle,rgba(255,110,70,.11),transparent_62%)]"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute right-[-12%] top-[8%] size-[560px] rounded-full bg-[radial-gradient(circle,rgba(255,150,90,.06),transparent_64%)]"
      />

      <Container className="relative grid items-center gap-14 py-16 sm:py-24 lg:grid-cols-[1.06fr_.94fr] lg:gap-12 lg:py-28">
        {/* left: message */}
        <div className="max-w-xl">
          <Reveal>
            <Eyebrow>Explainable AI clips</Eyebrow>
          </Reveal>
          <Reveal delay={60}>
            <h1 className="mt-6 font-display text-display-lg text-ink sm:text-display-xl lg:text-display-2xl">
              Don&rsquo;t just get clips. <span className="text-accent">Know why</span> they&rsquo;re
              worth posting.
            </h1>
          </Reveal>
          <Reveal delay={120}>
            <p className="mt-6 max-w-md text-lead text-muted">
              Drop a podcast, interview, or stream. Quip finds the moments, cuts clean vertical
              clips, and tells you the reason each one will land — a hook, a confidence score, and
              the cut explained.
            </p>
          </Reveal>
          <Reveal delay={180}>
            <div className="mt-9 flex flex-wrap items-center gap-3">
              <Link href="/signup" className={buttonVariants({ variant: "primary", size: "lg" })}>
                Paste a video link
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
          <Reveal delay={240}>
            <p className="mt-7 text-sm text-faint">
              <span className="font-medium text-muted">No credit card.</span> 2 free videos every
              month.
            </p>
          </Reveal>
        </div>

        {/* right: the product + its reasons */}
        <Reveal delay={140} className="relative mx-auto w-full max-w-[360px] lg:mx-0 lg:ml-auto">
          <div className="relative">
            <ClipMockup className="w-[78%] sm:w-[68%] lg:w-[74%]" />
            <ReasoningCard
              className="absolute -bottom-6 left-0 w-[80%] sm:left-[18%] sm:w-[74%] lg:-left-10 lg:w-[82%]"
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
