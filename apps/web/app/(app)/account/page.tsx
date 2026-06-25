import type { Metadata } from "next";
import { AccountBilling } from "@/components/app/AccountBilling";
import { AccountSecurity } from "@/components/app/AccountSecurity";
import { AppHeader } from "@/components/app/AppHeader";
import { PromoRedeem } from "@/components/app/PromoRedeem";
import { Container } from "@/components/ui/Container";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { Split } from "@/components/ui/Split";
import { siteConfig } from "@/lib/site";

export const metadata: Metadata = {
  title: "Account · Quip",
  robots: { index: false },
};

export default function AccountPage() {
  return (
    <div className="min-h-dvh">
      <AppHeader />
      <Container size="default" className="py-10 sm:py-14">
        {/* Left-aligned instrument header — a labeled section, not a centered title. */}
        <header className="max-w-prose">
          <Eyebrow tone="faint" as="p">
            Account
          </Eyebrow>
          <h1 className="mt-2 font-display text-h2 text-ink">Plan &amp; billing</h1>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            Your subscription, what it renews to, and where to redeem a code.
          </p>
        </header>

        {/* Asymmetric: subscription + sign-in = wide primary column, redeem + support = narrow rail. */}
        <Split variant="main-rail" gap="mt-8 gap-6 lg:gap-8">
          {/* Main column: billing on top, the optional set-password panel below it. */}
          <div className="space-y-6">
            <AccountBilling />
            <AccountSecurity />
          </div>
          <aside className="space-y-6">
            <PromoRedeem />
            {/* Refund / support note — its own quiet fascia in the rail. */}
            <div className="rounded-lg border border-line bg-surface p-5">
              <Eyebrow tone="faint" as="h2">
                Refunds &amp; support
              </Eyebrow>
              <p className="mt-2.5 text-sm leading-relaxed text-muted">
                Renewed by mistake and haven&apos;t used it? Cancel to stop future charges. For a
                refund, email{" "}
                <a
                  href={`mailto:${siteConfig.supportEmail}`}
                  className="text-ink underline decoration-line underline-offset-2 transition-colors hover:decoration-line-strong"
                >
                  {siteConfig.supportEmail}
                </a>{" "}
                and we&apos;ll sort it out.
              </p>
            </div>
          </aside>
        </Split>
      </Container>
    </div>
  );
}
