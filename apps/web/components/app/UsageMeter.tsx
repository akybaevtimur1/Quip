import Link from "next/link";
import { cn } from "@/lib/cn";

// Presentational. Defaults = Free plan limits (mirrors billing.py). Real usage is
// wired once Supabase/worker usage is connected (props become live).
function Quota({
  label,
  used,
  limit,
  unit,
}: {
  label: string;
  used: number;
  limit: number;
  unit?: string;
}) {
  const pct = limit > 0 ? Math.min(100, (used / limit) * 100) : 0;
  const near = pct >= 80;
  return (
    <div>
      <div className="flex items-center justify-between text-sm">
        <span className="text-muted">{label}</span>
        <span className="font-mono tabular-nums text-ink">
          {used} / {limit}
          {unit ? ` ${unit}` : ""}
        </span>
      </div>
      <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-surface-3">
        <div
          className={cn("h-full rounded-full", near ? "bg-warn" : "bg-accent")}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export function UsageMeter({
  planName = "Free",
  videosUsed = 0,
  videosLimit = 2,
  minutesUsed = 0,
  minutesLimit = 20,
  className,
}: {
  planName?: string;
  videosUsed?: number;
  videosLimit?: number;
  minutesUsed?: number;
  minutesLimit?: number;
  className?: string;
}) {
  return (
    <div className={cn("rounded-xl border border-line bg-surface p-5", className)}>
      <div className="flex items-center justify-between">
        <h2 className="font-display text-base font-semibold text-ink">This month</h2>
        <span className="rounded-pill border border-line px-2.5 py-1 font-mono text-eyebrow uppercase text-muted">
          {planName} plan
        </span>
      </div>
      <div className="mt-4 space-y-4">
        <Quota label="Videos" used={videosUsed} limit={videosLimit} />
        <Quota label="Source minutes" used={minutesUsed} limit={minutesLimit} unit="min" />
      </div>
      <Link href="/#pricing" className="mt-4 inline-block text-sm text-accent hover:underline">
        Upgrade for more &rarr;
      </Link>
    </div>
  );
}
