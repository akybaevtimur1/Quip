import { Check } from "lucide-react";
import Link from "next/link";
import { buttonVariants } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";
import { Reveal } from "@/components/ui/Reveal";
import { Section } from "@/components/ui/Section";
import { cn } from "@/lib/cn";
import { PLANS } from "@/lib/plans";
import { SectionHeading } from "./SectionHeading";

export function Pricing() {
  return (
    <Section id="pricing">
      <Container>
        <Reveal>
          <SectionHeading
            align="center"
            eyebrow="Pricing"
            title="Simple plans. No credit casino."
            lead="Pay for source minutes, the thing that actually costs money. No tokens to ration, no surprise paywalls — you always know your limit up front."
          />
        </Reveal>

        <Reveal>
          <div className="mx-auto mt-14 grid max-w-5xl items-start gap-5 lg:grid-cols-3">
            {PLANS.map((plan) => (
              <div
                key={plan.id}
                className={cn(
                  "relative flex flex-col rounded-xl border bg-surface p-7",
                  plan.highlighted ? "border-accent/50 ring-1 ring-accent/30" : "border-line",
                )}
              >
                {plan.highlighted && (
                  <span className="absolute -top-3 left-7 rounded-pill bg-accent px-3 py-1 font-mono text-eyebrow uppercase text-white">
                    Most popular
                  </span>
                )}
                <h3 className="font-display text-h3 text-ink">{plan.name}</h3>
                <p className="mt-1 text-sm text-muted">{plan.tagline}</p>
                <div className="mt-5 flex items-baseline gap-1">
                  <span className="font-display text-display-lg tabular-nums text-ink">
                    ${plan.price}
                  </span>
                  <span className="text-sm text-faint">/ month</span>
                </div>

                <Link
                  href="/signup"
                  className={cn(
                    "mt-6 w-full",
                    buttonVariants({ variant: plan.highlighted ? "primary" : "secondary", size: "md" }),
                  )}
                >
                  {plan.cta}
                </Link>

                <ul className="mt-7 space-y-3 border-t border-line pt-7">
                  {plan.features.map((f) => (
                    <li key={f} className="flex items-start gap-2.5 text-sm text-muted">
                      <Check className="mt-0.5 size-4 shrink-0 text-accent" aria-hidden />
                      <span>{f}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </Reveal>
        <p className="mt-8 text-center text-sm text-faint">
          Prices in USD. Cancel anytime. Limits reset monthly.
        </p>
      </Container>
    </Section>
  );
}
