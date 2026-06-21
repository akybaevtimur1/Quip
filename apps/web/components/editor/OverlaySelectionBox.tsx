"use client";

import { useRef } from "react";
import type { OverlayRect } from "@/lib/overlayBox";
import { safeBoxPx, type SafeInsets } from "@/lib/safeAreas";
import { computeSnap, SNAP_THRESHOLD_PX } from "@/lib/snapEngine";
import { buildTargets } from "@/lib/snapTargets";
import type { SnapGuidesHandle } from "./SnapGuides";

// ── OverlaySelectionBox — CapCut-style on-video selection box for hook / captions ──
// Grab the box ANYWHERE to move it FREELY (X + Y, into a corner). Grab a CORNER handle to
// resize the font. Grab a SIDE handle (left/right middle) to change the BLOCK WIDTH — the
// text reflows onto more lines WITHOUT changing the font size (libass MarginL/MarginR).
//
// The box is positioned EXACTLY on libass's OWN rendered rectangle (`rect`, render-box
// fractions surfaced by LibassLayer from the worker's per-frame fused bbox), so it hugs the
// real text pixel-for-pixel (no DOM text-mirror — a browser can't reproduce libass's box
// model). If `rect` is null → render nothing.
//
// PERF + 1:1 feel: during a gesture we DON'T touch React state per pointermove — that would
// re-render the heavy ClipEditorScreen (libass/timeline) → dropped frames and a laggy grab.
// We drive the box style IMPERATIVELY via a ref (setPointerCapture) and commit to React state
// ONLY on pointerup (one re-render per gesture). All fractions are normalised against the LIVE
// getBoundingClientRect() of the inner render box (offsetParent = PreviewPlayer's render box)
// on every move → correct in fullscreen / after a resize.
//
// Commit semantics (mirror models.py / captions_v2.py):
//   • move  → pos_x = box CENTER-X fraction; pos_y = the ANCHORED EDGE fraction from the TOP
//             (caption = BOTTOM edge under \an2; hook = TOP edge under \an8).
//   • corner→ font size.
//   • side  → wrap_width = box width fraction of the render box.

export interface OverlaySelectionBoxProps {
  /** "top" → hook (\an8, top edge anchored); "bottom" → caption (\an2, bottom edge anchored). */
  anchor: "top" | "bottom";
  /** libass's real rendered rect for this element (render-box fractions), or null to hide. */
  rect: OverlayRect | null;
  /** Current font size (ASS units) — drives the resize gesture's starting point. */
  size: number;
  sizeMin: number;
  sizeMax: number;
  /** Accessible label / role of the element ("Hook" | "Captions"). */
  label: string;
  /** Commit free position: center-X fraction + anchored-edge fraction (both 0..1, clamped). */
  onMoveCommit: (xFrac: number, yFrac: number) => void;
  /** Commit a new font size (clamped to [sizeMin, sizeMax]). */
  onResizeCommit: (size: number) => void;
  /** Commit a new block-width fraction (0..1, clamped). */
  onWidthCommit: (widthFrac: number) => void;
  /** Optional: a plain tap (no drag) on the body — e.g. open inline text edit. */
  onTap?: () => void;
  /** The OTHER element's render-box-fraction rect, for element-to-element snapping (or null). */
  otherRect?: OverlayRect | null;
  /** Active platform safe-area insets (fractions 0..1), or null when no platform picked. */
  safeInsets?: SafeInsets | null;
  /** Whether snapping is active. Hold Alt during a drag to suspend it. Default true. */
  snapEnabled?: boolean;
  /** Imperative handle to the alignment-guide overlay (drawn during snap). */
  guidesRef?: React.RefObject<SnapGuidesHandle | null>;
}

// Pixels of drag distance that map to one ASS font-size unit when resizing.
const PX_PER_SIZE_UNIT = 1.4;
// Movement (px) below which a body gesture counts as a tap, not a drag.
const TAP_THRESHOLD = 6;
// Tiny visual pad (px) so the border sits just OUTSIDE the glyphs (CapCut feel).
const PAD_PX = 2;
// Narrowest block width we let the side handle commit (fraction of the render box).
const MIN_WIDTH_FRAC = 0.2;

/** Live render box = the box's offsetParent (PreviewPlayer inner render box). */
function renderBoxRect(el: HTMLElement): DOMRect | null {
  const box = (el.offsetParent as HTMLElement | null)?.getBoundingClientRect();
  if (!box || box.height <= 0 || box.width <= 0) return null;
  return box;
}

const clamp01 = (v: number) => Math.min(1, Math.max(0, v));

export function OverlaySelectionBox({
  anchor,
  rect,
  size,
  sizeMin,
  sizeMax,
  label,
  onMoveCommit,
  onResizeCommit,
  onWidthCommit,
  onTap,
  otherRect,
  safeInsets,
  snapEnabled = true,
  guidesRef,
}: OverlaySelectionBoxProps) {
  const boxRef = useRef<HTMLDivElement>(null);
  // MOVE: pointer start + the box's base offset (px in render box) so it tracks the cursor 1:1.
  const moveRef = useRef<{
    startX: number;
    startY: number;
    baseLeft: number;
    baseTop: number;
    moved: boolean;
  } | null>(null);
  // RESIZE (font): anchor the starting size + pointer Y.
  const resizeRef = useRef<{ startY: number; startSize: number } | null>(null);
  // WIDTH (block): center + base half-width + which side is being dragged.
  const widthRef = useRef<{ startX: number; centerX: number; baseHalf: number; side: 1 | -1 } | null>(
    null,
  );

  // ── MOVE (body) → free X/Y ──
  const onBodyDown = (e: React.PointerEvent<HTMLDivElement>) => {
    const node = boxRef.current;
    const box = node ? renderBoxRect(node) : null;
    if (!node || !box) return;
    const nr = node.getBoundingClientRect();
    moveRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      baseLeft: nr.left - box.left,
      baseTop: nr.top - box.top,
      moved: false,
    };
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const onBodyMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const m = moveRef.current;
    const node = boxRef.current;
    if (!m || !node) return;
    if (!m.moved && Math.abs(e.clientX - m.startX) < TAP_THRESHOLD && Math.abs(e.clientY - m.startY) < TAP_THRESHOLD)
      return;
    const box = renderBoxRect(node);
    if (!box) return;
    m.moved = true;
    const nr = node.getBoundingClientRect();
    const left = Math.min(box.width - nr.width, Math.max(0, m.baseLeft + (e.clientX - m.startX)));
    const top = Math.min(box.height - nr.height, Math.max(0, m.baseTop + (e.clientY - m.startY)));
    // SNAP (pure math, imperative draw) — fully off the React-state path so the drag stays
    // zero-re-render. Hold Alt to suspend. Compute candidate lines (canvas center/edges, the
    // platform safe area, the OTHER element), snap the raw box to the nearest within threshold,
    // clamp back inside the render box, and draw the magenta guides via the ref handle.
    let snapLeft = left,
      snapTop = top;
    if (snapEnabled && !e.altKey) {
      const W = box.width,
        H = box.height;
      const other = otherRect
        ? {
            left: (otherRect.leftPct / 100) * W,
            top: (otherRect.topPct / 100) * H,
            width: (otherRect.widthPct / 100) * W,
            height: (otherRect.heightPct / 100) * H,
          }
        : null;
      const safe = safeInsets ? safeBoxPx(safeInsets, W, H) : null;
      const targets = buildTargets(W, H, other, safe);
      const res = computeSnap({ left, top, width: nr.width, height: nr.height }, targets, SNAP_THRESHOLD_PX);
      snapLeft = Math.min(box.width - nr.width, Math.max(0, res.left));
      snapTop = Math.min(box.height - nr.height, Math.max(0, res.top));
      guidesRef?.current?.show(res.guides, W, H);
    } else {
      guidesRef?.current?.hide();
    }
    // imperative: move the box itself (no React state → no re-render on move). Always position
    // by top/left during the drag (clear the % anchor) so X and Y are free.
    node.style.left = `${(snapLeft / box.width) * 100}%`;
    node.style.top = `${(snapTop / box.height) * 100}%`;
    node.style.bottom = "auto";
  };
  const onBodyUp = () => {
    const m = moveRef.current;
    moveRef.current = null;
    // Clear any alignment guides on release (covers the snapped-drag, tap, and missing-box paths).
    guidesRef?.current?.hide();
    const node = boxRef.current;
    if (!m || !node) return;
    if (!m.moved) {
      onTap?.();
      return;
    }
    const box = renderBoxRect(node);
    if (!box) return;
    const nr = node.getBoundingClientRect();
    const centerX = (nr.left - box.left + nr.width / 2) / box.width;
    // anchored edge fraction FROM THE TOP: caption commits its BOTTOM edge (\an2), hook its TOP.
    const edgeY = anchor === "top" ? (nr.top - box.top) / box.height : (nr.bottom - box.top) / box.height;
    onMoveCommit(clamp01(centerX), clamp01(edgeY));
  };

  // ── RESIZE (corner handle) → font size ──
  const onHandleDown = (e: React.PointerEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    resizeRef.current = { startY: e.clientY, startSize: size };
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const sizeFromEvent = (clientY: number): number => {
    const r = resizeRef.current;
    if (!r) return size;
    const delta = (clientY - r.startY) / PX_PER_SIZE_UNIT; // drag DOWN grows (CapCut feel)
    return Math.round(Math.min(sizeMax, Math.max(sizeMin, r.startSize + delta)));
  };
  const onHandleMove = (e: React.PointerEvent<HTMLButtonElement>) => {
    const r = resizeRef.current;
    const node = boxRef.current;
    if (!r || !node) return;
    e.stopPropagation();
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

  // ── WIDTH (side handles) → block width (wrap_width) ──
  // Single handler (NOT a factory created in render — that would trip react-hooks/refs); the
  // dragged side comes from the button's data-side attribute.
  const onWidthDown = (e: React.PointerEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    const node = boxRef.current;
    const box = node ? renderBoxRect(node) : null;
    if (!node || !box) return;
    const side: 1 | -1 = e.currentTarget.dataset.side === "1" ? 1 : -1;
    const nr = node.getBoundingClientRect();
    widthRef.current = {
      startX: e.clientX,
      centerX: nr.left - box.left + nr.width / 2,
      baseHalf: nr.width / 2,
      side,
    };
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const halfFromEvent = (clientX: number, box: DOMRect): number => {
    const w = widthRef.current;
    if (!w) return 0;
    const half = w.baseHalf + w.side * (clientX - w.startX); // outward = wider
    return Math.min(box.width / 2, Math.max((MIN_WIDTH_FRAC * box.width) / 2, half));
  };
  const onWidthMove = (e: React.PointerEvent<HTMLButtonElement>) => {
    const w = widthRef.current;
    const node = boxRef.current;
    if (!w || !node) return;
    e.stopPropagation();
    const box = renderBoxRect(node);
    if (!box) return;
    const half = halfFromEvent(e.clientX, box);
    // imperative feedback: widen/narrow the box symmetrically about its center (the text only
    // reflows on commit, when libass re-wraps to the new MarginL/R).
    node.style.width = `${((2 * half) / box.width) * 100}%`;
    node.style.left = `${((w.centerX - half) / box.width) * 100}%`;
  };
  const onWidthUp = (e: React.PointerEvent<HTMLButtonElement>) => {
    const w = widthRef.current;
    const node = boxRef.current;
    if (!w || !node) return;
    e.stopPropagation();
    const box = renderBoxRect(node);
    // compute the committed width BEFORE clearing widthRef — halfFromEvent reads widthRef,
    // so nulling it first would make it return 0 → degenerate wrap_width=0 (wraps every word).
    if (box) {
      const half = halfFromEvent(e.clientX, box);
      onWidthCommit(clamp01((2 * half) / box.width));
    }
    widthRef.current = null;
  };

  if (!rect) return null;

  // Position the box EXACTLY on libass's real rect (render-box fractions): top/left/width/height.
  // A tiny negative margin + padding lets the border sit a hair OUTSIDE the glyphs.
  return (
    <div
      ref={boxRef}
      role="group"
      aria-label={`${label}: drag to move, corner to resize, side to change width`}
      onPointerDown={onBodyDown}
      onPointerMove={onBodyMove}
      onPointerUp={onBodyUp}
      style={{
        top: `${rect.topPct}%`,
        left: `${rect.leftPct}%`,
        width: `${rect.widthPct}%`,
        height: `${rect.heightPct}%`,
        margin: `-${PAD_PX}px`,
        padding: `${PAD_PX}px`,
        boxSizing: "content-box",
      }}
      className="absolute z-30 cursor-grab touch-none rounded-[3px] border border-white/90 shadow-[0_0_0_1px_rgba(0,0,0,0.45)] active:cursor-grabbing"
    >
      {/* crisp corner markers */}
      <Handle pos="-left-1 -top-1" />
      <Handle pos="-right-1 -top-1" />
      <Handle pos="-bottom-1 -left-1" />
      {/* SIDE width handles (left/right middle) — short vertical bars */}
      <button
        type="button"
        data-side="-1"
        aria-label={`Change ${label.toLowerCase()} width`}
        onPointerDown={onWidthDown}
        onPointerMove={onWidthMove}
        onPointerUp={onWidthUp}
        className="absolute -left-1.5 top-1/2 z-10 h-5 w-2 -translate-y-1/2 cursor-ew-resize touch-none rounded-full border border-black/40 bg-white shadow"
      />
      <button
        type="button"
        data-side="1"
        aria-label={`Change ${label.toLowerCase()} width`}
        onPointerDown={onWidthDown}
        onPointerMove={onWidthMove}
        onPointerUp={onWidthUp}
        className="absolute -right-1.5 top-1/2 z-10 h-5 w-2 -translate-y-1/2 cursor-ew-resize touch-none rounded-full border border-black/40 bg-white shadow"
      />
      {/* CORNER resize handle (bottom-right) → font size */}
      <button
        type="button"
        aria-label={`Resize ${label.toLowerCase()} text`}
        onPointerDown={onHandleDown}
        onPointerMove={onHandleMove}
        onPointerUp={onHandleUp}
        className="absolute -bottom-2 -right-2 z-10 size-4 cursor-nwse-resize touch-none rounded-[3px] border border-black/40 bg-white shadow"
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
