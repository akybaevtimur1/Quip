/**
 * Classify a job-polling error: is it a transient CONNECTIVITY blip (the job is still
 * alive server-side, so reconnect) or a REAL failure (surface it)?
 *
 * PURE — `online` is passed in (read from `navigator.onLine` at the call site) so this stays
 * unit-testable without a browser. Treated as connectivity:
 *   - the browser reports offline (`!online`) — definitionally a network problem, whatever threw;
 *   - `TypeError` — what `fetch()` rejects with on a network failure ("Failed to fetch": DNS,
 *     dropped connection, no route) — the classic "their internet died" signal;
 *   - `AbortError` / `TimeoutError` — our 15s `fetchWithTimeout` cap firing on a stalled request
 *     (worker reachable-but-silent, or a crawling connection).
 *
 * Anything else (e.g. `getJob` throwing `Error("getJob failed: 500")` for a non-OK HTTP response)
 * is a genuine error and must NOT be hidden behind the reconnect banner.
 */
export function isConnectivityError(err: unknown, online: boolean): boolean {
  if (!online) return true;
  const name =
    err instanceof Error
      ? err.name
      : typeof err === "object" && err !== null && typeof (err as { name?: unknown }).name === "string"
        ? (err as { name: string }).name
        : "";
  return name === "TypeError" || name === "AbortError" || name === "TimeoutError";
}
