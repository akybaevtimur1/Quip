"use client";

import { Clapperboard } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { getUsage, type UsageInfo } from "@/lib/api";
import { cn } from "@/lib/cn";

// Always-visible (in the app header, every page) balance: how many VIDEOS and MINUTES are
// left this month. 1 video = 60 min; the remainder is fractional (e.g. "1.8 videos · 108 min").
// Includes the never-expiring PAYG balance. Tap → pricing. Dual-mode: no worker/auth → free.

function fmtVideos(v: number): string {
  return Number.isInteger(v) ? String(v) : v.toFixed(1);
}

export function UsagePill({ className }: { className?: string }) {
  const [u, setU] = useState<UsageInfo | null>(null);

  useEffect(() => {
    let cancelled = false;
    getUsage()
      .then((x) => !cancelled && setU(x))
      .catch(() => {
        /* no worker/auth → leave empty (dual-mode) */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const videosLeft = u ? u.remaining_videos + u.payg_videos : null;
  const minutesLeft = u ? Math.round(u.remaining_minutes + u.payg_minutes) : null;
  const low = videosLeft !== null && videosLeft < 1;

  return (
    <Link
      href="/pricing"
      title="Videos left this month — 1 video = 60 min. Click to upgrade or top up."
      className={cn(
        "inline-flex items-center gap-1.5 rounded-pill border px-3 py-1.5 font-mono text-eyebrow uppercase transition-colors",
        low ? "border-warn/50 text-warn" : "border-line text-muted hover:text-ink",
        className,
      )}
    >
      <Clapperboard className="size-3.5" aria-hidden />
      {videosLeft === null ? (
        <span className="text-faint">—</span>
      ) : (
        <span className="tabular-nums">
          {fmtVideos(videosLeft)} videos · {minutesLeft} min
        </span>
      )}
    </Link>
  );
}
