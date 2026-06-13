"use client";

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
  monthly_credits: 2,
  used_credits: 0,
  remaining_credits: 2,
  payg_credits: 0,
};

function planLabel(plan: string, name: string): string {
  return plan === "free" ? "Free" : name;
}

export function UsageMeter({ className }: { className?: string }) {
  const [usage, setUsage] = useState<UsageInfo>(FREE_DEFAULT);

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
    usage.monthly_credits > 0
      ? Math.min(100, (usage.used_credits / usage.monthly_credits) * 100)
      : 0;
  const near = pct >= 80;

  return (
    <div className={cn("rounded-xl border border-line bg-surface p-5", className)}>
      <div className="flex items-center justify-between">
        <h2 className="font-display text-base font-semibold text-ink">This month</h2>
        <span className="rounded-pill border border-line px-2.5 py-1 font-mono text-eyebrow uppercase text-muted">
          {planLabel(usage.plan, usage.plan_name)}
        </span>
      </div>

      <div className="mt-4">
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted">Videos</span>
          <span className="font-mono tabular-nums text-ink">
            {usage.used_credits} / {usage.monthly_credits}
          </span>
        </div>
        <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-surface-3">
          <div
            className={cn(
              "h-full rounded-full transition-[width] duration-500 ease-snappy",
              near ? "bg-warn" : "bg-accent",
            )}
            style={{ width: `${pct}%` }}
          />
        </div>
        <p className="mt-1.5 text-xs text-muted">1 video = 1 credit (source up to 60 min)</p>
      </div>

      {usage.payg_credits > 0 && (
        <div className="mt-3 flex items-center justify-between rounded-lg border border-line bg-surface-2 px-3 py-2">
          <span className="text-xs text-muted">Purchased (never expires)</span>
          <span className="font-mono text-sm tabular-nums text-ink">
            +{usage.payg_credits}
          </span>
        </div>
      )}

      <Link href="/pricing" className="mt-4 inline-block text-sm text-accent hover:underline">
        Upgrade limits &rarr;
      </Link>
    </div>
  );
}
