/**
 * Server-only Polar REST helper for the subscription routes (/api/subscription*).
 * Reads POLAR_ACCESS_TOKEN (a SERVER env var, not NEXT_PUBLIC) — never import this from a
 * client component. Dual-mode: when the token is absent the routes report "not configured".
 */
const POLAR_BASE =
  process.env.POLAR_SERVER === "sandbox" ? "https://sandbox-api.polar.sh" : "https://api.polar.sh";

export function polarConfigured(): boolean {
  return Boolean(process.env.POLAR_ACCESS_TOKEN);
}

export function polarFetch(path: string, init?: RequestInit): Promise<Response> {
  return fetch(`${POLAR_BASE}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${process.env.POLAR_ACCESS_TOKEN ?? ""}`,
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
}
