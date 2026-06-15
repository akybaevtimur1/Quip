import type { Metadata } from "next";
import { LegalDoc, type LegalSection } from "@/components/marketing/LegalDoc";
import { siteConfig } from "@/lib/site";

export const metadata: Metadata = {
  title: "Terms of Service",
  description: "The terms that govern your use of Quip.",
  robots: { index: false },
};

const email = siteConfig.supportEmail;

const sections: LegalSection[] = [
  {
    heading: "Acceptance of these terms",
    body: [
      `These Terms of Service ("Terms") govern your use of Quip, the website and app at quip.ink ("the Service"). By creating an account or using the Service, you agree to these Terms. If you do not agree, do not use the Service.`,
    ],
  },
  {
    heading: "The service",
    body: [
      "Quip turns long videos and podcasts into short vertical clips with captions, hooks and a confidence score. Features and limits may change as we improve the product.",
    ],
  },
  {
    heading: "Accounts and eligibility",
    body: [
      "You need an account to use most features. You agree to provide accurate information, to keep your credentials secure, and to be responsible for activity under your account.",
      "You must be old enough to enter into a binding contract in your country to use the Service.",
    ],
  },
  {
    heading: "Your content and responsibilities",
    body: [
      "You retain ownership of the media you upload and the clips you generate. You grant us a limited licence to store and process your content solely to provide the Service to you.",
      "You represent that you have all rights and consents needed for the content you upload, including the consent of any people who appear or speak in it, and that your use does not infringe anyone's rights or break any law.",
    ],
  },
  {
    heading: "Acceptable use",
    body: [
      "You agree not to use the Service to process content that is illegal, infringing, hateful, deceptive, or that violates the rights or privacy of others.",
      "You agree not to abuse, overload, reverse-engineer, or attempt to bypass the limits or security of the Service, and not to resell it without our permission.",
    ],
  },
  {
    heading: "Plans, credits and payment",
    body: [
      "Quip uses a credit model: one credit covers one video of up to 60 minutes of source, with longer videos using minutes proportionally. Plans, credit allowances and prices are shown on the Pricing page at quip.ink/pricing, which forms part of these Terms.",
      "Paid subscriptions renew automatically each billing period until cancelled. Pay-as-you-go credits are one-off purchases that do not expire. Payments are processed by our payment provider, Polar.",
      "We may change prices or plans going forward; changes will not affect the period you have already paid for.",
    ],
  },
  {
    heading: "Cancellation and refunds",
    body: [
      "You can cancel your subscription at any time from your account settings; cancellation stops future renewals, and you keep access until the end of the paid period.",
      `Refunds are handled case by case — there is no self-serve refund button by design. If something went wrong, contact us at ${email} and we will make it right.`,
    ],
  },
  {
    heading: "Free plan and watermark",
    body: [
      "The free plan lets you try the Service within a monthly limit. Free exports may carry a small watermark and a lower resolution; paid plans remove the watermark and export at higher quality.",
    ],
  },
  {
    heading: "Intellectual property",
    body: [
      "The Service itself — including the software, design, branding and content we provide (excluding your uploads and clips) — belongs to Quip and is protected by intellectual-property laws. These Terms do not grant you any rights in our brand or software beyond using the Service as intended.",
    ],
  },
  {
    heading: "Third-party services",
    body: [
      "The Service relies on third-party providers (for hosting, storage, transcription, AI and payments). Your use may also be subject to their terms. We are not responsible for third-party services outside our control.",
    ],
  },
  {
    heading: "Disclaimers",
    body: [
      `The Service is provided "as is" and "as available", without warranties of any kind. We do not guarantee that clip selection, captions, transcripts or confidence scores will be accurate, error-free, or suitable for any particular purpose, or that the Service will be uninterrupted.`,
    ],
  },
  {
    heading: "Limitation of liability",
    body: [
      "To the maximum extent permitted by law, Quip will not be liable for indirect, incidental, special or consequential damages, or for lost profits or data. Our total liability for any claim relating to the Service is limited to the amount you paid us for the Service in the three months before the claim.",
    ],
  },
  {
    heading: "Suspension and termination",
    body: [
      "You can stop using the Service and delete your account at any time. We may suspend or terminate access if you breach these Terms or use the Service in a way that risks harm to others or to the Service.",
    ],
  },
  {
    heading: "Changes to the service and terms",
    body: [
      "We may update the Service and these Terms over time. When we make material changes to these Terms we will update the date at the top of this page. Continued use after changes means you accept the updated Terms.",
    ],
  },
  {
    heading: "Governing law",
    body: [
      "These Terms are governed by the laws applicable at the operator's principal place of business, and any disputes will be handled by the competent courts there, except where mandatory consumer-protection law in your country of residence grants you stronger rights.",
    ],
  },
  {
    heading: "Contact",
    body: [`Questions about these Terms? Email us at ${email}.`],
  },
];

export default function TermsPage() {
  return (
    <LegalDoc
      title="Terms of Service"
      updated="15 June 2026"
      intro="These terms explain the rules for using Quip — your responsibilities, how plans and credits work, and the usual legal points — in plain language."
      sections={sections}
    />
  );
}
