// ────────────────────────────────────────────────────────────────────────────
// captionFitBrowser — browser glue around the pure `captionFit` math.
//
// Builds the real <canvas> text measurer (using the actual caption font — the same
// TTF family libass renders, so the estimate tracks the real output) and the frame
// geometry from the ASS PlayRes + the user's block width, then asks `fitCaptionSize`
// for the single largest size at which every page fits. A safety margin shrinks the
// usable frame a hair so minor browser-vs-libass metric differences never overflow
// in the final render. Pure math + tests live in `captionFit.ts`.
// ────────────────────────────────────────────────────────────────────────────

import type { CaptionReply, CaptionStyle, Word } from "@/lib/types";
import { captionPageTexts } from "@/components/editor/replyUtils";
import { fitCaptionSize, type Measure } from "./captionFit";

// Mirror services/worker/app/editor/captions_v2._CAPTION_DEFAULT_MARGIN (40/40) — the
// default block width when wrap_width is unset, so the fit matches the legacy render.
const CAPTION_DEFAULT_SIDE_MARGIN = 40;
// Vertical budget for the caption block as a fraction of PlayResY. Keeps a verbose
// page from towering up the frame; the bottom anchor + margin_v place it.
const MAX_HEIGHT_FRAC = 0.42;
// Shrink the usable frame so the (approximate) browser metrics stay conservative vs
// libass — captions land a touch smaller rather than ever spilling out.
const SAFETY = 0.92;
// Matches the caption line-height used in the CSS overlay / libass leading.
const LINE_HEIGHT = 1.25;

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

function parsePlayRes(ass: string): { w: number; h: number } {
  const w = Number(/PlayResX:\s*(\d+)/.exec(ass)?.[1]);
  const h = Number(/PlayResY:\s*(\d+)/.exec(ass)?.[1]);
  return { w: w || 1080, h: h || 1920 };
}

/** Quote the font family so canvas measures with the real TTF (libass renders the same). */
const canvasFamily = (font: string) => `'${font}'`;

export interface FitInput {
  replies: CaptionReply[];
  words: Word[];
  /** Current caption style (font/uppercase/wrap_width feed the fit). */
  style: CaptionStyle;
  /** Current compiled ASS — only used to read PlayResX/PlayResY (aspect-correct frame). */
  assText: string;
  /** The size the user is asking for; treated as a CEILING. */
  desiredSize: number;
  minSize: number;
  maxSize: number;
}

/**
 * Compute the largest caption size (≤ desiredSize, ≥ minSize) at which every visible
 * caption page fits the user's frame. Best-effort: returns the clamped desired size if
 * there are no pages or canvas/fonts are unavailable (never throws). Async only to await
 * font loading for accurate metrics.
 */
export async function computeFittedCaptionSize(input: FitInput): Promise<number> {
  const { replies, words, style, assText, desiredSize, minSize, maxSize } = input;
  const ceiling = clamp(Math.round(desiredSize), minSize, maxSize);

  const pages = captionPageTexts(replies, words, style.uppercase ?? true);
  if (pages.length === 0) return ceiling;

  const { w: playW, h: playH } = parsePlayRes(assText);
  const wrapFrac =
    style.wrap_width != null
      ? style.wrap_width
      : (playW - 2 * CAPTION_DEFAULT_SIDE_MARGIN) / playW;
  const frameWidth = wrapFrac * playW * SAFETY;
  const frameHeight = MAX_HEIGHT_FRAC * playH * SAFETY;

  const family = canvasFamily(style.font ?? "Montserrat");
  // Best-effort: ensure the font is loaded so measureText uses its real metrics.
  try {
    await document.fonts?.load(`900 100px ${family}`);
  } catch {
    /* fall back to whatever metrics are available — the safety margin still guards */
  }

  const ctx = document.createElement("canvas").getContext("2d");
  if (!ctx) return ceiling;
  const measure: Measure = (text, size) => {
    ctx.font = `900 ${size}px ${family}`;
    return ctx.measureText(text).width;
  };

  return fitCaptionSize({
    pages,
    maxSize: ceiling,
    minSize,
    frameWidth,
    frameHeight,
    lineHeight: LINE_HEIGHT,
    measure,
  });
}
