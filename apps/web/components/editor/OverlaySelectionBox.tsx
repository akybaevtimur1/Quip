"use client";

import { useRef } from "react";

// ── OverlaySelectionBox — CapCut-style on-video selection box for hook / captions ──
// Grab the box ANYWHERE to drag the element vertically; grab the corner handle to
// resize the font. There is NO horizontal-position field in the model (text is
// horizontally centered by the ASS renderer), so manipulation is vertical position
// + font size only.
//
// PERF + scale stability (mirrors the existing imperative-drag technique):
//   • during an active gesture we do NOT touch React state per pointermove — that
//     would re-render the heavy ClipEditorScreen (libass/timeline) → dropped frames
//     and a "not 1:1" grab. Instead we drive the box style IMPERATIVELY via a ref;
//   • Y fraction is normalised against the LIVE getBoundingClientRect() of the inner
//     render box (the box's offsetParent = PreviewPlayer's 9:16 render box) on EVERY
//     move — so it stays correct in fullscreen / after a resize and libass doesn't
//     "jump" scale;
//   • we commit to React state (margin_v / size) ONLY on pointerup — one re-render
//     per gesture.
//
// Move and resize are INDEPENDENT: grabbing the body moves (position only), grabbing
// the handle resizes (font size only) — neither affects the other.

export interface OverlaySelectionBoxProps {
  /** "top" → fraction measured from the top (hook); "bottom" → from the bottom (caption). */
  anchor: "top" | "bottom";
  /** Current vertical fraction [0..1] of the anchored edge within the render box. */
  frac: number;
  /** Current font size (ASS units) — drives the resize gesture's starting point. */
  size: number;
  sizeMin: number;
  sizeMax: number;
  /** Accessible label / role of the element ("Hook" | "Captions"). */
  label: string;
  /** Commit a new vertical fraction (already clamped by the caller's range). */
  onMoveCommit: (frac: number) => void;
  /** Commit a new font size (clamped to [sizeMin, sizeMax]). */
  onResizeCommit: (size: number) => void;
  /** Optional: a plain tap (no drag) on the body — e.g. open inline text edit. */
  onTap?: () => void;
}

// Pixels of drag distance that map to one ASS font-size unit when resizing.
// ~1.4px/unit feels close to CapCut's corner-drag sensitivity at preview scale.
const PX_PER_SIZE_UNIT = 1.4;
// Movement (px) below which a body gesture counts as a tap, not a drag.
const TAP_THRESHOLD = 6;

/** Live render box = the box's offsetParent (PreviewPlayer inner 9:16 box). */
function renderBoxRect(el: HTMLElement): DOMRect | null {
  const box = (el.offsetParent as HTMLElement | null)?.getBoundingClientRect();
  if (!box || box.height <= 0) return null;
  return box;
}

/** Fraction [0..1] of the anchored edge from clientY, given the live render box. */
function fracFromClientY(clientY: number, box: DOMRect, anchor: "top" | "bottom"): number {
  const fromTop = Math.min(1, Math.max(0, (clientY - box.top) / box.height));
  return anchor === "top" ? fromTop : 1 - fromTop;
}

export function OverlaySelectionBox({
  anchor,
  frac,
  size,
  sizeMin,
  sizeMax,
  label,
  onMoveCommit,
  onResizeCommit,
  onTap,
}: OverlaySelectionBoxProps) {
  const boxRef = useRef<HTMLDivElement>(null);
  // Active move gesture: remember the start so we can tell tap vs drag.
  const moveRef = useRef<{ startY: number; moved: boolean } | null>(null);
  // Active resize gesture: anchor the starting size + pointer Y.
  const resizeRef = useRef<{ startY: number; startSize: number } | null>(null);

  const edgeStyle = anchor === "top" ? "top" : "bottom";

  // ── MOVE (body) ──
  const onBodyDown = (e: React.PointerEvent<HTMLDivElement>) => {
    moveRef.current = { startY: e.clientY, moved: false };
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const onBodyMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const m = moveRef.current;
    if (!m) return;
    if (!m.moved && Math.abs(e.clientY - m.startY) < TAP_THRESHOLD) return;
    const box = renderBoxRect(boxRef.current!);
    if (!box) return;
    m.moved = true;
    const f = fracFromClientY(e.clientY, box, anchor);
    // imperative: move the box itself (no React state → no re-render on move)
    const node = boxRef.current;
    if (node) node.style[edgeStyle] = `${f * 100}%`;
  };
  const onBodyUp = (e: React.PointerEvent<HTMLDivElement>) => {
    const m = moveRef.current;
    moveRef.current = null;
    if (!m) return;
    if (!m.moved) {
      onTap?.();
      return;
    }
    const box = renderBoxRect(boxRef.current!);
    if (!box) return;
    onMoveCommit(fracFromClientY(e.clientY, box, anchor));
  };

  // ── RESIZE (corner handle) → font size ──
  const onHandleDown = (e: React.PointerEvent<HTMLButtonElement>) => {
    e.stopPropagation(); // never start a move gesture from the handle
    resizeRef.current = { startY: e.clientY, startSize: size };
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const sizeFromEvent = (clientY: number): number => {
    const r = resizeRef.current;
    if (!r) return size;
    // Dragging DOWN grows the text (CapCut bottom-right corner feel).
    const delta = (clientY - r.startY) / PX_PER_SIZE_UNIT;
    return Math.round(Math.min(sizeMax, Math.max(sizeMin, r.startSize + delta)));
  };
  const onHandleMove = (e: React.PointerEvent<HTMLButtonElement>) => {
    if (!resizeRef.current) return;
    e.stopPropagation();
    // live preview: scale the box height a touch so the gesture feels physical.
    const next = sizeFromEvent(e.clientY);
    const node = boxRef.current;
    if (node) node.style.height = `${heightForSize(next)}%`;
  };
  const onHandleUp = (e: React.PointerEvent<HTMLButtonElement>) => {
    if (!resizeRef.current) return;
    e.stopPropagation();
    const next = sizeFromEvent(e.clientY);
    resizeRef.current = null;
    onResizeCommit(next);
  };

  return (
    <div
      ref={boxRef}
      role="group"
      aria-label={`${label}: drag to reposition, drag the corner to resize`}
      onPointerDown={onBodyDown}
      onPointerMove={onBodyMove}
      onPointerUp={onBodyUp}
      style={{ [edgeStyle]: `${frac * 100}%`, height: `${heightForSize(size)}%` }}
      className="absolute inset-x-[6%] z-30 cursor-grab touch-none rounded-md border border-accent/90 bg-accent/5 shadow-[0_0_0_1px_rgba(0,0,0,0.25)] active:cursor-grabbing"
    >
      {/* corner handles (visual) — only bottom-right is interactive (resize) */}
      <Handle pos="-left-1 -top-1" />
      <Handle pos="-right-1 -top-1" />
      <Handle pos="-bottom-1 -left-1" />
      <button
        type="button"
        aria-label={`Resize ${label.toLowerCase()} text`}
        onPointerDown={onHandleDown}
        onPointerMove={onHandleMove}
        onPointerUp={onHandleUp}
        className="absolute -bottom-2.5 -right-2.5 z-10 size-5 cursor-nwse-resize touch-none rounded-full border-2 border-white bg-accent shadow-md"
      />
    </div>
  );
}

/** A small square corner marker (non-interactive, decorative). */
function Handle({ pos }: { pos: string }) {
  return (
    <span
      className={`pointer-events-none absolute ${pos} size-2 rounded-[2px] border border-white bg-accent`}
    />
  );
}

/**
 * Box height as a % of the render box, derived from font size. Purely a visual
 * affordance so the selection box roughly tracks the text's vertical extent and
 * the resize gesture feels physical — render math is unchanged (size commits via
 * the existing handlers).
 */
function heightForSize(size: number): number {
  // PlayResY = 1920; a line of text is ~1.3× the font size tall. Clamp so the box
  // stays a reasonable on-screen band.
  return Math.min(28, Math.max(6, (size * 1.3 * 100) / 1920));
}
