import { Check, Sparkles, Zap } from "lucide-react";
import Link from "next/link";
import { buttonVariants } from "@/components/ui/Button";
import { Reveal } from "@/components/ui/Reveal";
import { cn } from "@/lib/cn";
import { PAYG, PLANS } from "@/lib/plans";
import { checkoutHref, paygCheckoutHref } from "@/lib/polar";

// ────────────────────────────────────────────────────────────────────────────
// PricingCards — three plan cards (shared by landing section + /pricing) + a
// pay-as-you-go strip. Precision Dark: hairline cards on near-black, the coral
// accent reserved for the ONE recommended plan (badge, ring, coral CTA). Prices
// use tabular figures; cards lift tactilely on hover (transform only).
// ────────────────────────────────────────────────────────────────────────────

export function PricingCards() {
  return (
    <>
      <Reveal>
        <div className="mx-auto grid max-w-5xl items-stretch gap-5 lg:grid-cols-3">
          {PLANS.map((plan) => {
            const recommended = plan.recommended ?? false;
            return (
              <div
                key={plan.id}
                className={cn(
                  "group relative flex flex-col rounded-xl border bg-surface p-7",
                  "transition duration-200 ease-snappy hover:-translate-y-1",
                  recommended
                    ? "border-accent/60 ring-1 ring-accent/40"
                    : "border-line hover:border-line-strong",
                )}
              >
                {recommended && (
                  <span className="absolute -top-3 left-7 inline-flex items-center gap-1 rounded-pill bg-accent px-3 py-1 font-mono text-eyebrow uppercase text-white shadow-[0_8px_24px_-10px_rgba(255,90,61,.7)]">
                    <Sparkles className="size-3" aria-hidden />
                    Recommended
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

                {/* Headline limit — the thing a buyer actually compares. */}
                <div className="mt-4 rounded-lg border border-line bg-surface-2 px-3.5 py-3">
                  <p className="font-semibold tabular-nums text-ink">{plan.limit}</p>
                  <p className="mt-0.5 text-xs leading-snug text-muted">{plan.limitNote}</p>
                </div>

                <Link
                  href={checkoutHref(plan.id)}
                  className={cn(
                    "mt-6 w-full",
                    buttonVariants({
                      variant: recommended ? "accent" : "secondary",
                      size: "md",
                    }),
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
            );
          })}
        </div>
      </Reveal>

      {/* Pay-as-you-go — no subscription, credits never expire. */}
      <Reveal>
        <div className="mx-auto mt-5 flex max-w-5xl flex-col items-start gap-5 rounded-xl border border-line bg-surface p-7 transition duration-200 ease-snappy hover:border-line-strong sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3.5">
            <span className="mt-0.5 grid size-10 shrink-0 place-items-center rounded-lg border border-line bg-surface-2 text-accent">
              <Zap className="size-5" aria-hidden />
            </span>
            <div>
              <p className="font-display text-h3 text-ink">{PAYG.title}</p>
              <p className="mt-1 max-w-md text-sm leading-relaxed text-muted">{PAYG.body}</p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-5 sm:flex-col sm:items-end sm:gap-2">
            <div className="flex items-baseline gap-1">
              <span className="font-display text-h2 tabular-nums text-ink">
                ${PAYG.pricePerVideo}
              </span>
              <span className="text-sm text-faint">/ video</span>
            </div>
            <Link href={paygCheckoutHref()} className={buttonVariants({ variant: "secondary", size: "md" })}>
              {PAYG.cta}
            </Link>
          </div>
        </div>
      </Reveal>

      <p className="mt-8 text-center text-sm text-faint">
        Prices in USD. Cancel anytime. Monthly credits reset each month; pay-as-you-go credits
        never expire.
      </p>
    </>
  );
}
