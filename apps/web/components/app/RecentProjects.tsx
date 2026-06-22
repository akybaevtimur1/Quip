"use client";

import { AlertCircle, Check, Clock, Loader2, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useSyncExternalStore } from "react";
import { getJob } from "@/lib/api";
import {
  getRecentServerSnapshot,
  getRecentSnapshot,
  isTerminalStatus,
  type JobStatusLite,
  removeRecentProject,
  subscribeRecent,
  updateRecentProject,
} from "@/lib/recent";

const PROCESSING_LABEL: Partial<Record<JobStatusLite, string>> = {
  queued: "Queued",
  downloading: "Preparing",
  transcribing: "Transcribing",
  selecting: "Finding moments",
  rendering: "Rendering",
};

/** Compact status line for a recent item: live state + a "New" cue for unopened results. */
function StatusLine({
  status,
  nclips,
  reviewed,
}: {
  status?: JobStatusLite;
  nclips?: number;
  reviewed?: boolean;
}) {
  if (status === "done") {
    const clips = nclips != null ? `${nclips} clip${nclips === 1 ? "" : "s"}` : "Ready";
    if (!reviewed) {
      return (
        <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-accent/15 px-2 py-0.5 text-[11px] font-semibold text-accent">
          <span className="size-1.5 rounded-full bg-accent" />
          New · {clips}
        </span>
      );
    }
    return (
      <span className="inline-flex shrink-0 items-center gap-1 text-[11px] text-ok">
        <Check className="size-3.5" />
        {clips}
      </span>
    );
  }
  if (status === "failed") {
    return (
      <span className="inline-flex shrink-0 items-center gap-1 text-[11px] text-bad">
        <AlertCircle className="size-3.5" />
        Failed
      </span>
    );
  }
  if (status === "cancelled") {
    return <span className="shrink-0 text-[11px] text-faint">Stopped</span>;
  }
  // processing (or unknown-yet) → animated cue
  return (
    <span className="inline-flex shrink-0 items-center gap-1 text-[11px] text-muted">
      <Loader2 className="size-3 animate-spin" />
      {status ? (PROCESSING_LABEL[status] ?? "Processing") : "Processing"}…
    </span>
  );
}

export function RecentProjects() {
  const items = useSyncExternalStore(subscribeRecent, getRecentSnapshot, getRecentServerSnapshot);

  // Only re-subscribe the poller when the SET of non-terminal jobs changes (not on every
  // status tick) — so the interval isn't torn down/rebuilt each poll. Sorted for a stable key.
  const pendingKey = useMemo(
    () =>
      items
        .filter((p) => !isTerminalStatus(p.status))
        .map((p) => p.id)
        .sort()
        .join(","),
    [items],
  );

  // Poll the live status of any non-terminal recent project so the list reflects
  // "Processing… → Ready" even if it finished while the user was away. Stops once every
  // tracked job is terminal (empty pendingKey → effect returns early, no interval).
  useEffect(() => {
    if (!pendingKey) return;
    const ids = pendingKey.split(",");
    let active = true;
    const poll = () => {
      for (const id of ids) {
        getJob(id)
          .then((j) => {
            if (!active) return;
            updateRecentProject(id, {
              status: j.status as JobStatusLite,
              nclips: j.clips?.length || undefined,
            });
          })
          .catch(() => {
            /* transient network error → keep last-known status, retry next tick */
          });
      }
    };
    poll(); // immediate, then every 5s
    const t = setInterval(poll, 5000);
    return () => {
      active = false;
      clearInterval(t);
    };
  }, [pendingKey]);

  return (
    <div className="rounded-xl border border-line bg-surface p-5">
      <h2 className="font-display text-base font-semibold text-ink">Recent projects</h2>
      {items.length === 0 ? (
        <p className="mt-3 text-sm leading-relaxed text-muted">
          Projects created on this device will appear here.
        </p>
      ) : (
        <ul className="mt-3 space-y-1">
          {items.map((p) => (
            <li key={p.id} className="group flex items-center gap-1">
              <Link
                href={`/dashboard?job=${p.id}`}
                className="flex min-w-0 flex-1 items-center gap-2.5 rounded-md px-2 py-2 text-sm text-muted transition-colors hover:bg-surface-2 hover:text-ink"
              >
                <Clock className="size-3.5 shrink-0 text-faint" aria-hidden />
                <span className="min-w-0 flex-1 truncate">{p.label}</span>
                <StatusLine status={p.status} nclips={p.nclips} reviewed={p.reviewed} />
              </Link>
              <button
                type="button"
                onClick={() => removeRecentProject(p.id)}
                aria-label="Remove from recent"
                className="shrink-0 rounded-md p-2.5 text-faint transition hover:text-ink [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover:opacity-100"
              >
                <X className="size-3.5" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
