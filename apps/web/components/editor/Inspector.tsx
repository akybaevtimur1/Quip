"use client";

import { Maximize2, Minimize2, X } from "lucide-react";
import type React from "react";
import type { Tab } from "./EditorRail";

// ────────────────────────────────────────────────────────────────────────────
// Inspector — the right contextual panel of the Fixed-Studio shell. Fixed width
// (--inspector-w). Outer overflow-hidden + inner min-h-0 overflow-y-auto so its
// content height can NEVER expand the row (Task 1 invariant). Keeps the live-vs-
// render banner at the top.
//   • `overlay`  — narrow viewports: a right sheet over the canvas gutter (backdrop
//     + close X). The canvas behind it does NOT resize.
//   • `expanded` — desktop: the panel breaks out of its grid column into a WIDE,
//     translucent (backdrop-blur) absolute overlay over the video, so you can see
//     the whole picture while tuning settings. The grid column still reserves its
//     width → the canvas does NOT resize/jump (invariant preserved).
// ────────────────────────────────────────────────────────────────────────────

const TAB_TITLE: Record<Tab, string> = {
  agent: "Agent",
  subtitles: "Subtitles",
  hook: "Hook",
  frame: "Frame",
};

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
  expanded = false,
  onToggleExpand,
}: {
  active: Tab;
  children: React.ReactNode;
  /** Narrow viewport → render as a right sheet over the canvas (no canvas resize). */
  overlay?: boolean;
  onClose?: () => void;
  /** Desktop: expand into a wide translucent overlay over the video (no canvas resize). */
  expanded?: boolean;
  onToggleExpand?: () => void;
}) {
  const panel = (
    <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden" data-tab={active}>
      {onToggleExpand && (
        <div className="flex shrink-0 items-center justify-between gap-2">
          <span className="text-xs font-semibold text-ink">{TAB_TITLE[active]}</span>
          <button
            type="button"
            onClick={onToggleExpand}
            title={expanded ? "Collapse panel" : "Expand panel over the video"}
            aria-label={expanded ? "Collapse panel" : "Expand panel over the video"}
            className="rounded-lg border border-line p-1.5 text-muted transition hover:bg-surface-2 hover:text-ink"
          >
            {expanded ? <Minimize2 className="size-3.5" /> : <Maximize2 className="size-3.5" />}
          </button>
        </div>
      )}
      <LiveBanner />
      <div
        className={`flex min-h-0 flex-1 flex-col overflow-y-auto rounded-xl border border-line p-4 ${
          expanded ? "bg-surface/80 backdrop-blur-xl" : "bg-surface"
        }`}
      >
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

  // Desktop EXPANDED → wide translucent overlay over the video. Absolute relative to <main>
  // (position:relative): the grid column still reserves --inspector-w, so the canvas to its
  // left keeps its size — only the panel floats over the right part of the video.
  if (expanded) {
    return (
      <div className="absolute inset-y-3 right-3 z-40 flex w-[min(620px,60vw)] flex-col overflow-hidden rounded-2xl border border-line bg-bg/55 p-3 shadow-2xl backdrop-blur-xl">
        {panel}
      </div>
    );
  }

  return (
    <div className="flex min-h-0 w-[var(--inspector-w)] flex-col overflow-hidden">{panel}</div>
  );
}
