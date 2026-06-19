"use client";

import { useEffect, useRef, useState } from "react";
import { boxPctFromMetrics, wrapWidthPx } from "@/lib/overlayBox";

// ── OverlaySelectionBox — CapCut-style on-video selection box for hook / captions ──
// Grab the box ANYWHERE to drag the element vertically; grab the corner handle to
// resize the font. There is NO horizontal-position field in the model (text is
// horizontally centered by the ASS renderer), so manipulation is vertical position
// + font size only.
//
// The box TIGHTLY HUGS the actual text (CapCut feel): we measure the glyph extent
// with a hidden off-screen DOM "text-mirror" laid out at the SAME font px and wrap
// width libass uses, then size the box to that (centered horizontally, anchored
// top/bottom at `frac`). It resizes live while dragging the corner.
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
  /** Visible text of the element (for tight measurement). ASS `\N` = hard line break. */
  text: string;
  /** Font family name (must match a libass font: Montserrat | Unbounded | Rubik). */
  font: string;
  /** ASS left/right margin (logical px): captions = 40, hook = 60. */
  marginLR: number;
  /** Whether the rendered text is upper-cased (affects measured width). */
  uppercase: boolean;
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
// Uniform padding around the measured glyph extent, as a fraction of render-box
// height (each side). Small → the box "hugs" the text like CapCut.
const PAD_FRAC = 0.012;

// The web app loads only Onest/Plex via next/font; the caption fonts (Montserrat /
// Unbounded / Rubik) exist ONLY as the .ttf files served to libass-wasm. To measure
// the TRUE glyph metrics we register those same files via the FontFace API (once,
// lazily) so the mirror lays out in the real face — not a system fallback.
const LIBASS_FONT_URL: Record<string, string> = {
  Montserrat: "/libass/fonts/Montserrat.ttf",
  Unbounded: "/libass/fonts/Unbounded.ttf",
  Rubik: "/libass/fonts/Rubik.ttf",
};
const loadedFonts = new Set<string>();

/** Register a libass font face with the document (idempotent). No-op if unknown. */
function ensureFontLoaded(font: string): Promise<void> | null {
  if (typeof document === "undefined" || !("fonts" in document)) return null;
  const url = LIBASS_FONT_URL[font];
  if (!url || loadedFonts.has(font)) return null;
  loadedFonts.add(font);
  try {
    const face = new FontFace(font, `url("${url}")`);
    return face.load().then((loaded) => {
      document.fonts.add(loaded);
    });
  } catch {
    loadedFonts.delete(font);
    return null;
  }
}

/** CSS font-family for the mirror — real face first, then a sane fallback chain. */
function fontFamilyFor(font: string): string {
  return font === "Montserrat"
    ? `"Montserrat", var(--font-display), system-ui, sans-serif`
    : `"${font}", var(--font-display), system-ui, sans-serif`;
}

/** Escape text for safe innerHTML, converting ASS `\N` hard breaks to <br>. */
function textToHtml(text: string): string {
  const esc = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  // ASS hard line break is a literal backslash-N (\N). Newlines also become <br>.
  return esc.replace(/\\N/g, "<br>").replace(/\r?\n/g, "<br>");
}

/** Box size in % of the render box, or null if the box isn't laid out / no text. */
export interface BoxPct {
  widthPct: number;
  heightPct: number;
}

/**
 * Measure the tight glyph extent of `text` at the given on-screen font size and
 * wrap width, returning the box size in % of the render box. Pure DOM measurement
 * via a hidden off-screen mirror (no React state churn). Returns null when the
 * render box isn't laid out yet (NO guessed fallback — project rule: no silent fake).
 */
function measureBox(
  mirror: HTMLDivElement,
  renderBox: HTMLElement,
  opts: {
    text: string;
    font: string;
    marginLR: number;
    uppercase: boolean;
    fontPx: number;
  },
): BoxPct | null {
  const renderW = renderBox.clientWidth;
  const renderH = renderBox.clientHeight;
  if (renderW === 0 || renderH === 0) return null;
  const content = opts.uppercase ? opts.text.toUpperCase() : opts.text;
  if (!content.trim()) return null;

  const wrapW = wrapWidthPx(opts.marginLR, renderW);
  mirror.style.font = `${opts.fontPx}px ${fontFamilyFor(opts.font)}`;
  mirror.style.lineHeight = "normal";
  mirror.style.width = `${wrapW}px`;
  mirror.style.textAlign = "center";
  mirror.style.whiteSpace = "normal";
  mirror.style.wordBreak = "normal";
  mirror.innerHTML = textToHtml(content);

  // width = TIGHT glyph extent of the contents (NOT the div's own rect — the div is
  // forced to wrapW). height = the wrapped block's rect.
  const range = document.createRange();
  range.selectNodeContents(mirror);
  const tightW = range.getBoundingClientRect().width;
  range.detach?.();
  const blockH = mirror.getBoundingClientRect().height;
  if (tightW === 0 || blockH === 0) return null;

  return boxPctFromMetrics(tightW, blockH, renderW, renderH, PAD_FRAC);
}

/**
 * useTextBox — keeps a hidden off-screen mirror <div> mounted (appended to <body>
 * once, removed on unmount) and re-measures the box size whenever inputs change,
 * fonts load, or the render box resizes / fullscreen toggles. `getRenderBox` reads
 * the live offsetParent. Returns the measured {widthPct,heightPct} or null.
 */
function useTextBox(
  getRenderBox: () => HTMLElement | null,
  opts: { text: string; font: string; marginLR: number; uppercase: boolean; size: number },
): { box: BoxPct | null; measureAt: (fontPxOverride: number) => BoxPct | null } {
  const mirrorRef = useRef<HTMLDivElement | null>(null);
  const [box, setBox] = useState<BoxPct | null>(null);

  // mount the off-screen mirror once
  useEffect(() => {
    const el = document.createElement("div");
    el.style.position = "absolute";
    el.style.left = "-99999px";
    el.style.top = "0";
    el.style.visibility = "hidden";
    el.style.pointerEvents = "none";
    el.setAttribute("aria-hidden", "true");
    document.body.appendChild(el);
    mirrorRef.current = el;
    return () => {
      el.remove();
      mirrorRef.current = null;
    };
  }, []);

  // measure at the CURRENT committed size (k derived from the live render box width)
  const measureAt = (fontPxOverride: number): BoxPct | null => {
    const mirror = mirrorRef.current;
    const renderBox = getRenderBox();
    if (!mirror || !renderBox) return null;
    return measureBox(mirror, renderBox, {
      text: opts.text,
      font: opts.font,
      marginLR: opts.marginLR,
      uppercase: opts.uppercase,
      fontPx: fontPxOverride,
    });
  };

  // re-measure on inputs + fonts.ready + render-box resize + fullscreen toggles
  useEffect(() => {
    let cancelled = false;
    const remeasure = () => {
      const mirror = mirrorRef.current;
      const renderBox = getRenderBox();
      if (!mirror || !renderBox) {
        if (!cancelled) setBox(null);
        return;
      }
      const renderW = renderBox.clientWidth;
      if (renderW === 0) {
        if (!cancelled) setBox(null);
        return;
      }
      const k = renderW / 1080;
      const next = measureBox(mirror, renderBox, {
        text: opts.text,
        font: opts.font,
        marginLR: opts.marginLR,
        uppercase: opts.uppercase,
        fontPx: opts.size * k,
      });
      if (!cancelled) setBox(next);
    };

    // gate on custom fonts loading (Montserrat/Unbounded/Rubik) so width is correct
    const fontPromise = ensureFontLoaded(opts.font);
    Promise.all([
      document.fonts?.ready ?? Promise.resolve(),
      fontPromise ?? Promise.resolve(),
    ]).then(remeasure);
    remeasure(); // also measure now (fonts may already be cached)

    // mirror LibassLayer: ResizeObserver on the render box + fullscreen/resize
    const renderBox = getRenderBox();
    let ro: ResizeObserver | null = null;
    if (renderBox) {
      ro = new ResizeObserver(remeasure);
      ro.observe(renderBox);
    }
    document.addEventListener("fullscreenchange", remeasure);
    window.addEventListener("resize", remeasure);
    return () => {
      cancelled = true;
      ro?.disconnect();
      document.removeEventListener("fullscreenchange", remeasure);
      window.removeEventListener("resize", remeasure);
    };
    // getRenderBox reads boxRef.current.offsetParent live (stable closure); the box
    // size only depends on the inputs below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opts.text, opts.font, opts.marginLR, opts.uppercase, opts.size]);

  return { box, measureAt };
}

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
  text,
  font,
  marginLR,
  uppercase,
  onMoveCommit,
  onResizeCommit,
  onTap,
}: OverlaySelectionBoxProps) {
  const boxRef = useRef<HTMLDivElement>(null);
  // Active move gesture: remember the start so we can tell tap vs drag.
  const moveRef = useRef<{ startY: number; moved: boolean } | null>(null);
  // Active resize gesture: anchor the starting size + pointer Y.
  const resizeRef = useRef<{ startY: number; startSize: number } | null>(null);
  // rAF throttle for live resize re-measure.
  const rafRef = useRef(0);

  const edgeStyle = anchor === "top" ? "top" : "bottom";

  const getRenderBox = () => (boxRef.current?.offsetParent as HTMLElement | null) ?? null;
  const { box, measureAt } = useTextBox(getRenderBox, { text, font, marginLR, uppercase, size });

  // ── MOVE (body) ──
  const onBodyDown = (e: React.PointerEvent<HTMLDivElement>) => {
    moveRef.current = { startY: e.clientY, moved: false };
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const onBodyMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const m = moveRef.current;
    if (!m) return;
    if (!m.moved && Math.abs(e.clientY - m.startY) < TAP_THRESHOLD) return;
    const rect = renderBoxRect(boxRef.current!);
    if (!rect) return;
    m.moved = true;
    const f = fracFromClientY(e.clientY, rect, anchor);
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
    const rect = renderBoxRect(boxRef.current!);
    if (!rect) return;
    onMoveCommit(fracFromClientY(e.clientY, rect, anchor));
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
    const next = sizeFromEvent(e.clientY);
    // live re-hug: re-measure the box at the dragged size, rAF-throttled, and apply
    // imperatively (no React state per move → no heavy re-render). The box visibly
    // grows/shrinks with the text as you drag (CapCut "text scales" feel).
    if (rafRef.current) return;
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = 0;
      const renderBox = getRenderBox();
      const node = boxRef.current;
      if (!renderBox || !node) return;
      const k = renderBox.clientWidth / 1080;
      const live = measureAt(next * k);
      if (live) {
        node.style.width = `${live.widthPct}%`;
        node.style.height = `${live.heightPct}%`;
      }
    });
  };
  const onHandleUp = (e: React.PointerEvent<HTMLButtonElement>) => {
    if (!resizeRef.current) return;
    e.stopPropagation();
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = 0;
    }
    const next = sizeFromEvent(e.clientY);
    resizeRef.current = null;
    onResizeCommit(next);
  };

  useEffect(
    () => () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    },
    [],
  );

  // The box div is ALWAYS mounted (even before measurement) so that boxRef has an
  // offsetParent to measure the render box from — otherwise it's a chicken-and-egg:
  // returning null while unmeasured means we can never measure. Until measured we keep
  // it laid-out but invisible (visibility:hidden keeps offsetParent resolvable, unlike
  // display:none); border + handles appear only once we have a real size.
  const measured = box !== null;

  return (
    <div
      ref={boxRef}
      role="group"
      aria-label={`${label}: drag to reposition, drag the corner to resize`}
      onPointerDown={onBodyDown}
      onPointerMove={onBodyMove}
      onPointerUp={onBodyUp}
      style={{
        [edgeStyle]: `${frac * 100}%`,
        left: "50%",
        transform: "translateX(-50%)",
        width: measured ? `${box.widthPct}%` : "0px",
        height: measured ? `${box.heightPct}%` : "0px",
        visibility: measured ? "visible" : "hidden",
      }}
      className="absolute z-30 cursor-grab touch-none rounded-[3px] border border-white/90 shadow-[0_0_0_1px_rgba(0,0,0,0.45)] active:cursor-grabbing"
    >
      {measured && (
        <>
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
        </>
      )}
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
