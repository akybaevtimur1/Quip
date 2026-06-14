"use client";

import { Loader2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { getUsage, type UsageInfo } from "@/lib/api";
import { cn } from "@/lib/cn";

// Живой расход за месяц: план + видео-кредиты (use/limit) + не сгорающий PAYG-баланс.
// Данные с воркера (GET /usage, с Supabase-JWT когда auth активен); без воркера/auth —
// тихий откат на дефолт free (dual-mode). Числа лимитов — из billing.py (один источник).

const FREE_DEFAULT: UsageInfo = {
  plan: "free",
  plan_name: "Free",
  monthly_videos: 2,
  monthly_minutes: 120,
  used_minutes: 0,
  remaining_minutes: 120,
  remaining_videos: 2,
  payg_videos: 0,
  payg_minutes: 0,
};

function planLabel(plan: string, name: string): string {
  return plan === "free" ? "Free" : name;
}

function fmtVideos(v: number): string {
  return Number.isInteger(v) ? String(v) : v.toFixed(1);
}

export function UsageMeter({ className }: { className?: string }) {
  const [usage, setUsage] = useState<UsageInfo>(FREE_DEFAULT);
  // Immediate feedback on click: /pricing nav can lag (cold route / slow network), and a
  // dead-looking link makes people click twice. Spinner + locked link until we leave.
  const [navigating, setNavigating] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getUsage()
      .then((u) => !cancelled && setUsage(u))
      .catch(() => {
        /* нет воркера/auth → остаёмся на дефолте free (dual-mode) */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const pct =
    usage.monthly_minutes > 0
      ? Math.min(100, (usage.used_minutes / usage.monthly_minutes) * 100)
      : 0;
  const near = pct >= 80;
  // Видео и минуты ОСТАЛОСЬ (месячный пул + не сгорающий PAYG).
  const videosLeft = usage.remaining_videos + usage.payg_videos;
  const minutesLeft = Math.round(usage.remaining_minutes + usage.payg_minutes);

  return (
    <div className={cn("rounded-xl border border-line bg-surface p-5", className)}>
      <div className="flex items-center justify-between">
        <h2 className="font-display text-base font-semibold text-ink">This month</h2>
        <span className="rounded-pill border border-line px-2.5 py-1 font-mono text-eyebrow uppercase text-muted">
          {planLabel(usage.plan, usage.plan_name)}
        </span>
      </div>

      <div className="mt-4">
        <div className="flex items-baseline justify-between">
          <span className="text-sm text-muted">Left this month</span>
          <span className="font-mono tabular-nums text-ink">
            <span className="text-lg font-semibold">{fmtVideos(videosLeft)}</span>
            <span className="text-sm text-muted"> videos · {minutesLeft} min</span>
          </span>
        </div>
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-3">
          <div
            className={cn(
              "h-full rounded-full transition-[width] duration-500 ease-snappy",
              near ? "bg-warn" : "bg-accent",
            )}
            style={{ width: `${pct}%` }}
          />
        </div>
        <p className="mt-1.5 text-xs text-muted">
          1 video = 60 min. A longer video uses minutes proportionally (90 min = 1.5 videos).
        </p>
      </div>

      {usage.payg_videos > 0 && (
        <div className="mt-3 flex items-center justify-between rounded-lg border border-line bg-surface-2 px-3 py-2">
          <span className="text-xs text-muted">Purchased (never expires)</span>
          <span className="font-mono text-sm tabular-nums text-ink">
            +{usage.payg_videos} videos · {usage.payg_minutes} min
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
