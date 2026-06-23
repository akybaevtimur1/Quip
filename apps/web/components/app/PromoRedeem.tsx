"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { createSupabaseBrowserClient } from "@/lib/supabase/client";
import { isSupabaseConfigured } from "@/lib/supabase/config";

type Status = "idle" | "sending" | "ok" | "error";

const FRIENDLY: Record<string, string> = {
  invalid_code: "That code isn’t valid.",
  already_redeemed: "You’ve already redeemed this code.",
  code_used_up: "This code has reached its limit.",
  not_authenticated: "Please sign in first.",
};

type RedeemResult = { ok: boolean; error?: string; credits?: number; balance?: number };

/** Redeem a promo/invite code → adds non-expiring credits to the signed-in account. Calls the
 *  SECURITY DEFINER `redeem_promo` RPC (credits only the caller, once per code, atomic).
 *  Rendered as the rail's TERTIARY action — a slim disclosure, not a matching card. */
export function PromoRedeem({ className }: { className?: string }) {
  const [code, setCode] = useState("");
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<Status>("idle");
  const [msg, setMsg] = useState("");

  async function redeem() {
    const c = code.trim();
    if (!c || status === "sending") return;
    setMsg("");
    if (!isSupabaseConfigured) {
      setStatus("error");
      setMsg("Promo codes need an account — sign in first.");
      return;
    }
    setStatus("sending");
    try {
      const supabase = createSupabaseBrowserClient();
      const { data, error } = await supabase.rpc("redeem_promo", { p_code: c });
      if (error) throw error;
      const r = data as RedeemResult;
      if (r.ok) {
        setStatus("ok");
        setMsg(
          `+${r.credits} credit${r.credits === 1 ? "" : "s"} added — you now have ${r.balance}.`,
        );
        setCode("");
      } else {
        setStatus("error");
        setMsg(FRIENDLY[r.error ?? ""] ?? "Couldn’t redeem that code.");
      }
    } catch {
      setStatus("error");
      setMsg("Something went wrong — please try again.");
    }
  }

  return (
    <section className={className}>
      {!open ? (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="flex w-full items-center justify-between gap-2 px-1 py-1 text-left transition-colors"
        >
          <Eyebrow tone="faint" as="span">
            Redeem
          </Eyebrow>
          <span className="text-sm text-muted transition-colors hover:text-ink">
            Have a code? →
          </span>
        </button>
      ) : (
        <div className="px-1">
          <Eyebrow tone="faint" as="h2">
            Redeem a code
          </Eyebrow>
          <div className="mt-2.5 flex flex-col gap-2 sm:flex-row">
            <input
              value={code}
              onChange={(e) => setCode(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && redeem()}
              placeholder="Enter code"
              aria-label="Promo code"
              autoFocus
              className="flex-1 rounded-md border border-line bg-surface-2 px-3 py-2.5 text-sm uppercase text-ink outline-none transition-colors placeholder:normal-case placeholder:text-faint focus:border-line-strong"
            />
            <Button
              variant="secondary"
              size="sm"
              onClick={redeem}
              loading={status === "sending"}
              disabled={!code.trim()}
              className="h-11 w-full sm:h-9 sm:w-auto"
            >
              Redeem
            </Button>
          </div>
          {msg && (
            <p className={`mt-2.5 text-sm ${status === "ok" ? "text-ok" : "text-bad"}`}>{msg}</p>
          )}
        </div>
      )}
    </section>
  );
}
