"use client";

import { Loader2, RotateCcw, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import { siteConfig } from "@/lib/site";
import { deriveUsage, fmtMinutes, fmtVideos, useUsage } from "@/lib/useUsage";

// Live plan + remaining videos for the dashboard. Three explicit states (no silent Free
// fallback): skeleton while loading, a real error with a support line if it fails, and the
// data otherwise. Hero = TOTAL videos available now (monthly remaining + never-expiring
// PAYG); the bar below is the MONTHLY pool only. Limit numbers come from billing.py via /usage.

/** Pulsing placeholder while /usage loads — same shape as the real card, so no layout jump. */
function MeterSkeleton() {
  return (
    <div
      className="rounded-xl border border-line bg-surface p-5"
      aria-busy="true"
      aria-label="Loading your plan and limits"
    >
      <div className="flex items-center justify-between">
        <div className="h-4 w-24 animate-pulse rounded bg-surface-3" />
        <div className="h-5 w-14 animate-pulse rounded-pill bg-surface-3" />
      </div>
      <div className="mt-5 h-10 w-32 animate-pulse rounded-lg bg-surface-3" />
      <div className="mt-2.5 h-3.5 w-28 animate-pulse rounded bg-surface-2" />
      <div className="mt-5 h-2 w-full animate-pulse rounded-full bg-surface-3" />
      <div className="mt-4 h-12 w-full animate-pulse rounded-lg bg-surface-2" />
    </div>
  );
}

/** Honest failure state — the plan/limits didn't load. Says it's on us, offers retry +
 *  the support inbox, instead of silently pretending the user is on Free. */
function MeterError({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="rounded-xl border border-bad/40 bg-bad/[0.06] p-5" role="alert">
      <div className="flex items-center gap-2 text-bad">
        <TriangleAlert className="size-4 shrink-0" aria-hidden />
        <h2 className="font-display text-base font-semibold">Couldn’t load your limits</h2>
      </div>
      <p className="mt-2 text-sm leading-relaxed text-muted">
        Your plan and remaining videos didn’t load — this is on our side, not your account.
        Try again, or email{" "}
        <a
          href={`mailto:${siteConfig.supportEmail}`}
          className="font-medium text-accent hover:underline"
        >
          {siteConfig.supportEmail}
        </a>{" "}
        and we’ll fix it as fast as we can.
      </p>
      <Button variant="secondary" size="sm" onClick={onRetry} className="mt-4">
        <RotateCcw className="size-4" aria-hidden />
        Try again
      </Button>
    </div>
  );
}

export function UsageMeter({ className }: { className?: string }) {
  const { status, usage, reload } = useUsage();
  // Immediate feedback on click: /pricing nav can lag (cold route / slow network), and a
  // dead-looking link makes people click twice. Spinner + locked link until we leave.
  const [navigating, setNavigating] = useState(false);

  if (status === "loading") return <MeterSkeleton />;
  if (status === "error" || !usage)
    return (
      <div className={className}>
        <MeterError onRetry={reload} />
      </div>
    );

  const v = deriveUsage(usage);

  return (
    <div className={cn("rounded-xl border border-line bg-surface p-5", className)}>
      <div className="flex items-center justify-between">
        <h2 className="font-display text-base font-semibold text-ink">This month</h2>
        <span className="rounded-pill border border-line px-2.5 py-1 font-mono text-eyebrow uppercase text-muted">
          {v.planName}
        </span>
      </div>

      {/* Hero: the one number you read at a glance — how many videos you can make now. */}
      <div className="mt-4 flex items-end justify-between gap-3">
        <div>
          <div
            className={cn(
              "font-display text-[2.75rem] font-bold leading-none tracking-tight tabular-nums",
              v.out ? "text-bad" : "text-ink",
            )}
          >
            {fmtVideos(v.videosLeft)}
          </div>
          <div className="mt-1.5 text-sm text-muted">videos left</div>
        </div>
        <div className="pb-0.5 text-right">
          <div className="font-mono text-base tabular-nums text-ink">{fmtMinutes(v.minutesLeft)}</div>
          <div className="text-xs text-muted">minutes</div>
        </div>
      </div>

      {/* Monthly pool bar — clearly labeled so it's never mistaken for the total above. */}
      <div className="mt-5">
        <div className="flex items-center justify-between text-xs">
          <span className="text-muted">Monthly plan</span>
          <span className="font-mono tabular-nums text-muted">
            {fmtVideos(v.monthlyUsedVideos)} / {v.monthlyTotalVideos} used
          </span>
        </div>
        <div className="mt-2 h-2 overflow-hidden rounded-full bg-surface-3">
          <div
            className={cn(
              "h-full rounded-full transition-[width] duration-500 ease-snappy",
              v.near ? "bg-warn" : "bg-accent",
            )}
            style={{ width: `${v.usedPct}%` }}
          />
        </div>
        <p className="mt-1.5 text-xs text-faint">
          Resets monthly · 1 video = 60 min (90 min = 1.5 videos)
        </p>
      </div>

      {/* Never-expiring purchased balance, kept distinct from the monthly pool. */}
      {v.paygVideos > 0 && (
        <div className="mt-4 flex items-center justify-between rounded-lg border border-line bg-surface-2 px-3 py-2.5">
          <span className="text-xs text-muted">Purchased · never expires</span>
          <span className="font-mono text-sm tabular-nums text-ink">
            +{fmtVideos(v.paygVideos)} videos · {fmtMinutes(v.paygMinutes)} min
          </span>
        </div>
      )}

      <Link
        href="/pricing"
        onClick={() => setNavigating(true)}
        aria-busy={navigating || undefined}
        className={cn(
          "mt-4 inline-flex items-center gap-1.5 text-sm text-accent hover:underline",
          navigating && "pointer-events-none opacity-70",
        )}
      >
        {navigating && <Loader2 className="size-3.5 animate-spin" aria-hidden />}
        {navigating ? "Opening…" : "Upgrade limits →"}
      </Link>
    </div>
  );
}
