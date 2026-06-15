"use client";

import { User } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { SignOutButton } from "@/components/auth/SignOutButton";
import { UsagePill } from "@/components/app/UsagePill";
import { Logo } from "@/components/ui/Logo";
import { createSupabaseBrowserClient } from "@/lib/supabase/client";
import { isSupabaseConfigured } from "@/lib/supabase/config";

/** App shell header for the logged-in area. Shows plan + account. Email is read
 *  client-side from Supabase when configured; dev mode shows no account. */
export function AppHeader() {
  const [email, setEmail] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isSupabaseConfigured) return;
    createSupabaseBrowserClient()
      .auth.getUser()
      .then(({ data }) => setEmail(data.user?.email ?? null))
      .catch(() => setEmail(null));
  }, []);

  // Light-dismiss (same pattern as ExportMenu): close on a click/tap outside the
  // menu or on Escape. The old native <details> only toggled via its own summary,
  // so the panel stayed open until you clicked the avatar again — clicking anywhere
  // else did nothing, which is what made it feel stuck.
  useEffect(() => {
    if (!menuOpen) return;
    const onPointerDown = (e: PointerEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenuOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [menuOpen]);

  return (
    <header className="sticky top-0 z-40 border-b border-line bg-bg/80 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-[1200px] items-center justify-between px-5 sm:px-8">
        <Logo href="/dashboard" />
        <div className="flex items-center gap-2.5">
          {/* always-visible balance: videos + minutes left this month */}
          <UsagePill className="hidden sm:inline-flex" />
          <div className="relative" ref={menuRef}>
            <button
              type="button"
              onClick={() => setMenuOpen((v) => !v)}
              aria-haspopup="menu"
              aria-expanded={menuOpen}
              aria-label="Account menu"
              className="flex size-9 cursor-pointer items-center justify-center rounded-full border border-line bg-surface-2 text-sm font-semibold text-ink transition-colors hover:border-line-strong"
            >
              {email ? email[0]?.toUpperCase() : <User className="size-4 text-muted" aria-hidden />}
            </button>
            {menuOpen && (
              <div
                role="menu"
                className="absolute right-0 top-11 w-60 rounded-lg border border-line bg-surface p-2 shadow-[0_24px_60px_-28px_rgba(0,0,0,.9)]"
              >
                {email && (
                  <p className="truncate border-b border-line px-3 pb-2.5 pt-1.5 text-xs text-faint">
                    {email}
                  </p>
                )}
                <Link
                  href="/account"
                  role="menuitem"
                  onClick={() => setMenuOpen(false)}
                  className="mt-1 block rounded-md px-3 py-2 text-sm text-muted transition-colors hover:bg-surface-2 hover:text-ink"
                >
                  Account &amp; subscription
                </Link>
                <Link
                  href="/#pricing"
                  role="menuitem"
                  onClick={() => setMenuOpen(false)}
                  className="block rounded-md px-3 py-2 text-sm text-muted transition-colors hover:bg-surface-2 hover:text-ink"
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
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
