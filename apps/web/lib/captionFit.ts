// ────────────────────────────────────────────────────────────────────────────
// captionFit — pure auto-fit for burned-in captions.
//
// The render path (services/worker/app/editor/captions_v2.compile_ass) writes the
// caption font size LITERALLY (`Style: Default,…,{size},…`) and turns the block
// width into symmetric MarginL/MarginR — it does NOT auto-fit. So a caption page
// with many/long words renders at the SAME fixed size as a short one and spills
// out of the frame the user drew.
//
// This module computes ONE stable size for the whole clip = the largest size at
// which EVERY caption page fits the frame (no line wider than the frame width, no
// page taller than the frame height). The user's chosen size is treated as a
// CEILING; the frame width is the real control (wider frame ⇒ bigger text allowed,
// narrow frame ⇒ text shrinks). The result is written into `style.size`, so all
// three render surfaces (CSS overlay, libass preview, ffmpeg export) honour it for
// free — no model/backend change.
//
// Text measurement is INJECTED (`measure(text, size) → px width of a single line`)
// so the wrap/fit math is pure and unit-testable. The browser wires a real <canvas>
// measurer with the actual caption font (see editor integration). All sizes/widths
// share the ASS PlayRes pixel space (Fontsize is in PlayRes px, so a canvas font of
// `${size}px` measures in the same units as `wrap_width * PlayResX`).
// ────────────────────────────────────────────────────────────────────────────

/** Measure the rendered width (px) of a single line of `text` at font `size`. */
export type Measure = (text: string, size: number) => number;

export interface FitParams {
  /** Text of each caption page (already upper-cased iff the style upper-cases). */
  pages: string[];
  /** User's chosen size = the MAXIMUM (ceiling), in ASS font units. */
  maxSize: number;
  /** Floor so text never becomes unreadably tiny. */
  minSize: number;
  /** Frame width (px, ASS PlayRes space). Lines must not exceed this. */
  frameWidth: number;
  /** Max block height (px, ASS PlayRes space). A page's wrapped block must fit. */
  frameHeight: number;
  /** Line-height multiple (matches CSS/libass leading, ~1.2–1.25). */
  lineHeight: number;
  /** Single-line width measurer (no wrapping). */
  measure: Measure;
}

/**
 * Greedy word-wrap `text` to `maxWidth` at font `size`, mirroring libass WrapStyle 0
 * (greedy, no hyphenation). Internal whitespace is collapsed; blank input yields `[]`.
 * A single word wider than `maxWidth` occupies its own (overflowing) line — there is
 * nowhere to break it, exactly like the renderer.
 */
export function wrapGreedy(
  text: string,
  size: number,
  maxWidth: number,
  measure: Measure,
): string[] {
  const words = text.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return [];
  const lines: string[] = [];
  let line = words[0];
  for (let i = 1; i < words.length; i++) {
    const candidate = `${line} ${words[i]}`;
    if (measure(candidate, size) <= maxWidth) {
      line = candidate;
    } else {
      lines.push(line);
      line = words[i];
    }
  }
  lines.push(line);
  return lines;
}

/** Does a single page fit the frame at `size`? width: no wrapped line exceeds the
 *  frame; height: lines × size × lineHeight ≤ frameHeight. */
function pageFits(
  text: string,
  size: number,
  frameWidth: number,
  frameHeight: number,
  lineHeight: number,
  measure: Measure,
): boolean {
  const lines = wrapGreedy(text, size, frameWidth, measure);
  if (lines.length === 0) return true; // blank page constrains nothing
  for (const line of lines) {
    if (measure(line, size) > frameWidth) return false; // an over-wide (unbreakable) line
  }
  return lines.length * size * lineHeight <= frameHeight;
}

/**
 * Largest INTEGER size in [minSize, maxSize] at which EVERY page fits the frame.
 * Falls back to `minSize` when even that can't fit (better a readable floor than
 * an overflow). Linear scan from the ceiling down — the search space is tiny
 * (≤ ~100 steps) and this makes no monotonicity assumption about wrapping.
 */
export function fitCaptionSize(params: FitParams): number {
  const { pages, maxSize, minSize, frameWidth, frameHeight, lineHeight, measure } = params;
  const lo = Math.round(Math.min(minSize, maxSize));
  const hi = Math.round(Math.max(minSize, maxSize));
  const texts = pages.map((p) => p.trim()).filter(Boolean);
  if (texts.length === 0) return hi;
  for (let size = hi; size > lo; size--) {
    if (texts.every((t) => pageFits(t, size, frameWidth, frameHeight, lineHeight, measure))) {
      return size;
    }
  }
  return lo;
}
