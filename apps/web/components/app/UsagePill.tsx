"use client";

import { Clapperboard, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { cn } from "@/lib/cn";
import { deriveUsage, fmtMinutes, fmtVideos, useUsage } from "@/lib/useUsage";

// Always-visible (app header, every page) balance: VIDEOS and MINUTES left right now
// (monthly remaining + never-expiring PAYG). Three states like the dashboard meter —
// loading shows a dash, a failure shows a tappable amber "retry" chip (never a silent Free).

export function UsagePill({ className }: { className?: string }) {
  const { status, usage, reload } = useUsage();

  // Surface the failure instead of hiding it — tapping retries the fetch.
  if (status === "error") {
    return (
      <button
        type="button"
        onClick={reload}
        title="Couldn’t load your limits — tap to retry"
        className={cn(
          "inline-flex items-center gap-1.5 rounded-pill border border-warn/50 px-3 py-1.5 font-mono text-eyebrow uppercase text-warn transition-colors hover:bg-warn/10",
          className,
        )}
      >
        <TriangleAlert className="size-3.5" aria-hidden />
        limits N/A
      </button>
    );
  }

  const v = usage ? deriveUsage(usage) : null;
  const low = v?.out ?? false;

  return (
    <Link
      href="/pricing"
      title="Videos left right now — 1 video = 60 min. Click to upgrade or top up."
      className={cn(
        "inline-flex items-center gap-1.5 rounded-pill border px-3 py-1.5 font-mono text-eyebrow uppercase transition-colors",
        low ? "border-warn/50 text-warn" : "border-line text-muted hover:text-ink",
        className,
      )}
    >
      <Clapperboard className="size-3.5" aria-hidden />
      {!v ? (
        <span className="text-faint">—</span>
      ) : (
        <span className="tabular-nums">
          {fmtVideos(v.videosLeft)} videos · {fmtMinutes(v.minutesLeft)} min
        </span>
      )}
    </Link>
  );
}
