import type { Metadata } from "next";
import { LegalDoc, type LegalSection } from "@/components/marketing/LegalDoc";
import { siteConfig } from "@/lib/site";

export const metadata: Metadata = {
  title: "Privacy Policy",
  description: "How Quip collects, uses, stores and protects your data.",
  robots: { index: false },
};

const email = siteConfig.supportEmail;

const sections: LegalSection[] = [
  {
    heading: "Who we are",
    body: [
      `Quip ("Quip", "we", "us") provides a web service that turns long videos and podcasts into short vertical clips with captions, hooks and a confidence score. This policy explains what personal data we process when you use the website and the app at quip.ink, and your rights over it.`,
      `If you have any question about your data or this policy, contact us at ${email}.`,
    ],
  },
  {
    heading: "Information we collect",
    body: [
      "Account information: when you sign up we collect your email address and basic profile details. If you sign in with Google, we receive your name, email and avatar from Google's OAuth flow. We do not see your Google password.",
      "Content you upload: the videos, audio and any files you submit for processing, plus the transcripts, clips, captions and edits generated from them.",
      "Billing information: your plan, credit balance and transaction history. Card and payment details are handled by our payment processor (Polar) — we never receive or store your full card number.",
      "Usage and device data: pages visited, actions taken, approximate location, browser and device type, and similar technical data collected through analytics tools.",
    ],
  },
  {
    heading: "How we use your information",
    body: [
      "To provide the service: transcribe your media, detect strong moments, generate and reframe clips, render exports, and let you edit them.",
      "To run your account and billing: authenticate you, track your credit balance, process payments and prevent abuse of quotas.",
      "To support and improve the product: respond to your messages, diagnose issues, and understand which features are used so we can make Quip better.",
      "We do not sell your personal data, and we do not use the private contents of your uploads to train third-party models beyond what is required to generate your clips.",
    ],
  },
  {
    heading: "Your content and ownership",
    body: [
      "Your uploads and the clips you generate are yours. You grant us a limited licence to store and process them solely to provide the service to you (for example, transcription, clip selection, reframing and rendering).",
      "You are responsible for having the rights and any necessary consents for the media you upload, including consent from people who appear or speak in it.",
    ],
  },
  {
    heading: "Service providers (subprocessors)",
    body: [
      "We rely on a small set of trusted providers to run Quip, and share only the data each needs for its function:",
      "Supabase — authentication and database (account, billing and job records).",
      "Cloudflare R2 and CDN — storage and delivery of your source media, previews and clips (served via cdn.quip.ink).",
      "Modal — compute that runs the processing pipeline.",
      "Deepgram — speech-to-text transcription of your media.",
      "Google (Gemini) — AI used to select moments and write hooks.",
      "Polar — payment processing and subscription management.",
      "Vercel — website hosting and aggregate product analytics.",
      "Yandex.Metrica — website analytics and session-replay (see the cookies section).",
    ],
  },
  {
    heading: "Cookies, analytics and session replay",
    body: [
      "We use cookies and similar technologies for sign-in sessions and analytics. Vercel Analytics collects privacy-friendly, aggregate usage metrics.",
      "Yandex.Metrica is used for analytics and includes Webvisor, which records interactions on the page (clicks, scrolling, mouse movement and form activity, with sensitive fields masked) to help us understand and improve the experience. This data is used in aggregate to improve the site, not to identify you personally.",
      "You can block or delete cookies in your browser settings and use browser privacy controls. Disabling cookies may affect sign-in and some features.",
    ],
  },
  {
    heading: "Data retention and deletion",
    body: [
      "We keep your account and billing records for as long as your account is active and as required for legal and accounting purposes. Source media and generated clips are retained so you can access them in your dashboard.",
      `You can request deletion of your account and associated content at any time by contacting ${email}. We will delete or anonymise your data unless we are required to retain certain records (for example, payment records) by law.`,
    ],
  },
  {
    heading: "Security",
    body: [
      "We use industry-standard measures to protect your data, including encryption in transit, access controls, and reputable infrastructure providers. No method of transmission or storage is completely secure, but we work to protect your information and to limit access to it.",
    ],
  },
  {
    heading: "International transfers",
    body: [
      "Our providers may process and store data in different countries. Where data is transferred across borders, we rely on the safeguards offered by those providers. By using Quip you understand that your data may be processed in locations outside your country of residence.",
    ],
  },
  {
    heading: "Children",
    body: [
      "Quip is not intended for children. You must be old enough to enter into a binding agreement in your country to use the service. We do not knowingly collect data from children.",
    ],
  },
  {
    heading: "Your rights and choices",
    body: [
      `Depending on where you live, you may have the right to access, correct, export or delete your personal data, and to object to or restrict certain processing. To exercise these rights, contact ${email}.`,
      "You can also update some details and cancel your subscription directly in your account settings.",
    ],
  },
  {
    heading: "Changes to this policy",
    body: [
      "We may update this policy as the product evolves. When we make material changes we will update the date at the top of this page and, where appropriate, notify you. Continued use of Quip after changes means you accept the updated policy.",
    ],
  },
  {
    heading: "Contact",
    body: [`Questions about your privacy or this policy? Email us at ${email} and we will help.`],
  },
];

export default function PrivacyPage() {
  return (
    <LegalDoc
      title="Privacy Policy"
      updated="15 June 2026"
      intro="Your videos and clips are yours. This policy explains, in plain language, what data Quip processes, why, who helps us run the service, and the choices and rights you have."
      sections={sections}
    />
  );
}
