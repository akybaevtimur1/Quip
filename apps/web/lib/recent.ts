/** Client-side "recent projects" history backed by localStorage, exposed as an
 *  external store for useSyncExternalStore (lint-clean, hydration-safe, reactive
 *  across tabs and on create). A no-backend stand-in until jobs are user-scoped
 *  in Supabase, where this swaps to a server list.
 *
 *  `status`/`nclips`/`reviewed` (optional, added later — old entries without them
 *  stay valid): let the dashboard show live per-project state (processing / done /
 *  failed) and a "done but not opened yet" indicator without a server jobs list. */
export type RecentProject = {
  id: string;
  label: string;
  at: number;
  /** Last-known job status (cached so a returning user sees it before the poll resolves). */
  status?: JobStatusLite;
  /** Clip count once known (for "Ready · N clips"). */
  nclips?: number;
  /** True once the user has opened this job's done results → drops the "New" badge. */
  reviewed?: boolean;
};

/** Mirror of the worker JobStatus (kept local so recent.ts has no type-contract dep). */
export type JobStatusLite =
  | "queued"
  | "downloading"
  | "transcribing"
  | "selecting"
  | "rendering"
  | "done"
  | "failed"
  | "cancelled";

const TERMINAL: ReadonlySet<JobStatusLite> = new Set(["done", "failed", "cancelled"]);
export function isTerminalStatus(s: JobStatusLite | undefined): boolean {
  return s !== undefined && TERMINAL.has(s);
}

const KEY = "quip:recent-projects";
const MAX = 12;

const listeners = new Set<() => void>();
let snapshot: RecentProject[] = [];
let loaded = false;
// Stable reference for SSR/hydration (useSyncExternalStore caches by identity).
const EMPTY_SNAPSHOT: readonly RecentProject[] = [];

function readStorage(): RecentProject[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as RecentProject[]) : [];
  } catch {
    // Corrupt localStorage shouldn't crash the dashboard — start fresh.
    return [];
  }
}

function refresh(): void {
  snapshot = readStorage();
  loaded = true;
}

function emit(): void {
  refresh();
  for (const l of listeners) l();
}

/** Stable snapshot for useSyncExternalStore (same ref until a mutation). */
export function getRecentSnapshot(): RecentProject[] {
  if (!loaded) refresh();
  return snapshot;
}

export function getRecentServerSnapshot(): RecentProject[] {
  return EMPTY_SNAPSHOT as RecentProject[];
}

export function subscribeRecent(cb: () => void): () => void {
  listeners.add(cb);
  const onStorage = (e: StorageEvent) => {
    if (e.key === KEY) emit();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(cb);
    window.removeEventListener("storage", onStorage);
  };
}

export function addRecentProject(p: RecentProject): void {
  if (typeof window === "undefined") return;
  const list = [p, ...readStorage().filter((x) => x.id !== p.id)].slice(0, MAX);
  window.localStorage.setItem(KEY, JSON.stringify(list));
  emit();
}

export function removeRecentProject(id: string): void {
  if (typeof window === "undefined") return;
  const list = readStorage().filter((x) => x.id !== id);
  window.localStorage.setItem(KEY, JSON.stringify(list));
  emit();
}

/** Merge fields into an existing recent entry (no-op if it isn't tracked). Used to cache
 *  live status/nclips and the reviewed flag. Skips the write (and the re-render) when
 *  nothing actually changed, so polling that returns the same status is free. */
export function updateRecentProject(
  id: string,
  patch: Partial<Omit<RecentProject, "id">>,
): void {
  if (typeof window === "undefined") return;
  const list = readStorage();
  const i = list.findIndex((x) => x.id === id);
  if (i < 0) return;
  const cur = list[i];
  const next = { ...cur, ...patch };
  if (
    next.status === cur.status &&
    next.nclips === cur.nclips &&
    next.reviewed === cur.reviewed &&
    next.label === cur.label
  ) {
    return; // nothing changed → don't churn storage/listeners
  }
  list[i] = next;
  window.localStorage.setItem(KEY, JSON.stringify(list));
  emit();
}

/** Mark a job's results as seen → removes the "New" badge from the recent list. */
export function markReviewed(id: string): void {
  updateRecentProject(id, { reviewed: true });
}
