import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import { cache } from "react";
import { SUPABASE_ANON_KEY, SUPABASE_URL, isSupabaseConfigured } from "./config";

/** Server Supabase client (Server Components / Route Handlers / Server Actions).
 *  `cookies()` is async in Next 16. Use only when isSupabaseConfigured. */
export async function createSupabaseServerClient() {
  const cookieStore = await cookies();
  return createServerClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet) {
        try {
          for (const { name, value, options } of cookiesToSet) {
            cookieStore.set(name, value, options);
          }
        } catch {
          // Official @supabase/ssr pattern: a Server Component cannot set cookies.
          // Not a swallowed failure — the proxy refreshes the session on the next request.
        }
      },
    },
  });
}

/** Optional auth check for public (marketing) surfaces: returns the user or null.
 *  Dual-mode safe — returns null WITHOUT touching cookies() when Supabase isn't
 *  configured, so the marketing page stays static until auth is live. `cache()`
 *  dedupes to a single auth check per request even when several components call it. */
export const getOptionalUser = cache(async () => {
  if (!isSupabaseConfigured) return null;
  const supabase = await createSupabaseServerClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  return user;
});
