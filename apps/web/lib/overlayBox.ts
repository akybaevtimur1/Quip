// ────────────────────────────────────────────────────────────────────────────
// overlayBox — helpers for the CapCut-style manipulation box (OverlaySelectionBox).
//
// The selection box is now driven by libass's OWN rendered rectangle (the bbox the
// libass-wasm worker computes every frame and posts to the main thread), NOT by a
// DOM "text-mirror". A DOM layout engine can't reproduce libass's box model
// (BorderStyle=3 plaque padding, leading, balanced WrapStyle=0), so the old mirror
// mis-sized/mis-positioned the box. We now read the real rect instead.
//
// Hook (\an8, top-anchored) and caption (\an2, bottom-anchored) are rendered as TWO
// separate libass instances (one ASS each) so each instance's fused blend rect is the
// EXACT bbox of just that element — no fragile partitioning of a unioned rect. This
// module splits the combined server ASS into a hook-only and a caption-only ASS by the
// Dialogue line's Style field (`Hook` vs everything else), and converts a device-px
// rect on the canvas into render-box fractions for the box.
// ────────────────────────────────────────────────────────────────────────────

/** A box position/size as fractions [0..1] of the render box (CapCut selection box). */
export interface OverlayRect {
  topPct: number;
  leftPct: number;
  widthPct: number;
  heightPct: number;
}

/** The pair of rects surfaced per frame (either may be null when nothing is drawn). */
export interface SubRects {
  hook: OverlayRect | null;
  caption: OverlayRect | null;
}

/**
 * Convert a device-px rectangle on the libass canvas into render-box fractions.
 * The canvas is `absolute inset-0 size-full`, 1:1 with the ASS grid (no letterbox at
 * 9:16) and DPR-scaled, so the fraction is simply the rect coordinate over the canvas
 * pixel size. Returns null for a degenerate (empty) rect or canvas.
 */
export function rectToFractions(
  rect: { x: number; y: number; w: number; h: number },
  canvasW: number,
  canvasH: number,
): OverlayRect | null {
  if (canvasW <= 0 || canvasH <= 0 || rect.w <= 0 || rect.h <= 0) return null;
  return {
    topPct: (rect.y / canvasH) * 100,
    leftPct: (rect.x / canvasW) * 100,
    widthPct: (rect.w / canvasW) * 100,
    heightPct: (rect.h / canvasH) * 100,
  };
}

/** The ASS Style name used for the hook event (services/worker/app/editor/captions_v2.py). */
const HOOK_STYLE = "Hook";

/**
 * Split a combined ASS (hook + captions) into a hook-only and a caption-only ASS.
 *
 * Script-info + ALL Style definitions are kept in BOTH outputs (so each renders with the
 * correct styles); only the `[Events]` Dialogue lines are partitioned by their Style field
 * (the 4th comma-separated field): `Hook` → hook ASS, anything else → caption ASS. A part
 * with no Dialogue lines of its kind yields `null` (so we don't spin up a libass instance
 * for an empty track — libass #166 doesn't render an empty track anyway).
 */
export function splitHookCaptionAss(ass: string): { hook: string | null; caption: string | null } {
  if (!ass.trim()) return { hook: null, caption: null };
  const lines = ass.split(/\r?\n/);
  const hookLines: string[] = [];
  const captionLines: string[] = [];
  let hasHookEvent = false;
  let hasCaptionEvent = false;

  for (const line of lines) {
    if (line.startsWith("Dialogue:")) {
      // ASS Dialogue format: "Dialogue: Layer,Start,End,Style,Name,...". Style = field 3 (0-based).
      const style = line.slice("Dialogue:".length).split(",")[3]?.trim();
      if (style === HOOK_STYLE) {
        hookLines.push(line);
        hasHookEvent = true;
      } else {
        captionLines.push(line);
        hasCaptionEvent = true;
      }
    } else {
      // Headers, [Script Info], all Style: lines, [Events] / Format: — shared by both.
      hookLines.push(line);
      captionLines.push(line);
    }
  }

  return {
    hook: hasHookEvent ? hookLines.join("\n") : null,
    caption: hasCaptionEvent ? captionLines.join("\n") : null,
  };
}
