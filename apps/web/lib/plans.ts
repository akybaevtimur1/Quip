/**
 * Marketing display data for pricing — MIRRORS services/worker/app/billing.py PLANS
 * (the enforcement source of truth). Keep numbers in sync when billing.py changes.
 *
 * Video-minutes model: 1 "video" = 60 min of source. A plan's monthly limit is a pool of
 * minutes (videos × 60); a longer video just uses minutes proportionally (90 min = 1.5
 * videos), so the balance is shown as both videos and minutes. No token casino, no surprise
 * paywalls. A single video can be up to 3 hours; length is limited only by your remaining minutes.
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
    limitNote: "120 minutes of source to use however you like.",
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
    price: 15,
    tagline: "For creators shipping weekly.",
    limit: "10 videos / month",
    limitNote: "600 min total. Longer videos use minutes proportionally.",
    cta: "Choose Starter",
    features: [
      "Everything in Free",
      "No watermark, 1080p export",
      "All aspect ratios: 9:16, 1:1, 4:5, 16:9",
      "Top up anytime with pay-as-you-go videos",
    ],
  },
  {
    id: "pro",
    name: "Pro",
    price: 35,
    tagline: "For heavy repurposing.",
    limit: "30 videos / month",
    limitNote: "1800 min total. Longer videos use minutes proportionally.",
    cta: "Choose Pro",
    recommended: true,
    features: [
      "Everything in Starter",
      "Priority processing in the queue",
      "Early access to new features",
      "Pay-as-you-go videos when you need more",
    ],
  },
];

/** Pay-as-you-go: one-off videos, no subscription. Mirrors billing.PAYG_PRICE_USD. */
export const PAYG = {
  pricePerVideo: 3, // USD per video (source up to 60 min)
  title: "No subscription? Pay as you go.",
  body: "Buy videos one at a time. They never expire — one video covers up to 60 minutes of source.",
  cta: "Buy a video",
} as const;
