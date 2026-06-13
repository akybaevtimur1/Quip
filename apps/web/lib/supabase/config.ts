/**
 * Supabase env resolution + dual-mode flag.
 *
 * The founder connects a real Supabase project later (sub not paid yet), so every
 * auth path must degrade gracefully: when these env vars are absent the app runs
 * "open" (dev), and gating/quotas activate automatically once they're set.
 *
 * Key name: prefer the checklist's NEXT_PUBLIC_SUPABASE_ANON_KEY (docs/SUPABASE_SETUP.md);
 * fall back to the newer NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY name. Never the service_role.
 */
export const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";

export const SUPABASE_ANON_KEY =
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ??
  process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ??
  "";

/** True only when both URL and a public key are present → real auth is active. */
export const isSupabaseConfigured = Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);
