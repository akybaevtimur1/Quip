import { Check } from "lucide-react";
import { CheckoutCta } from "@/components/ui/CheckoutCta";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { Numeral } from "@/components/ui/Numeral";
import { Reveal } from "@/components/ui/Reveal";
import { cn } from "@/lib/cn";
import { PAYG, PLANS } from "@/lib/plans";
import { checkoutHref, paygCheckoutHref } from "@/lib/polar";

// ────────────────────────────────────────────────────────────────────────────
// PricingCards — three plan panels (shared by landing section + /pricing) + a
// pay-as-you-go strip. Warm Precision: hairline panels on near-black, every
// price/limit in mono tabular numerals (the data signature), and the coral accent
// reserved for the ONE recommended plan (badge + ring + lit surface). Panels lift
// tactilely on hover (transform only); radius-lg discipline throughout.
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
                  "group relative flex flex-col rounded-lg border p-7",
                  "transition duration-200 ease-snappy hover:-translate-y-1",
                  recommended
                    ? "border-accent-line bg-surface-2 ring-1 ring-accent-line"
                    : "border-line bg-surface hover:border-line-strong",
                )}
              >
                {recommended && (
                  // Near-black on coral: white-on-coral is only 3.09:1 (fails AA for
                  // small text); dark text on the same coral clears 5.5:1. The coral pill
                  // is itself the scarce signal — no decorative icon needed.
                  <span className="absolute -top-3 left-7 inline-flex items-center rounded-pill bg-accent px-3 py-1 font-mono text-eyebrow font-semibold uppercase text-bg">
                    Recommended
                  </span>
                )}

                <div className="flex items-baseline justify-between gap-2">
                  <h2 className="font-display text-h3 text-ink">{plan.name}</h2>
                  <Eyebrow tone="faint">{recommended ? "Best value" : "Plan"}</Eyebrow>
                </div>
                <p className="mt-1 text-sm text-muted">{plan.tagline}</p>

                <div className="mt-6 flex items-baseline gap-1.5">
                  <Numeral className="text-display-lg font-semibold leading-none tracking-tight text-ink">
                    ${plan.price}
                  </Numeral>
                  <Eyebrow tone="faint">/ month</Eyebrow>
                </div>

                {/* Headline limit — the thing a buyer actually compares, as a readout. */}
                <div className="mt-5 border-y border-line py-4">
                  <Eyebrow tone="faint">Monthly limit</Eyebrow>
                  <p className="mt-1.5 font-mono text-base font-semibold tabular-nums text-ink">
                    {plan.limit}
                  </p>
                  <p className="mt-1 text-xs leading-snug text-muted">{plan.limitNote}</p>
                </div>

                {/* Recommended CTA = near-white primary (highest contrast + the site's
                    established primary-CTA style). Coral emphasis lives in the ring +
                    badge, keeping the accent scarce and AA-clean. */}
                <CheckoutCta
                  href={checkoutHref(plan.id)}
                  variant={recommended ? "primary" : "secondary"}
                  size="md"
                  className="mt-6 w-full"
                >
                  {plan.cta}
                </CheckoutCta>

                <ul className="mt-7 space-y-3 border-t border-line pt-7">
                  {plan.features.map((f) => (
                    <li key={f} className="flex items-start gap-2.5 text-sm text-muted">
                      <Check className="mt-0.5 size-4 shrink-0 text-faint" aria-hidden />
                      <span>{f}</span>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      </Reveal>

      {/* Pay-as-you-go — no subscription, credits never expire. A slim inline action. */}
      <Reveal>
        <div className="mx-auto mt-5 flex max-w-5xl flex-col items-start gap-5 rounded-lg border border-line bg-surface p-7 transition duration-200 ease-snappy hover:border-line-strong sm:flex-row sm:items-center sm:justify-between">
          <div>
            <Eyebrow tone="faint">Pay as you go</Eyebrow>
            <p className="mt-2 font-display text-h3 text-ink">{PAYG.title}</p>
            <p className="mt-1 max-w-md text-sm leading-relaxed text-muted">{PAYG.body}</p>
          </div>
          <div className="flex shrink-0 items-center gap-5 sm:flex-col sm:items-end sm:gap-2">
            <div className="flex items-baseline gap-1.5">
              <Numeral className="text-h2 font-semibold tracking-tight text-ink">
                ${PAYG.pricePerVideo}
              </Numeral>
              <Eyebrow tone="faint">/ video</Eyebrow>
            </div>
            <CheckoutCta href={paygCheckoutHref()} variant="secondary" size="md">
              {PAYG.cta}
            </CheckoutCta>
          </div>
        </div>
      </Reveal>

      <Eyebrow as="p" tone="faint" className="mt-8 text-center">
        Prices in USD · cancel anytime · monthly credits reset · pay-as-you-go never expires
      </Eyebrow>
    </>
  );
}
