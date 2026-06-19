"use client";

import { useRef } from "react";
import type { OverlayRect } from "@/lib/overlayBox";

// ── OverlaySelectionBox — CapCut-style on-video selection box for hook / captions ──
// Grab the box ANYWHERE to drag the element vertically; grab the corner handle to
// resize the font. There is NO horizontal-position field in the model (text is
// horizontally centered by the ASS renderer), so manipulation is vertical position
// + font size only.
//
// The box is positioned EXACTLY on libass's OWN rendered rectangle (`rect`, render-box
// fractions surfaced by LibassLayer from the worker's per-frame fused bbox). It is a
// presentational rectangle — no DOM "text-mirror" measurement (a DOM layout engine can't
// reproduce libass's box model: BorderStyle=3 plaque padding, leading, balanced wrap), so
// the box now hugs the real text pixel-for-pixel. If `rect` is null → render nothing.
//
// PERF + scale stability: during an active gesture we do NOT touch React state per
// pointermove — that would re-render the heavy ClipEditorScreen (libass/timeline) →
// dropped frames and a "not 1:1" grab. We drive the box style IMPERATIVELY via a ref and
// commit margin_v / size to React state ONLY on pointerup (one re-render per gesture). The
// Y fraction is normalised against the LIVE getBoundingClientRect() of the inner render
// box (the box's offsetParent = PreviewPlayer's 9:16 render box) on EVERY move — correct
// in fullscreen / after a resize.
//
// Move and resize are INDEPENDENT: grabbing the body moves (position only), grabbing the
// handle resizes (font size only) — neither affects the other.

export interface OverlaySelectionBoxProps {
  /** "top" → fraction measured from the top (hook); "bottom" → from the bottom (caption). */
  anchor: "top" | "bottom";
  /** libass's real rendered rect for this element (render-box fractions), or null to hide. */
  rect: OverlayRect | null;
  /** Current font size (ASS units) — drives the resize gesture's starting point. */
  size: number;
  sizeMin: number;
  sizeMax: number;
  /** Accessible label / role of the element ("Hook" | "Captions"). */
  label: string;
  /** Commit a new vertical fraction of the anchored edge (already clamped by the caller). */
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
// Tiny visual pad (px) so the border sits just OUTSIDE the glyphs (CapCut feel).
const PAD_PX = 2;

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
  rect,
  size,
  sizeMin,
  sizeMax,
  label,
  onMoveCommit,
  onResizeCommit,
  onTap,
}: OverlaySelectionBoxProps) {
  const boxRef = useRef<HTMLDivElement>(null);
  // Active move gesture: remember the start + the grab offset (#3 fix) so the box tracks
  // the cursor 1:1 and never jumps out from under it.
  const moveRef = useRef<{ startY: number; grabOffset: number; moved: boolean } | null>(null);
  // Active resize gesture: anchor the starting size + pointer Y.
  const resizeRef = useRef<{ startY: number; startSize: number } | null>(null);

  const edgeStyle = anchor === "top" ? "top" : "bottom";

  // The anchored-edge fraction of the CURRENT libass rect: top edge for the hook,
  // bottom edge for the caption (both as a fraction of the render-box height).
  const anchoredEdgeFrac = rect
    ? anchor === "top"
      ? rect.topPct / 100
      : 1 - (rect.topPct + rect.heightPct) / 100
    : 0;

  // ── MOVE (body) ──
  const onBodyDown = (e: React.PointerEvent<HTMLDivElement>) => {
    const node = boxRef.current;
    const box = node ? renderBoxRect(node) : null;
    // grabOffset = where the cursor sits RELATIVE to the anchored edge at grab time, so
    // during the drag we set edge = cursorFrac − grabOffset (box tracks the cursor 1:1).
    const cursorFrac = box ? fracFromClientY(e.clientY, box, anchor) : anchoredEdgeFrac;
    moveRef.current = { startY: e.clientY, grabOffset: cursorFrac - anchoredEdgeFrac, moved: false };
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const onBodyMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const m = moveRef.current;
    if (!m) return;
    if (!m.moved && Math.abs(e.clientY - m.startY) < TAP_THRESHOLD) return;
    const node = boxRef.current;
    const box = node ? renderBoxRect(node) : null;
    if (!box || !node) return;
    m.moved = true;
    const edge = Math.min(1, Math.max(0, fracFromClientY(e.clientY, box, anchor) - m.grabOffset));
    // imperative: move the box itself (no React state → no re-render on move)
    node.style[edgeStyle] = `${edge * 100}%`;
  };
  const onBodyUp = (e: React.PointerEvent<HTMLDivElement>) => {
    const m = moveRef.current;
    moveRef.current = null;
    if (!m) return;
    if (!m.moved) {
      onTap?.();
      return;
    }
    const node = boxRef.current;
    const box = node ? renderBoxRect(node) : null;
    if (!box) return;
    const edge = Math.min(1, Math.max(0, fracFromClientY(e.clientY, box, anchor) - m.grabOffset));
    onMoveCommit(edge);
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
    const r = resizeRef.current;
    const node = boxRef.current;
    if (!r || !node) return;
    e.stopPropagation();
    // Imperative visual feedback: scale the box proportional to the size change (the libass
    // canvas re-renders only on commit — on commit the real rect re-hugs exactly). Scale is
    // anchored at the anchored edge (top for hook, bottom for caption) so it doesn't drift.
    const scale = sizeFromEvent(e.clientY) / r.startSize;
    node.style.transform = `scale(${scale})`;
    node.style.transformOrigin = anchor === "top" ? "center top" : "center bottom";
  };
  const onHandleUp = (e: React.PointerEvent<HTMLButtonElement>) => {
    const r = resizeRef.current;
    if (!r) return;
    e.stopPropagation();
    const next = sizeFromEvent(e.clientY);
    resizeRef.current = null;
    const node = boxRef.current;
    if (node) node.style.transform = ""; // clear feedback scale; rect re-hugs on commit
    onResizeCommit(next);
  };

  if (!rect) return null;

  // Position the box EXACTLY on libass's real rect (render-box fractions). The anchored
  // edge is `top` (hook) or `bottom` (caption); left/width/height come straight from the
  // rect. A tiny negative margin + padding lets the border sit a hair OUTSIDE the glyphs.
  return (
    <div
      ref={boxRef}
      role="group"
      aria-label={`${label}: drag to reposition, drag the corner to resize`}
      onPointerDown={onBodyDown}
      onPointerMove={onBodyMove}
      onPointerUp={onBodyUp}
      style={{
        [edgeStyle]: `${anchoredEdgeFrac * 100}%`,
        left: `${rect.leftPct}%`,
        width: `${rect.widthPct}%`,
        height: `${rect.heightPct}%`,
        margin: `-${PAD_PX}px`,
        padding: `${PAD_PX}px`,
        boxSizing: "content-box",
      }}
      className="absolute z-30 cursor-grab touch-none rounded-[3px] border border-white/90 shadow-[0_0_0_1px_rgba(0,0,0,0.45)] active:cursor-grabbing"
    >
      {/* clean white corner markers (CapCut-style); bottom-right is the resize handle */}
      <Handle pos="-left-1 -top-1" />
      <Handle pos="-right-1 -top-1" />
      <Handle pos="-bottom-1 -left-1" />
      <button
        type="button"
        aria-label={`Resize ${label.toLowerCase()} text`}
        onPointerDown={onHandleDown}
        onPointerMove={onHandleMove}
        onPointerUp={onHandleUp}
        className="absolute -bottom-1.5 -right-1.5 z-10 size-3.5 cursor-nwse-resize touch-none rounded-[2px] border border-black/40 bg-white shadow"
      />
    </div>
  );
}

/** A small square corner marker (non-interactive, decorative). */
function Handle({ pos }: { pos: string }) {
  return (
    <span
      className={`pointer-events-none absolute ${pos} size-2 rounded-[1px] bg-white shadow-[0_0_0_1px_rgba(0,0,0,0.45)]`}
    />
  );
}
