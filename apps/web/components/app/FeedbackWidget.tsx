"use client";

import { MessageSquarePlus, X } from "lucide-react";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import { siteConfig } from "@/lib/site";
import { createSupabaseBrowserClient } from "@/lib/supabase/client";
import { isSupabaseConfigured } from "@/lib/supabase/config";

type Status = "idle" | "sending" | "done" | "error";

/** Floating "Feedback" button + modal, mounted site-wide. Writes to the Supabase `feedback`
 *  table (insert-only RLS) so it reaches the founder; falls back to a mailto when Supabase
 *  isn't configured (dev). Hidden on the editor route so it never floats over its controls.
 *
 *  Motion: the dialog mounts, then animates in (backdrop fade + panel rise/scale on desktop,
 *  slide-up sheet on mobile); on close it animates out before unmounting. Focus is trapped
 *  inside the dialog and returned to the FAB on close. prefers-reduced-motion is honored by
 *  the global rule that clamps transition-duration to ~0. */
export function FeedbackWidget() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [shown, setShown] = useState(false); // drives the enter/exit transition
  const [message, setMessage] = useState("");
  const [status, setStatus] = useState<Status>("idle");

  const panelRef = useRef<HTMLDivElement>(null);
  const fabRef = useRef<HTMLButtonElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const doneCloseRef = useRef<HTMLButtonElement>(null);

  const close = useCallback(() => {
    setShown(false); // play the exit transition; unmount happens on transitionEnd
  }, []);

  // After the exit transition, unmount the dialog, reset state, restore focus to the FAB.
  // Guard on the event target/property: child controls have their own `transition-colors`
  // (hover) whose transitionend bubbles up — only the panel's own transform/opacity exit
  // should trigger the unmount, never a button hover mid-close.
  function onPanelTransitionEnd(e: React.TransitionEvent<HTMLDivElement>) {
    if (shown) return;
    if (e.target !== e.currentTarget) return;
    if (e.propertyName !== "opacity" && e.propertyName !== "transform") return;
    setOpen(false);
    setStatus("idle");
    setMessage("");
    fabRef.current?.focus();
  }

  // Mount → next frame → animate in. Also focus the field once it's in.
  useEffect(() => {
    if (!open) return;
    const raf = requestAnimationFrame(() => setShown(true));
    return () => cancelAnimationFrame(raf);
  }, [open]);

  // When the form swaps to the success view, the Send button it was on unmounts —
  // pull focus to the success Close button so focus never falls out of the dialog.
  useEffect(() => {
    if (status === "done") doneCloseRef.current?.focus();
  }, [status]);

  // Escape to close + a minimal focus trap (Tab cycles within the dialog).
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        close();
        return;
      }
      if (e.key !== "Tab") return;
      const panel = panelRef.current;
      if (!panel) return;
      const focusable = panel.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), textarea, input, [tabindex]:not([tabindex="-1"])',
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (e.shiftKey && active === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, close]);

  // The editor has its own bottom controls — don't float over them there.
  if (pathname?.startsWith("/edit/")) return null;

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
      {/* FAB — swaps out (fade + shrink) while the dialog is mounted. */}
      <button
        ref={fabRef}
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Send feedback"
        aria-hidden={open || undefined}
        tabIndex={open ? -1 : undefined}
        className={cn(
          "fixed bottom-5 right-5 z-40 inline-flex items-center gap-2 rounded-full border border-line bg-surface px-4 py-2.5 text-sm font-medium text-ink shadow-[0_16px_40px_-20px_rgba(0,0,0,.85)] transition duration-150 ease-snappy hover:border-line-strong hover:-translate-y-px",
          open && "pointer-events-none scale-95 opacity-0",
        )}
      >
        <MessageSquarePlus className="size-4 text-muted" aria-hidden />
        Feedback
      </button>

      {open && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Send feedback"
          onClick={close}
          className={cn(
            "fixed inset-0 z-50 flex items-end justify-center bg-black/50 p-4 backdrop-blur-sm transition-opacity duration-150 ease-snappy sm:items-center",
            shown ? "opacity-100" : "opacity-0",
          )}
        >
          <div
            ref={panelRef}
            onClick={(e) => e.stopPropagation()}
            onTransitionEnd={onPanelTransitionEnd}
            className={cn(
              "max-h-[calc(100dvh-2rem)] w-full max-w-md overflow-y-auto rounded-lg border border-line bg-surface p-5 shadow-[0_24px_80px_-24px_rgba(0,0,0,.9)] transition duration-150 ease-snappy",
              // mobile = slide-up sheet; sm+ = rise + scale
              shown
                ? "translate-y-0 scale-100 opacity-100"
                : "translate-y-6 opacity-0 sm:translate-y-2 sm:scale-95",
            )}
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
                  ref={doneCloseRef}
                  type="button"
                  onClick={close}
                  className="mt-4 rounded-md border border-line px-3.5 py-2 text-sm text-muted transition hover:border-line-strong hover:text-ink"
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
                  ref={textareaRef}
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  autoFocus
                  rows={5}
                  maxLength={5000}
                  placeholder="What’s on your mind?"
                  className="mt-3 w-full resize-y rounded-lg border border-line bg-surface-2 px-3 py-2.5 text-sm text-ink outline-none transition-colors placeholder:text-faint focus:border-line-strong"
                />
                {status === "error" && (
                  <p role="alert" className="mt-2 text-sm text-bad">
                    Couldn’t send — email us at{" "}
                    <a
                      href={`mailto:${siteConfig.supportEmail}`}
                      className="font-medium text-bad underline decoration-bad/40 underline-offset-2 transition-colors hover:decoration-bad"
                    >
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
