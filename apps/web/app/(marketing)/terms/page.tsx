import type { Metadata } from "next";
import { Container } from "@/components/ui/Container";

export const metadata: Metadata = {
  title: "Terms of Service",
  description: "Quip terms of service.",
  robots: { index: false },
};

export default function TermsPage() {
  return (
    <Container className="prose-none max-w-2xl py-20 sm:py-28">
      <h1 className="font-display text-h2 text-ink sm:text-display-lg">Terms of Service</h1>
      <p className="mt-6 text-lead text-muted">
        These terms are being finalized ahead of launch. By using Quip during early access you agree
        to use it lawfully and accept that the service is provided as-is while we polish it.
      </p>
      <p className="mt-4 text-sm text-faint">
        Questions? Reach out and we&rsquo;ll help. A full agreement will be published here before
        general availability.
      </p>
    </Container>
  );
}
