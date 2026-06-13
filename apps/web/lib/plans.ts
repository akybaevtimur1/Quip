/**
 * Marketing display data for pricing — MIRRORS services/worker/app/billing.py PLANS
 * (the enforcement source of truth). Keep numbers in sync when billing.py changes.
 */
export type PlanId = "free" | "starter" | "pro";

export interface PlanDisplay {
  id: PlanId;
  name: string;
  price: number; // USD / month
  tagline: string;
  cta: string;
  highlighted?: boolean;
  features: string[];
}

export const PLANS: PlanDisplay[] = [
  {
    id: "free",
    name: "Free",
    price: 0,
    tagline: "See it work, no card required.",
    cta: "Start free",
    features: [
      "2 videos / month",
      "20 source minutes / month",
      "Explainable clips — hook, score & reason",
      "Smooth 9:16 reframe, no flashes",
      "Full editor & caption styles",
      "720p export with watermark",
    ],
  },
  {
    id: "starter",
    name: "Starter",
    price: 12,
    tagline: "For creators shipping weekly.",
    cta: "Choose Starter",
    highlighted: true,
    features: [
      "20 videos / month",
      "200 source minutes / month",
      "Everything in Free",
      "No watermark",
      "1080p export",
      "All aspect ratios — 9:16, 1:1, 4:5, 16:9",
    ],
  },
  {
    id: "pro",
    name: "Pro",
    price: 29,
    tagline: "For heavy repurposing.",
    cta: "Choose Pro",
    features: [
      "100 videos / month",
      "1000 source minutes / month",
      "Everything in Starter",
      "Priority processing",
      "Early access to new features",
    ],
  },
];
