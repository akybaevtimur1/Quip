import type { Metadata } from "next";
import { AccountBilling } from "@/components/app/AccountBilling";
import { AppHeader } from "@/components/app/AppHeader";

export const metadata: Metadata = {
  title: "Account · Quip",
  robots: { index: false },
};

export default function AccountPage() {
  return (
    <div className="min-h-dvh">
      <AppHeader />
      <main className="mx-auto max-w-2xl px-5 py-10 sm:px-8 sm:py-12">
        <h1 className="font-display text-h2 text-ink">Account</h1>
        <p className="mt-2 text-sm text-muted">Manage your plan and subscription.</p>
        <div className="mt-8">
          <AccountBilling />
        </div>
      </main>
    </div>
  );
}
