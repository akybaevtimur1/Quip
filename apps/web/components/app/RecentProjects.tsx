"use client";

import { Loader2, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useSyncExternalStore } from "react";
import { Badge } from "@/components/ui/Badge";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { Numeral } from "@/components/ui/Numeral";
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

/** Compact ledger timestamp: "now" / "12m" / "3h" / "5d". Mono-rendered by the caller. */
function relTime(at: number): string {
  const s = Math.max(0, Math.floor((Date.now() - at) / 1000));
  if (s < 60) return "now";
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}

/** Right-edge status reading for a ledger row: live state or the "New" cue for unopened results. */
function StatusCell({
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
        <Badge tone="accent" dot>
          New · {clips}
        </Badge>
      );
    }
    return (
      <Badge tone="ok" dot>
        {clips}
      </Badge>
    );
  }
  if (status === "failed") {
    return (
      <Badge tone="bad" dot>
        Failed
      </Badge>
    );
  }
  if (status === "cancelled") {
    return (
      <Badge tone="neutral" dot>
        Stopped
      </Badge>
    );
  }
  // processing (or unknown-yet) → animated cue
  return (
    <span className="inline-flex shrink-0 items-center gap-1.5 font-mono text-eyebrow uppercase text-muted">
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
    <section className="rounded-lg border border-line bg-surface p-5">
      <Eyebrow tone="muted" as="h2">
        Recent
      </Eyebrow>
      {items.length === 0 ? (
        <p className="mt-3 text-sm leading-relaxed text-muted">
          Projects created on this device appear here.
        </p>
      ) : (
        <ul className="mt-3 -mx-2 divide-y divide-line">
          {items.map((p) => (
            <li key={p.id} className="group relative flex items-center">
              <Link
                href={`/dashboard?job=${p.id}`}
                className="flex min-w-0 flex-1 items-center gap-3 rounded-md px-2 py-2.5 transition-colors hover:bg-surface-2"
              >
                <Numeral className="w-8 shrink-0 text-eyebrow text-faint">{relTime(p.at)}</Numeral>
                <span className="min-w-0 flex-1 truncate text-sm text-muted group-hover:text-ink">
                  {p.label}
                </span>
                <StatusCell status={p.status} nclips={p.nclips} reviewed={p.reviewed} />
              </Link>
              <button
                type="button"
                onClick={() => removeRecentProject(p.id)}
                aria-label="Remove from recent"
                className="ml-0.5 shrink-0 rounded-md p-2 text-faint transition hover:text-ink [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover:opacity-100"
              >
                <X className="size-3.5" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
