import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import { SUPABASE_ANON_KEY, SUPABASE_URL } from "./config";

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
