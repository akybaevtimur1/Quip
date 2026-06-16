"use client";

import { useCallback, useEffect, useState } from "react";
import { getUsage, type UsageInfo } from "./api";
import { isSupabaseConfigured } from "./supabase/config";

/** Free defaults — used ONLY in dual-mode dev (Supabase not configured), where the app
 *  runs open and there's no real plan to fetch. In production a fetch failure is surfaced
 *  as an error (status="error"), NOT silently shown as Free (что и пряталось раньше). */
export const FREE_DEFAULT: UsageInfo = {
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

export type UsageStatus = "loading" | "ok" | "error";

/** Fetches the live plan/limits with explicit loading/ok/error states (no silent Free
 *  fallback). Shared by the dashboard meter and the header pill so the rule "no silent
 *  fallbacks" holds in one place. `reload()` re-runs the fetch (retry button). */
export function useUsage(): { status: UsageStatus; usage: UsageInfo | null; reload: () => void } {
  // Dual-mode dev: no Supabase → worker is open, no plan to load → start in Free/ok (valid
  // state, not an error). Configured (prod) → start loading and fetch; failure → error.
  // `isSupabaseConfigured` is a stable module constant, so it's safe as initial state.
  const [status, setStatus] = useState<UsageStatus>(isSupabaseConfigured ? "loading" : "ok");
  const [usage, setUsage] = useState<UsageInfo | null>(isSupabaseConfigured ? null : FREE_DEFAULT);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    if (!isSupabaseConfigured) return; // dev: state already Free/ok, nothing to fetch
    let cancelled = false;
    getUsage()
      .then((u) => {
        if (cancelled) return;
        setUsage(u);
        setStatus("ok");
      })
      .catch(() => {
        if (cancelled) return;
        setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, [nonce]);

  // Retry: flip to loading (in this handler, not the effect) then re-run the fetch.
  const reload = useCallback(() => {
    setStatus("loading");
    setNonce((n) => n + 1);
  }, []);
  return { status, usage, reload };
}

export interface UsageView {
  planId: string;
  planName: string;
  /** Total videos available right now = monthly remaining + never-expiring PAYG. */
  videosLeft: number;
  /** Total minutes available right now (rounded). */
  minutesLeft: number;
  /** Monthly plan pool, this month (the bar): used / total, in whole "videos". */
  monthlyUsedVideos: number;
  monthlyTotalVideos: number;
  /** Monthly pool used, 0–100 (the orange bar's width). */
  usedPct: number;
  /** Monthly pool ≥80% used → bar goes amber. */
  near: boolean;
  /** Nothing left to create with (monthly + PAYG exhausted) → highlight red. */
  out: boolean;
  paygVideos: number;
  paygMinutes: number;
}

/** Pure: UsageInfo → display view. The bar is the MONTHLY pool only (resets monthly);
 *  the hero number is the TOTAL available (monthly remaining + PAYG). Keeping them
 *  distinct is what makes "how much is left" unambiguous. */
export function deriveUsage(u: UsageInfo): UsageView {
  const videosLeft = u.remaining_videos + u.payg_videos;
  const usedPct =
    u.monthly_minutes > 0
      ? Math.min(100, Math.max(0, (u.used_minutes / u.monthly_minutes) * 100))
      : 0;
  return {
    planId: u.plan,
    planName: u.plan === "free" ? "Free" : u.plan_name,
    videosLeft,
    minutesLeft: Math.round(u.remaining_minutes + u.payg_minutes),
    monthlyUsedVideos: u.used_minutes / 60,
    monthlyTotalVideos: u.monthly_videos,
    usedPct,
    near: usedPct >= 80,
    out: videosLeft < 1,
    paygVideos: u.payg_videos,
    paygMinutes: u.payg_minutes,
  };
}

/** "1,026" for big counts (instant read), "1.8" for small fractional, "2" for whole. */
export function fmtVideos(v: number): string {
  if (v >= 100) return Math.round(v).toLocaleString("en-US");
  if (Number.isInteger(v)) return String(v);
  return v.toFixed(1);
}

/** Whole minutes with thousands separators ("61,605"). */
export function fmtMinutes(m: number): string {
  return Math.round(m).toLocaleString("en-US");
}
