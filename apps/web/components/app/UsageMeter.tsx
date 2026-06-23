"use client";

import { Loader2, RotateCcw, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { Numeral } from "@/components/ui/Numeral";
import { Skeleton } from "@/components/ui/Skeleton";
import { Stat } from "@/components/ui/Stat";
import { cn } from "@/lib/cn";
import { siteConfig } from "@/lib/site";
import { deriveUsage, fmtMinutes, fmtVideos, useUsage } from "@/lib/useUsage";

// Live plan + remaining videos for the dashboard rail. Three explicit states (no silent Free
// fallback): skeleton while loading, a real error with a support line if it fails, and the
// data otherwise. Hero = TOTAL videos available now (monthly remaining + never-expiring
// PAYG); the meter below is the MONTHLY pool only. Limit numbers come from billing.py via /usage.

/** Pulsing placeholder while /usage loads — same shape as the real panel, so no layout jump. */
function MeterSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading your plan and limits">
      <div className="flex items-center justify-between">
        <Skeleton className="h-3 w-12" />
        <Skeleton className="h-3 w-14" />
      </div>
      <Skeleton className="mt-4 h-10 w-28" />
      <Skeleton className="mt-4 h-0.5 w-full" />
      <Skeleton className="mt-4 h-10 w-full" />
    </div>
  );
}

/** Honest failure state — the plan/limits didn't load. Says it's on us, offers retry +
 *  the support inbox, instead of silently pretending the user is on Free. */
function MeterError({ onRetry }: { onRetry: () => void }) {
  return (
    <div role="alert">
      <div className="flex items-center gap-2 text-bad">
        <TriangleAlert className="size-4 shrink-0" aria-hidden />
        <h2 className="font-display text-base font-semibold">Couldn’t load your limits</h2>
      </div>
      <p className="mt-2 text-sm leading-relaxed text-muted">
        Your plan and remaining videos didn’t load — this is on our side, not your account. Try
        again, or email{" "}
        <a
          href={`mailto:${siteConfig.supportEmail}`}
          className="font-medium text-accent hover:underline"
        >
          {siteConfig.supportEmail}
        </a>
        .
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

  let body: React.ReactNode;
  let plan: string | null = null;

  if (status === "loading") {
    body = <MeterSkeleton />;
  } else if (status === "error" || !usage) {
    body = <MeterError onRetry={reload} />;
  } else {
    const v = deriveUsage(usage);
    plan = v.planName;
    body = (
      <>
        {/* Hero readout: the one number — how many videos you can make right now. */}
        <Stat
          label="Videos left"
          value={fmtVideos(v.videosLeft)}
          size="lg"
          tone={v.out ? "bad" : "ink"}
          meter={Math.max(0, 1 - v.usedPct / 100)}
          meterTone={v.out ? "bad" : v.near ? "warn" : "neutral"}
        />

        {/* Compact mono footer: monthly pool, PAYG, reset rule — one line each, varied weight. */}
        <dl className="mt-4 space-y-1.5 border-t border-line pt-3.5 text-xs">
          <div className="flex items-center justify-between">
            <dt className="text-muted">Monthly plan</dt>
            <dd>
              <Numeral className={v.near ? "text-warn" : "text-ink"}>
                {fmtVideos(v.monthlyUsedVideos)} / {v.monthlyTotalVideos}
              </Numeral>
              <span className="ml-1 text-faint">used</span>
            </dd>
          </div>
          <div className="flex items-center justify-between">
            <dt className="text-muted">Minutes left</dt>
            <dd>
              <Numeral className="text-ink">{fmtMinutes(v.minutesLeft)}</Numeral>
              <span className="ml-1 text-faint">min</span>
            </dd>
          </div>
          {v.paygVideos > 0 && (
            <div className="flex items-center justify-between">
              <dt className="text-muted">Purchased · never expires</dt>
              <dd>
                <Numeral className="text-ink">
                  +{fmtVideos(v.paygVideos)} · {fmtMinutes(v.paygMinutes)}
                </Numeral>
                <span className="ml-1 text-faint">min</span>
              </dd>
            </div>
          )}
        </dl>
        <p className="mt-2.5 text-eyebrow text-faint">Resets monthly · 1 video = 60 min</p>

        <Link
          href="/pricing"
          onClick={() => setNavigating(true)}
          aria-busy={navigating || undefined}
          className={cn(
            "mt-3.5 inline-flex items-center gap-1.5 text-sm text-accent hover:underline",
            navigating && "pointer-events-none opacity-70",
          )}
        >
          {navigating && <Loader2 className="size-3.5 animate-spin" aria-hidden />}
          {navigating ? "Opening…" : "Upgrade limits →"}
        </Link>
      </>
    );
  }

  return (
    <section className={cn("rounded-lg border border-line bg-surface p-5", className)}>
      <div className="mb-4 flex items-center justify-between">
        <Eyebrow tone="muted" as="h2">
          Usage
        </Eyebrow>
        {plan && (
          <span className="font-mono text-eyebrow uppercase tabular-nums text-faint">{plan}</span>
        )}
      </div>
      {body}
    </section>
  );
}
