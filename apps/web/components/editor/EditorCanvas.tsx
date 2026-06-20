"use client";

import type React from "react";

// ────────────────────────────────────────────────────────────────────────────
// EditorCanvas — the stable-sizing center zone of the Fixed-Studio shell. Its
// main area derives height from the row (flex-1 min-h-0), so the video box NEVER
// resizes when sibling panels change (Task 1 invariant). `children` is the
// PreviewPlayer subtree (kept in ClipEditorScreen so all state stays put).
// FitTimeline was moved into the Frame inspector (Task 10) so the canvas column
// has NO conditional slot at all — height is identical on every tab.
// ────────────────────────────────────────────────────────────────────────────

export function EditorCanvas({
  children,
  aspectClass,
}: {
  children: React.ReactNode;
  /** Aspect class of the video inside `children`; surfaced for layout/debug. */
  aspectClass: string;
}) {
  return (
    <div className="flex min-h-0 flex-col" data-aspect={aspectClass}>
      <div className="grid min-h-0 flex-1 place-items-center">
        <div className="flex h-[44vh] max-h-full w-full items-center justify-center lg:h-auto lg:min-h-0 lg:flex-1 lg:self-stretch">
          {children}
        </div>
      </div>
    </div>
  );
}
