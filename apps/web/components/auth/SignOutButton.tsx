"use client";

import { LogOut } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { createSupabaseBrowserClient } from "@/lib/supabase/client";
import { cn } from "@/lib/cn";

export function SignOutButton({ className }: { className?: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function signOut() {
    setBusy(true);
    try {
      await createSupabaseBrowserClient().auth.signOut();
      router.replace("/");
      router.refresh();
    } catch {
      // Network hiccup while clearing the session — re-enable so the user can retry
      // instead of being stuck on a permanently-disabled button.
      setBusy(false);
    }
  }

  return (
    <button
      type="button"
      onClick={signOut}
      disabled={busy}
      className={cn(
        "inline-flex items-center gap-2 text-sm text-muted transition-colors hover:text-ink disabled:opacity-50",
        className,
      )}
    >
      <LogOut className="size-4" aria-hidden />
      Sign out
    </button>
  );
}
