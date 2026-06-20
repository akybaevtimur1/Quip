"use client";

import { X } from "lucide-react";
import type React from "react";
import type { Tab } from "./EditorRail";

// ────────────────────────────────────────────────────────────────────────────
// Inspector — the right contextual panel of the Fixed-Studio shell. Fixed width
// (--inspector-w). Outer overflow-hidden + inner min-h-0 overflow-y-auto so its
// content height can NEVER expand the row (Task 1 invariant). Keeps the live-vs-
// render banner at the top. On narrow viewports (`overlay`) it renders as an
// absolutely-positioned right sheet over the canvas gutter with a backdrop and a
// close button — the canvas behind it does NOT resize.
// ────────────────────────────────────────────────────────────────────────────

function LiveBanner() {
  return (
    <p className="shrink-0 rounded-lg border border-line bg-surface-2 px-3 py-2 text-[11px] leading-snug text-muted">
      <span className="font-semibold text-accent">Preview is live</span> — edits show instantly.{" "}
      <span className="font-semibold text-ink">“Render”</span> writes them to the downloadable file.
    </p>
  );
}

export function Inspector({
  active,
  children,
  overlay = false,
  onClose,
}: {
  active: Tab;
  children: React.ReactNode;
  /** Narrow viewport → render as a right sheet over the canvas (no canvas resize). */
  overlay?: boolean;
  onClose?: () => void;
}) {
  const panel = (
    <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden" data-tab={active}>
      <LiveBanner />
      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto rounded-xl border border-line bg-surface p-4">
        {children}
      </div>
    </div>
  );

  if (overlay) {
    return (
      <div className="absolute inset-0 z-40 flex justify-end">
        {/* backdrop — click to close; does not affect canvas layout (absolute over it) */}
        <button
          type="button"
          aria-label="Close panel"
          onClick={onClose}
          className="absolute inset-0 bg-black/40 backdrop-blur-sm"
        />
        <div className="relative flex w-[min(var(--inspector-w),85vw)] flex-col gap-3 border-l border-line bg-bg p-3 shadow-2xl">
          <button
            type="button"
            onClick={onClose}
            aria-label="Close panel"
            className="absolute right-3 top-3 z-10 rounded-lg p-1 text-muted transition hover:bg-surface-2 hover:text-ink"
          >
            <X className="size-4" />
          </button>
          {panel}
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 w-[var(--inspector-w)] flex-col overflow-hidden">{panel}</div>
  );
}
