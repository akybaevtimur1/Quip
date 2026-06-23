"use client";

import { useEffect, useRef } from "react";
import type { OverlayRect } from "@/lib/overlayBox";
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
  /** Current committed anchor fraction X (text center). A move commits currentAnchor + boxΔ so the
   *  re-rendered libass bbox lands exactly where the box was dropped (the union-bbox ≠ the anchor). */
  posX: number;
  /** Current committed anchor fraction Y (the anchored edge, measured from the top). */
  posY: number;
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

/**
 * The libass <canvas> that renders THIS box's element (hook | caption). Both canvases are
 * `absolute inset-0 size-full` siblings inside the same render box (the box's offsetParent),
 * so they share the box's coordinate space → a px delta/scale applied here matches the box 1:1.
 * `data-libass-part` is set by LibassLayer. Returns null if libass isn't mounted (CSS fallback).
 */
function libassCanvas(boxEl: HTMLElement, anchor: "top" | "bottom"): HTMLElement | null {
  const root = boxEl.offsetParent as HTMLElement | null;
  if (!root) return null;
  const part = anchor === "top" ? "hook" : "caption";
  return root.querySelector<HTMLElement>(`canvas[data-libass-part="${part}"]`);
}

const clamp01 = (v: number) => Math.min(1, Math.max(0, v));

export function OverlaySelectionBox({
  anchor,
  rect,
  size,
  sizeMin,
  sizeMax,
  posX,
  posY,
  label,
  onMoveCommit,
  onResizeCommit,
  onWidthCommit,
  onTap,
  otherRect,
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
  // RESIZE (font): anchor the starting size + pointer Y, plus the box's anchor point in render-box
  // px (center-X + anchored edge-Y) so the canvas scales about the SAME point as the box.
  const resizeRef = useRef<{
    startY: number;
    startSize: number;
    originX: number;
    originY: number;
    boxLeft: number;
    boxTop: number;
    startHeightPct: number;
  } | null>(null);
  // WIDTH (block): center + base half-width + which side is being dragged.
  const widthRef = useRef<{ startX: number; centerX: number; baseHalf: number; side: 1 | -1 } | null>(
    null,
  );
  // ── libass-text-follows-the-box (kills the during-drag separation + commit teleport) ──
  // During a gesture we apply the SAME visual transform to THIS element's libass canvas as we
  // apply to the box (translate for MOVE, scale for RESIZE), so the rendered text moves WITH the
  // frame. We must NOT clear that transform on pointerup: libass only re-renders at the new \pos
  // a few frames later, so clearing immediately snaps the text back to the OLD spot for a frame
  // (flash-back). Instead we keep the transform applied and flag a pending reconcile; once the
  // next libass bbox (`rect`) arrives reflecting the new position, the effect below clears it —
  // a seamless handoff. A short timeout is the safety net if no new rect arrives.
  const canvasTxRef = useRef<HTMLElement | null>(null); // canvas currently holding a drag transform
  const pendingReconcileRef = useRef(false); // true between commit and the libass re-render
  const reconcileTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Predicate that returns true once the live libass bbox (`rect`) reflects the COMMITTED target
  // (new position / new size) — gates the transform handoff so we don't clear on a stale frame.
  const reconcileMatchRef = useRef<((r: OverlayRect) => boolean) | null>(null);

  const setCanvasTransform = (transform: string, origin: string) => {
    const node = boxRef.current;
    const canvas = node ? libassCanvas(node, anchor) : null;
    if (!canvas) return;
    canvas.style.transformOrigin = origin;
    canvas.style.transform = transform;
    canvasTxRef.current = canvas;
  };

  const clearCanvasTransform = () => {
    const canvas = canvasTxRef.current;
    if (canvas) {
      canvas.style.transform = "";
      canvas.style.transformOrigin = "";
    }
    canvasTxRef.current = null;
    // ALSO drop the box's OWN gesture transform (the RESIZE feedback scale) in the SAME tick, so the
    // frame and the text lose their transforms together. The bug was: onHandleUp cleared the box
    // scale on release while the canvas scale was held → frame snapped to the OLD (small) size while
    // the text stayed at the NEW (big) size → "the text jumps inside the stationary frame". MOVE uses
    // left/top (no box transform) so this is a no-op there.
    const node = boxRef.current;
    if (node) {
      node.style.transform = "";
      node.style.transformOrigin = "";
    }
    reconcileMatchRef.current = null;
    pendingReconcileRef.current = false;
    if (reconcileTimerRef.current) {
      clearTimeout(reconcileTimerRef.current);
      reconcileTimerRef.current = null;
    }
  };

  // Arm the seamless handoff: KEEP the transform through the commit, then clear it once libass has
  // re-rendered at the new \pos (next `rect` update, handled by the effect) — with a timeout net.
  const armReconcile = (match: (r: OverlayRect) => boolean) => {
    pendingReconcileRef.current = true;
    reconcileMatchRef.current = match;
    if (reconcileTimerRef.current) clearTimeout(reconcileTimerRef.current);
    reconcileTimerRef.current = setTimeout(clearCanvasTransform, 450);
  };

  // Clear the drag transform once a FRESH libass bbox arrives after a commit (text now rendered at
  // the new position → safe to drop the visual transform with no flash-back). `rect` is the live
  // bbox fractions from LibassLayer; a new object identity per libass render frame is the signal.
  useEffect(() => {
    if (!pendingReconcileRef.current) return;
    // Hand off ONLY once libass's bbox reflects the committed target — the first rect updates after a
    // commit are still the OLD state (setTrack is async), so clearing on the first one snaps for a
    // frame. The per-gesture predicate gates it; a null rect / no predicate → clear immediately.
    const match = reconcileMatchRef.current;
    if (!rect || !match || match(rect)) clearCanvasTransform();
  }, [rect]);

  // Cleanup on unmount: never leave a transform stuck on the shared canvas.
  useEffect(() => () => clearCanvasTransform(), []);

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
    // A fresh gesture supersedes any in-flight reconcile from the previous commit.
    clearCanvasTransform();
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
      const targets = buildTargets(W, H, other);
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
    // Move THIS element's libass text by the SAME px delta so the rendered glyphs track the frame
    // 1:1 during the drag (no separation). Canvas shares the render-box coord space → identical px.
    setCanvasTransform(
      `translate(${snapLeft - m.baseLeft}px, ${snapTop - m.baseTop}px)`,
      "0 0",
    );
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
    // Commit by the box's DISPLACEMENT (delta), not its absolute geometry. The box was hugging the
    // libass union-bbox at gesture start, and the bbox−anchor offset (font metrics / plaque / a
    // highlighted word) is translation-invariant — so moving the anchor by the SAME Δ as the box
    // lands the re-rendered bbox EXACTLY where it was dropped. Committing absolute box geometry
    // teleported the text on release because the union-bbox center/edge ≠ the text anchor.
    const finalLeft = nr.left - box.left;
    const finalTop = nr.top - box.top;
    const dxFrac = (finalLeft - m.baseLeft) / box.width;
    const dyFrac = (finalTop - m.baseTop) / box.height; // pure translation → same Δ for top or bottom edge
    const newPosX = clamp01(posX + dxFrac);
    const newPosY = clamp01(posY + dyFrac);
    // The box's final on-screen geometry is the seamless handoff target for the next libass bbox.
    const finalCenterX = (finalLeft + nr.width / 2) / box.width;
    const finalEdgeY = anchor === "top" ? finalTop / box.height : (nr.bottom - box.top) / box.height;
    armReconcile(
      (r) => {
        const cx = (r.leftPct + r.widthPct / 2) / 100;
        const ey = anchor === "top" ? r.topPct / 100 : (r.topPct + r.heightPct) / 100;
        return Math.abs(cx - finalCenterX) < 0.04 && Math.abs(ey - finalEdgeY) < 0.04;
      },
    );
    onMoveCommit(newPosX, newPosY);
  };

  // ── RESIZE (corner handle) → font size ──
  const onHandleDown = (e: React.PointerEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    const node = boxRef.current;
    const box = node ? renderBoxRect(node) : null;
    // Scale BOTH the frame and the libass canvas about the TRUE text anchor (pos), in render-box px
    // — NOT the bbox edge. libass anchors the text at pos and grows about it; the inked bbox edge is
    // offset from the anchor by font metrics, and that offset scales with size — so scaling about the
    // edge drifts on commit (the "text jumps inside the frame on resize" bug). originX/Y = the anchor;
    // boxLeft/Top let us express the box's own transform-origin (anchor relative to the box element).
    let originX = 0,
      originY = 0,
      boxLeft = 0,
      boxTop = 0;
    if (node && box) {
      const nr = node.getBoundingClientRect();
      boxLeft = nr.left - box.left;
      boxTop = nr.top - box.top;
      originX = posX * box.width;
      originY = posY * box.height;
    }
    resizeRef.current = {
      startY: e.clientY,
      startSize: size,
      originX,
      originY,
      boxLeft,
      boxTop,
      startHeightPct: rect?.heightPct ?? 0,
    };
    clearCanvasTransform(); // supersede any in-flight reconcile
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
    // Scale the frame about the TRUE anchor (anchor px relative to the box), matching libass.
    node.style.transformOrigin = `${r.originX - r.boxLeft}px ${r.originY - r.boxTop}px`;
    // Scale THIS element's libass text by the SAME factor about the SAME render-box anchor point,
    // so the rendered glyphs grow/shrink locked to the frame (no lag, no commit teleport).
    setCanvasTransform(`scale(${scale})`, `${r.originX}px ${r.originY}px`);
  };
  const onHandleUp = (e: React.PointerEvent<HTMLButtonElement>) => {
    const r = resizeRef.current;
    if (!r) return;
    e.stopPropagation();
    const next = sizeFromEvent(e.clientY);
    const targetH = r.startHeightPct * (next / r.startSize);
    resizeRef.current = null;
    // Do NOT clear the box scale here — keep BOTH the frame scale and the canvas scale through the
    // commit so the frame never shows a size that mismatches the text (the "text jumps inside the
    // frame" bug). They drop together once the libass bbox height ≈ the new size's target.
    armReconcile((rr) => targetH <= 0 || Math.abs(rr.heightPct - targetH) / targetH < 0.12);
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
    // WIDTH changes line WRAPPING, not a uniform transform — no CSS transform can preview a reflow,
    // so the text still catches up on commit here (best-effort). But supersede any in-flight
    // reconcile from a prior move/resize so we don't leave a stale transform on the canvas.
    clearCanvasTransform();
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
