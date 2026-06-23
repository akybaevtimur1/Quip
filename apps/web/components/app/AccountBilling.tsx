"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { EmptyState } from "@/components/ui/EmptyState";
import { Numeral } from "@/components/ui/Numeral";
import { Skeleton } from "@/components/ui/Skeleton";
import { Spinner } from "@/components/ui/Spinner";
import { Stat } from "@/components/ui/Stat";

type Sub = {
  id: string;
  status: string;
  productName: string;
  amount: number | null;
  recurringInterval: string | null;
  currentPeriodEnd: string | null;
  cancelAtPeriodEnd: boolean;
};

/** Raw Polar subscription status → a friendly label. Never leak the raw enum to the UI. */
const STATUS_LABEL: Record<string, string> = {
  active: "Active",
  trialing: "Trial",
  past_due: "Payment due",
  unpaid: "Payment due",
  incomplete: "Incomplete",
  incomplete_expired: "Expired",
  canceled: "Canceled",
};

/** Status → calibrated Badge tone. thought = healthy, coral = cancelling (the one live
 *  signal), bad = payment problem. */
function statusBadge(sub: Sub): { tone: BadgeTone; label: string } {
  if (sub.cancelAtPeriodEnd) return { tone: "accent", label: "Cancelling" };
  if (sub.status === "past_due" || sub.status === "unpaid")
    return { tone: "bad", label: STATUS_LABEL[sub.status] };
  if (sub.status === "active" || sub.status === "trialing")
    return { tone: "thought", label: STATUS_LABEL[sub.status] };
  return { tone: "neutral", label: STATUS_LABEL[sub.status] ?? "Inactive" };
}

function fmtDate(iso: string | null): string {
  if (!iso) return "end of period";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? "end of period"
    : d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

/** One hairline-divided ledger row: mono eyebrow label left, right-aligned value. */
function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-3">
      <Eyebrow tone="faint">{label}</Eyebrow>
      <div className="min-w-0 text-right text-sm text-ink">{children}</div>
    </div>
  );
}

/** Plan + self-serve "Cancel subscription" (cancel at period end). No refund button by
 *  design — refunds go through support email (shown in the account-page rail). The panel
 *  reads like a receipt/ledger: a price readout above a mono spec table. */
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

  const badge = !loading && sub ? statusBadge(sub) : null;

  return (
    <section className="rounded-lg border border-line bg-surface">
      {/* Panel header: eyebrow label left, live status right, split by a hairline. */}
      <header className="flex items-center justify-between gap-3 border-b border-line px-5 py-3.5 sm:px-6">
        <Eyebrow tone="muted" as="h2">
          Subscription
        </Eyebrow>
        {badge && (
          <Badge tone={badge.tone} dot>
            {badge.label}
          </Badge>
        )}
      </header>

      <div className="px-5 py-5 sm:px-6 sm:py-6">
        {loading ? (
          <LoadingLedger />
        ) : error && !sub ? (
          <EmptyState
            title="Couldn’t load your subscription"
            description="This is on our side, not your account. Refresh to try again."
          />
        ) : !sub ? (
          <EmptyState
            title="You’re on the Free plan"
            description="No active subscription. Upgrade for more videos a month and never-expiring top-ups."
            action={
              <Link
                href="/#pricing"
                className="text-sm font-medium text-accent hover:underline"
              >
                See plans →
              </Link>
            }
          />
        ) : (
          <div>
            {/* Hero readout: the price you pay, captioned by its cadence. The one
                signature Stat on the page — so price/cadence live only here. */}
            <Stat
              label={sub.recurringInterval ? `Billed ${sub.recurringInterval}ly` : "Subscription"}
              value={sub.amount != null ? `$${(sub.amount / 100).toFixed(0)}` : "—"}
              suffix={sub.recurringInterval ? `/ ${sub.recurringInterval}` : undefined}
              size="lg"
              tone="ink"
            />

            {/* Receipt ledger: hairline-divided spec rows, right-aligned values. Each row is
                a distinct fact — price/cadence are the hero above, so they aren't repeated. */}
            <dl className="mt-6 divide-y divide-line border-t border-line">
              <Row label="Plan">
                <span className="font-medium">{sub.productName}</span>
              </Row>
              <Row label="Status">
                <span className={badge?.tone === "bad" ? "text-bad" : "text-ink"}>
                  {badge?.label ?? "—"}
                </span>
              </Row>
              <Row label={sub.cancelAtPeriodEnd ? "Access until" : "Renews"}>
                <Numeral className="text-ink">{fmtDate(sub.currentPeriodEnd)}</Numeral>
              </Row>
              <Row label="Next charge">
                {sub.cancelAtPeriodEnd ? (
                  <span className="text-muted">None — won’t renew</span>
                ) : sub.amount != null ? (
                  <Numeral className="text-ink">${(sub.amount / 100).toFixed(0)}</Numeral>
                ) : (
                  <span className="text-muted">—</span>
                )}
              </Row>
            </dl>

            {/* Action zone. Reserve vertical space so the rail note never jumps when the
                inline confirm/error appears. */}
            <div className="mt-6">
              {sub.cancelAtPeriodEnd ? (
                <p className="text-sm leading-relaxed text-muted">
                  Set to cancel — you keep access until{" "}
                  <span className="text-ink">
                    <Numeral>{fmtDate(sub.currentPeriodEnd)}</Numeral>
                  </span>{" "}
                  and won’t be charged again.
                </p>
              ) : confirming ? (
                <div className="rounded-lg border border-line bg-surface-2 p-4">
                  <p className="text-sm text-ink">Cancel your subscription?</p>
                  <p className="mt-1 text-sm leading-relaxed text-muted">
                    You keep access until{" "}
                    <Numeral className="text-ink">{fmtDate(sub.currentPeriodEnd)}</Numeral> — no
                    further charges, and everything you’ve made stays yours.
                  </p>
                  <div className="mt-3.5 flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={cancel}
                      disabled={busy}
                      className="inline-flex items-center gap-1.5 rounded-md border border-bad/40 bg-surface px-3.5 py-2 text-sm text-bad transition hover:bg-bad/10 disabled:opacity-60"
                    >
                      {busy && <Spinner size="sm" className="text-bad" />}
                      Yes, cancel
                    </button>
                    <button
                      type="button"
                      onClick={() => setConfirming(false)}
                      disabled={busy}
                      className="rounded-md border border-line px-3.5 py-2 text-sm text-muted transition hover:border-line-strong hover:text-ink"
                    >
                      Keep it
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

              {error && (
                <p role="alert" className="mt-3 text-sm text-bad">
                  {error}
                </p>
              )}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

/** Loading state that mirrors the final ledger — hero readout + four spec rows — so
 *  nothing reflows when the data lands. */
function LoadingLedger() {
  return (
    <div aria-busy="true" aria-label="Loading your subscription">
      <Skeleton className="h-3 w-24" />
      <Skeleton className="mt-2.5 h-11 w-36" />
      <div className="mt-6 divide-y divide-line border-t border-line">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="flex items-center justify-between gap-4 py-3">
            <Skeleton className="h-3 w-20" />
            <Skeleton className="h-3.5 w-28" />
          </div>
        ))}
      </div>
      <Skeleton className="mt-6 h-9 w-40" />
    </div>
  );
}
