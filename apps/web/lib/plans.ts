/**
 * Marketing display data for pricing — MIRRORS services/worker/app/billing.py PLANS
 * (the enforcement source of truth). Keep numbers in sync when billing.py changes.
 *
 * Credit model: 1 credit = 1 video up to 60 min of source. Longer videos cost more
 * credits (ceil(minutes / 60)). A plan's monthly limit is a number of video-credits:
 * no token casino, no surprise paywalls.
 */
export type PlanId = "free" | "starter" | "pro";

export interface PlanDisplay {
  id: PlanId;
  name: string;
  price: number; // USD / month
  tagline: string;
  /** Headline limit, shown large under the price (e.g. "10 videos / month"). */
  limit: string;
  /** One line clarifying what a "video" means on this plan. */
  limitNote: string;
  cta: string;
  /** The recommended plan gets the accent treatment (badge + ring + coral CTA). */
  recommended?: boolean;
  features: string[];
}

export const PLANS: PlanDisplay[] = [
  {
    id: "free",
    name: "Free",
    price: 0,
    tagline: "See it work, no card required.",
    limit: "2 videos / month",
    limitNote: "Source up to 30 min per video.",
    cta: "Start free",
    features: [
      "Explainable clips with hook, score and reason",
      "Smooth 9:16 reframe that tracks the speaker",
      "Full editor and every caption style",
      "720p export with a small watermark",
    ],
  },
  {
    id: "starter",
    name: "Starter",
    price: 10,
    tagline: "For creators shipping weekly.",
    limit: "10 videos / month",
    limitNote: "Up to 60 min each. Longer videos use more credits.",
    cta: "Choose Starter",
    features: [
      "Everything in Free",
      "No watermark, 1080p export",
      "All aspect ratios: 9:16, 1:1, 4:5, 16:9",
      "Top up anytime with pay-as-you-go credits",
    ],
  },
  {
    id: "pro",
    name: "Pro",
    price: 25,
    tagline: "For heavy repurposing.",
    limit: "30 videos / month",
    limitNote: "Up to 60 min each. Longer videos use more credits.",
    cta: "Choose Pro",
    recommended: true,
    features: [
      "Everything in Starter",
      "Priority processing in the queue",
      "Early access to new features",
      "Pay-as-you-go credits when you need more",
    ],
  },
];

/** Pay-as-you-go: one-off credits, no subscription. Mirrors billing.PAYG_PRICE_USD. */
export const PAYG = {
  pricePerVideo: 2, // USD per video-credit (source up to 60 min)
  title: "No subscription? Pay as you go.",
  body: "Buy credits one at a time. They never expire, and one credit covers a video up to 60 minutes.",
  cta: "Buy a credit",
} as const;
