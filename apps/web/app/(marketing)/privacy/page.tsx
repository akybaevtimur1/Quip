import type { Metadata } from "next";
import { Container } from "@/components/ui/Container";

export const metadata: Metadata = {
  title: "Privacy Policy",
  description: "How Quip handles your data.",
  robots: { index: false },
};

export default function PrivacyPage() {
  return (
    <Container className="max-w-2xl py-20 sm:py-28">
      <h1 className="font-display text-h2 text-ink sm:text-display-lg">Privacy Policy</h1>
      <p className="mt-6 text-lead text-muted">
        Your videos and clips are yours. We process them to generate clips and never sell your data.
        Authentication and storage run through Supabase; payments through Polar.sh.
      </p>
      <p className="mt-4 text-sm text-faint">
        A full privacy policy will be published here before general availability. Reach out anytime
        with questions about your data.
      </p>
    </Container>
  );
}
