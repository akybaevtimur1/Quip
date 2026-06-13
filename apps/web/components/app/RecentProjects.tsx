"use client";

import { Clock, X } from "lucide-react";
import Link from "next/link";
import { useSyncExternalStore } from "react";
import {
  getRecentServerSnapshot,
  getRecentSnapshot,
  removeRecentProject,
  subscribeRecent,
} from "@/lib/recent";

export function RecentProjects() {
  const items = useSyncExternalStore(subscribeRecent, getRecentSnapshot, getRecentServerSnapshot);

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
                <span className="truncate">{p.label}</span>
              </Link>
              <button
                type="button"
                onClick={() => removeRecentProject(p.id)}
                aria-label="Remove from recent"
                className="shrink-0 rounded-md p-1.5 text-faint opacity-0 transition hover:text-ink group-hover:opacity-100"
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
