"use client";

import { MessageSquarePlus, X } from "lucide-react";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { siteConfig } from "@/lib/site";
import { Button } from "@/components/ui/Button";
import { createSupabaseBrowserClient } from "@/lib/supabase/client";
import { isSupabaseConfigured } from "@/lib/supabase/config";

type Status = "idle" | "sending" | "done" | "error";

/** Floating "Feedback" button + modal, mounted site-wide. Writes to the Supabase `feedback`
 *  table (insert-only RLS) so it reaches the founder; falls back to a mailto when Supabase
 *  isn't configured (dev). Hidden on the editor route so it never floats over its controls. */
export function FeedbackWidget() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [status, setStatus] = useState<Status>("idle");

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  // The editor has its own bottom controls — don't float over them there.
  if (pathname?.startsWith("/edit/")) return null;

  function close() {
    setOpen(false);
    // reset after the close so the success/error state doesn't flash on reopen
    setTimeout(() => {
      setStatus("idle");
      setMessage("");
    }, 200);
  }

  async function submit() {
    const text = message.trim();
    if (!text || status === "sending") return;
    setStatus("sending");
    try {
      if (isSupabaseConfigured) {
        const supabase = createSupabaseBrowserClient();
        const { data } = await supabase.auth.getUser();
        const { error } = await supabase.from("feedback").insert({
          message: text,
          email: data.user?.email ?? null,
          user_id: data.user?.id ?? null,
          path: pathname ?? null,
        });
        if (error) throw error;
      } else {
        window.location.href = `mailto:${siteConfig.supportEmail}?subject=${encodeURIComponent(
          "Quip feedback",
        )}&body=${encodeURIComponent(text)}`;
      }
      setStatus("done");
    } catch {
      setStatus("error");
    }
  }

  return (
    <>
      {!open && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-label="Send feedback"
          className="fixed bottom-5 right-5 z-40 inline-flex items-center gap-2 rounded-full border border-line bg-surface px-4 py-2.5 text-sm font-medium text-ink shadow-[0_16px_40px_-20px_rgba(0,0,0,.85)] transition-colors hover:border-line-strong"
        >
          <MessageSquarePlus className="size-4 text-accent" aria-hidden />
          Feedback
        </button>
      )}

      {open && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Send feedback"
          onClick={close}
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 p-4 backdrop-blur-sm sm:items-center"
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-md max-h-[calc(100dvh-2rem)] overflow-y-auto rounded-xl border border-line bg-surface p-5 shadow-[0_24px_80px_-24px_rgba(0,0,0,.9)]"
          >
            <div className="flex items-center justify-between">
              <h2 className="font-display text-lg font-semibold text-ink">Send feedback</h2>
              <button
                type="button"
                onClick={close}
                aria-label="Close"
                className="grid size-8 place-items-center rounded-md text-muted transition-colors hover:bg-surface-2 hover:text-ink"
              >
                <X className="size-4" aria-hidden />
              </button>
            </div>

            {status === "done" ? (
              <div className="py-6 text-center">
                <p className="text-sm text-ink">Thanks — we read every message.</p>
                <button
                  type="button"
                  onClick={close}
                  className="mt-4 rounded-md border border-line px-3.5 py-2 text-sm text-muted transition hover:text-ink"
                >
                  Close
                </button>
              </div>
            ) : (
              <>
                <p className="mt-1 text-sm text-muted">
                  Bugs, ideas, anything — it goes straight to the founder.
                </p>
                <textarea
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  autoFocus
                  rows={5}
                  maxLength={5000}
                  placeholder="What’s on your mind?"
                  className="mt-3 w-full resize-y rounded-lg border border-line bg-surface-2 px-3 py-2.5 text-sm text-ink outline-none transition-colors placeholder:text-faint focus:border-line-strong"
                />
                {status === "error" && (
                  <p className="mt-2 text-sm text-bad">
                    Couldn’t send — email us at{" "}
                    <a href={`mailto:${siteConfig.supportEmail}`} className="text-accent hover:underline">
                      {siteConfig.supportEmail}
                    </a>
                    .
                  </p>
                )}
                <div className="mt-4 flex justify-end gap-2">
                  <Button variant="ghost" size="sm" onClick={close}>
                    Cancel
                  </Button>
                  <Button
                    variant="accent"
                    size="sm"
                    onClick={submit}
                    loading={status === "sending"}
                    disabled={!message.trim()}
                  >
                    Send
                  </Button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
}
