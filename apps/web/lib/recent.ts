/** Client-side "recent projects" history backed by localStorage, exposed as an
 *  external store for useSyncExternalStore (lint-clean, hydration-safe, reactive
 *  across tabs and on create). A no-backend stand-in until jobs are user-scoped
 *  in Supabase, where this swaps to a server list. */
export type RecentProject = { id: string; label: string; at: number };

const KEY = "quip:recent-projects";
const MAX = 12;

const listeners = new Set<() => void>();
let snapshot: RecentProject[] = [];
let loaded = false;

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
  return [];
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
