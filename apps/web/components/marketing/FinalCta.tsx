import Link from "next/link";
import { buttonVariants } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";
import { Reveal } from "@/components/ui/Reveal";
import { Section } from "@/components/ui/Section";
import { getOptionalUser } from "@/lib/supabase/server";

export async function FinalCta() {
  const authed = Boolean(await getOptionalUser());
  return (
    <Section className="relative overflow-hidden">
      <div
        aria-hidden
        className="pointer-events-none absolute left-1/2 top-1/2 size-[680px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-[radial-gradient(circle,rgba(255,90,61,.10),transparent_60%)]"
      />
      <Container className="relative">
        <Reveal className="mx-auto max-w-2xl text-center">
          <h2 className="font-display text-h2 text-ink sm:text-display-lg">
            Stop guessing which clips to post.
          </h2>
          <p className="mx-auto mt-5 max-w-md text-lead text-muted">
            Drop in a video and get a handful of clips you can actually stand behind — each with the
            reason it works.
          </p>
          <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
            <Link
              href={authed ? "/dashboard" : "/signup"}
              className={buttonVariants({ variant: "primary", size: "lg" })}
            >
              {authed ? "Open the app" : "Try Quip free"}
              <span aria-hidden>→</span>
            </Link>
            <Link href="#pricing" className={buttonVariants({ variant: "secondary", size: "lg" })}>
              See pricing
            </Link>
          </div>
          {!authed && (
            <p className="mt-7 text-sm text-faint">
              <span className="font-medium text-muted">No credit card.</span> 2 free videos every
              month.
            </p>
          )}
        </Reveal>
      </Container>
    </Section>
  );
}
