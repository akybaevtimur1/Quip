"use client";

import { User } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { SignOutButton } from "@/components/auth/SignOutButton";
import { Logo } from "@/components/ui/Logo";
import { createSupabaseBrowserClient } from "@/lib/supabase/client";
import { isSupabaseConfigured } from "@/lib/supabase/config";

/** App shell header for the logged-in area. Shows plan + account. Email is read
 *  client-side from Supabase when configured; dev mode shows no account. */
export function AppHeader() {
  const [email, setEmail] = useState<string | null>(null);

  useEffect(() => {
    if (!isSupabaseConfigured) return;
    createSupabaseBrowserClient()
      .auth.getUser()
      .then(({ data }) => setEmail(data.user?.email ?? null))
      .catch(() => setEmail(null));
  }, []);

  return (
    <header className="sticky top-0 z-40 border-b border-line bg-bg/80 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-[1200px] items-center justify-between px-5 sm:px-8">
        <Logo href="/dashboard" />
        <div className="flex items-center gap-2.5">
          <Link
            href="/#pricing"
            className="hidden rounded-pill border border-line px-3 py-1.5 font-mono text-eyebrow uppercase text-muted transition-colors hover:text-ink sm:inline-flex"
          >
            Free
          </Link>
          <details className="group relative">
            <summary className="flex size-9 cursor-pointer list-none items-center justify-center rounded-full border border-line bg-surface-2 text-sm font-semibold text-ink [&::-webkit-details-marker]:hidden">
              {email ? email[0]?.toUpperCase() : <User className="size-4 text-muted" aria-hidden />}
            </summary>
            <div className="absolute right-0 top-11 w-60 rounded-lg border border-line bg-surface p-2 shadow-[0_24px_60px_-28px_rgba(0,0,0,.9)]">
              {email && (
                <p className="truncate border-b border-line px-3 pb-2.5 pt-1.5 text-xs text-faint">
                  {email}
                </p>
              )}
              <Link
                href="/#pricing"
                className="mt-1 block rounded-md px-3 py-2 text-sm text-muted transition-colors hover:bg-surface-2 hover:text-ink"
              >
                Pricing
              </Link>
              <div className="px-3 py-2">
                {isSupabaseConfigured ? (
                  <SignOutButton />
                ) : (
                  <span className="text-xs text-faint">Dev mode (no account)</span>
                )}
              </div>
            </div>
          </details>
        </div>
      </div>
    </header>
  );
}
