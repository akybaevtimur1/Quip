"use client";

import { Loader2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { siteConfig } from "@/lib/site";

type Sub = {
  id: string;
  status: string;
  productName: string;
  amount: number | null;
  recurringInterval: string | null;
  currentPeriodEnd: string | null;
  cancelAtPeriodEnd: boolean;
};

function fmtDate(iso: string | null): string {
  if (!iso) return "the end of your billing period";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? "the end of your billing period"
    : d.toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" });
}

/** Plan + self-serve "Cancel subscription" (cancel at period end). No refund button by
 *  design — refunds go through support email (shown below). */
export function AccountBilling() {
  const [loading, setLoading] = useState(true);
  const [sub, setSub] = useState<Sub | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/subscription")
      .then((r) => r.json())
      .then((d) => !cancelled && setSub(d.subscription ?? null))
      .catch(() => !cancelled && setError("Couldn’t load your subscription."))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  async function cancel() {
    setBusy(true);
    setError(null);
    try {
      const r = await fetch("/api/subscription/cancel", { method: "POST" });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error ?? "Cancellation failed");
      setSub((prev) =>
        prev
          ? { ...prev, cancelAtPeriodEnd: true, currentPeriodEnd: d.endsAt ?? prev.currentPeriodEnd }
          : prev,
      );
      setConfirming(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Cancellation failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-xl border border-line bg-surface p-6">
      <h2 className="font-display text-lg font-semibold text-ink">Subscription</h2>

      {loading ? (
        <p className="mt-4 flex items-center gap-2 text-sm text-muted">
          <Loader2 className="size-4 animate-spin" aria-hidden /> Loading…
        </p>
      ) : !sub ? (
        <div className="mt-4">
          <p className="text-sm text-muted">
            You’re on the <span className="font-medium text-ink">Free</span> plan — no active
            subscription.
          </p>
          <Link href="/#pricing" className="mt-3 inline-block text-sm text-accent hover:underline">
            See plans →
          </Link>
        </div>
      ) : (
        <div className="mt-4 space-y-4">
          <div className="flex items-center justify-between gap-3 rounded-lg border border-line bg-surface-2 px-4 py-3">
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-ink">{sub.productName}</p>
              <p className="text-xs text-muted">
                {sub.amount != null ? `$${(sub.amount / 100).toFixed(0)}` : ""}
                {sub.recurringInterval ? ` / ${sub.recurringInterval}` : ""}
              </p>
            </div>
            <span className="shrink-0 rounded-pill border border-line px-2.5 py-1 font-mono text-eyebrow uppercase text-muted">
              {sub.cancelAtPeriodEnd ? "Cancelling" : sub.status}
            </span>
          </div>

          {sub.cancelAtPeriodEnd ? (
            <p className="text-sm text-muted">
              Your subscription is set to cancel on{" "}
              <span className="font-medium text-ink">{fmtDate(sub.currentPeriodEnd)}</span>. You keep
              access until then and won’t be charged again.
            </p>
          ) : confirming ? (
            <div className="rounded-lg border border-line bg-surface-2 p-4">
              <p className="text-sm text-ink">Cancel your subscription?</p>
              <p className="mt-1 text-xs text-muted">
                You’ll keep access until {fmtDate(sub.currentPeriodEnd)} — no further charges, and you
                keep everything you’ve already created.
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={cancel}
                  disabled={busy}
                  className="inline-flex items-center gap-1.5 rounded-md border border-bad/40 bg-surface px-3 py-1.5 text-sm text-bad transition hover:bg-bad/10 disabled:opacity-60"
                >
                  {busy && <Loader2 className="size-3.5 animate-spin" aria-hidden />}
                  Yes, cancel
                </button>
                <button
                  type="button"
                  onClick={() => setConfirming(false)}
                  disabled={busy}
                  className="rounded-md border border-line px-3 py-1.5 text-sm text-muted transition hover:text-ink"
                >
                  Keep subscription
                </button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setConfirming(true)}
              className="rounded-md border border-line px-3.5 py-2 text-sm text-muted transition hover:border-line-strong hover:text-ink"
            >
              Cancel subscription
            </button>
          )}

          {error && <p className="text-sm text-bad">{error}</p>}
        </div>
      )}

      <div className="mt-6 border-t border-line pt-4">
        <p className="text-xs text-muted">
          Renewed by mistake and haven’t used it yet? Cancel above to stop future charges. For a
          refund, email{" "}
          <a href={`mailto:${siteConfig.supportEmail}`} className="text-accent hover:underline">
            {siteConfig.supportEmail}
          </a>{" "}
          and we’ll sort it out.
        </p>
      </div>
    </div>
  );
}
