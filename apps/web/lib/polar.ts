/**
 * Polar.sh checkout wiring (frontend). The founder pastes hosted checkout links per
 * product into env; until then, paid CTAs funnel to /signup (no dead buttons).
 *
 *   NEXT_PUBLIC_POLAR_CHECKOUT_STARTER=https://polar.sh/<org>/checkout/<product>
 *   NEXT_PUBLIC_POLAR_CHECKOUT_PRO=https://polar.sh/<org>/checkout/<product>
 *   NEXT_PUBLIC_POLAR_CHECKOUT_PAYG=https://polar.sh/<org>/checkout/<product>
 *
 * Product IDs (Polar dashboard), for reference when creating the hosted links:
 *   Starter = 64607ae8-4d14-4eb2-a873-4c07a88cc83e
 *   Pro     = 3d989817-94b9-41ee-958b-d1b56013c980
 *   PAYG    = e7966387-a84b-4e2e-847d-df99862cf2b6
 *
 * To map a purchase back to the Quip account, the checkout must carry the user id
 * (Polar `customer_external_id` / `metadata[user_id]`); the worker webhook reads it.
 * On purchase, the worker webhook maps product -> profiles.plan (subscription) or
 * -> profiles.payg_credits (one-off PAYG order). Upgrade path: dynamic checkout via
 * @polar-sh/nextjs once POLAR_ACCESS_TOKEN is wired (then this maps id -> SDK checkout).
 */
import type { PlanId } from "@/lib/plans";

type CheckoutKey = Exclude<PlanId, "free"> | "payg";

const CHECKOUT: Record<CheckoutKey, string | undefined> = {
  starter: process.env.NEXT_PUBLIC_POLAR_CHECKOUT_STARTER,
  pro: process.env.NEXT_PUBLIC_POLAR_CHECKOUT_PRO,
  payg: process.env.NEXT_PUBLIC_POLAR_CHECKOUT_PAYG,
};

/** Where a plan's CTA should go. Free -> signup; paid -> Polar checkout (or signup
 *  if not configured yet, so the funnel never dead-ends). */
export function checkoutHref(planId: PlanId): string {
  if (planId === "free") return "/signup";
  return CHECKOUT[planId] ?? "/signup";
}

/** Where the pay-as-you-go CTA goes (Polar one-off checkout, or signup until wired). */
export function paygCheckoutHref(): string {
  return CHECKOUT.payg ?? "/signup";
}

/** True when a paid product has a real Polar checkout link configured. */
export function isCheckoutConfigured(key: CheckoutKey): boolean {
  return Boolean(CHECKOUT[key]);
}
