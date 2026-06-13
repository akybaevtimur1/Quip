/**
 * Polar.sh checkout wiring (frontend). The founder pastes hosted checkout links per
 * plan into env; until then, paid CTAs funnel to /signup (no dead buttons).
 *
 *   NEXT_PUBLIC_POLAR_CHECKOUT_STARTER=https://polar.sh/<org>/checkout/<product>
 *   NEXT_PUBLIC_POLAR_CHECKOUT_PRO=https://polar.sh/<org>/checkout/<product>
 *
 * To map a purchase back to the Quip account, the checkout should carry the user id
 * (Polar `customer_external_id` / `metadata[user_id]`); the worker webhook reads it.
 * On purchase, the Polar webhook (worker) maps product -> profiles.plan.
 */
import type { PlanId } from "@/lib/plans";

const CHECKOUT: Record<Exclude<PlanId, "free">, string | undefined> = {
  starter: process.env.NEXT_PUBLIC_POLAR_CHECKOUT_STARTER,
  pro: process.env.NEXT_PUBLIC_POLAR_CHECKOUT_PRO,
};

/** Where a plan's CTA should go. Free -> signup; paid -> Polar checkout (or signup
 *  if not configured yet, so the funnel never dead-ends). */
export function checkoutHref(planId: PlanId): string {
  if (planId === "free") return "/signup";
  return CHECKOUT[planId] ?? "/signup";
}

/** True when a paid plan has a real Polar checkout link configured. */
export function isCheckoutConfigured(planId: Exclude<PlanId, "free">): boolean {
  return Boolean(CHECKOUT[planId]);
}
