# Editor Alignment Guides + Snapping (Workstream C) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** When the user drags the hook or captions on the video, alignment guide lines appear and the element snaps to canvas center/edges, platform safe-area boundaries (TikTok/Reels/Shorts), and the other element — Figma/Canva-style — with an 8px threshold, hold-Alt to suspend, and a snap toggle + platform picker.

**Architecture:** Pure, unit-tested math (`snapEngine` / `snapTargets` / `safeAreas`) decides snapping; imperative DOM (`SnapGuides` ref API + `SafeAreaOverlay`) draws it without any React state per pointermove. Hooks into `OverlaySelectionBox`'s existing zero-re-render drag.

**Tech Stack:** Next.js 16 / React 19 / TypeScript / Tailwind v4; vitest for the pure logic (harness already gated in `just check`).

## Global Constraints
- **English-only** for every user-facing string ("Snap", "Safe area", "TikTok"/"Reels"/"Shorts").
- **Zero re-render during drag** — snapping + guides are imperative; never add React state in a pointermove path.
- **No silent fallbacks** — localStorage read failures fall back to defaults explicitly (try/catch that logs or returns a default, never an empty catch hiding a bug).
- **Type contract untouched** — no `models.py`/`packages/shared` changes (this is all web-side, no API change).
- **`just check` green before every commit** (run from PowerShell with PATH refresh:
  `$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")`). Commit from PowerShell, `git commit -F <utf8 msgfile WITHOUT a BOM>`, Conventional Commits, end with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- **Next 16 caveat** — client components only; read `apps/web/node_modules/next/dist/docs/` before any unfamiliar API (you won't need routing here).
- **Branch:** `editor-snapping`. Do not push/merge without user say-so.
- Vitest specs live at `apps/web/lib/**/*.test.ts`; run one with `pnpm --filter web exec vitest run lib/<file>.test.ts`.

---

### Task 1: `safeAreas` — platform safe-zone data + px mapping

**Files:** Create `apps/web/lib/safeAreas.ts`, `apps/web/lib/safeAreas.test.ts`.

**Interfaces — Produces:**
```ts
export type SafePlatform = "tiktok" | "reels" | "shorts";
export interface SafeInsets { top: number; bottom: number; left: number; right: number } // fractions 0..1
export interface SafeBox { top: number; bottom: number; left: number; right: number }     // px in render box
export const SAFE_AREAS: Record<SafePlatform, SafeInsets>;
export const SAFE_PLATFORMS: SafePlatform[];
export function safeBoxPx(insets: SafeInsets, renderW: number, renderH: number): SafeBox;
```
`safeBoxPx` maps insets→px: `{ top: top*H, bottom: bottom*H, left: left*W, right: right*W }`.

- [ ] **Step 1: Failing test** — `apps/web/lib/safeAreas.test.ts`:
```ts
import { describe, expect, it } from "vitest";
import { SAFE_AREAS, SAFE_PLATFORMS, safeBoxPx } from "./safeAreas";

describe("safeAreas", () => {
  it("has the three platforms", () => expect(SAFE_PLATFORMS).toEqual(["tiktok", "reels", "shorts"]));
  it("insets are fractions inside the frame (0<top<bottom<1, 0<left<right<1)", () => {
    for (const p of SAFE_PLATFORMS) {
      const s = SAFE_AREAS[p];
      expect(s.top).toBeGreaterThan(0); expect(s.top).toBeLessThan(s.bottom); expect(s.bottom).toBeLessThan(1);
      expect(s.left).toBeGreaterThan(0); expect(s.left).toBeLessThan(s.right); expect(s.right).toBeLessThan(1);
    }
  });
  it("safeBoxPx maps fractions to px", () => {
    expect(safeBoxPx({ top: 0.1, bottom: 0.8, left: 0.05, right: 0.9 }, 200, 400))
      .toEqual({ top: 40, bottom: 320, left: 10, right: 180 });
  });
});
```
- [ ] **Step 2: Run → FAIL** — `pnpm --filter web exec vitest run lib/safeAreas.test.ts`.
- [ ] **Step 3: Implement** — `apps/web/lib/safeAreas.ts`:
```ts
export type SafePlatform = "tiktok" | "reels" | "shorts";
export interface SafeInsets { top: number; bottom: number; left: number; right: number }
export interface SafeBox { top: number; bottom: number; left: number; right: number }

export const SAFE_PLATFORMS: SafePlatform[] = ["tiktok", "reels", "shorts"];

// Fractions (0..1) of the 1080x1920 frame; the SAFE region is INSIDE these. Design-tunable.
export const SAFE_AREAS: Record<SafePlatform, SafeInsets> = {
  tiktok: { top: 0.06, bottom: 0.83, left: 0.055, right: 0.89 },
  reels: { top: 0.115, bottom: 0.8, left: 0.055, right: 0.945 },
  shorts: { top: 0.2, bottom: 0.8, left: 0.05, right: 0.82 },
};

export function safeBoxPx(insets: SafeInsets, renderW: number, renderH: number): SafeBox {
  return {
    top: insets.top * renderH,
    bottom: insets.bottom * renderH,
    left: insets.left * renderW,
    right: insets.right * renderW,
  };
}
```
- [ ] **Step 4: Run → PASS** (3 passed).
- [ ] **Step 5: `just check` + commit** — `feat(editor): safe-area platform data + px mapping (pure)`.

---

### Task 2: `snapEngine` — the pure snapping core

**Files:** Create `apps/web/lib/snapEngine.ts`, `apps/web/lib/snapEngine.test.ts`.

**Interfaces — Produces:**
```ts
export type Axis = "x" | "y";
export type GuideKind = "center" | "edge" | "safe" | "element";
export interface DragBox { left: number; top: number; width: number; height: number }
export interface SnapTarget { axis: Axis; pos: number; kind: GuideKind }
export interface GuideLine { axis: Axis; pos: number; kind: GuideKind }
export interface SnapResult { left: number; top: number; guides: GuideLine[] }
export const SNAP_THRESHOLD_PX = 8;
export function computeSnap(box: DragBox, targets: SnapTarget[], threshold: number): SnapResult;
```
Per axis, the box features are: x → `left`, `left+width/2`, `left+width`; y → `top`, `top+height/2`, `top+height`. For each axis independently, find the (feature,target) pair with the smallest `|feature - target.pos|` that is `<= threshold`; if found, shift `left` (x) or `top` (y) by `target.pos - feature` and add a `GuideLine{axis, pos: target.pos, kind: target.kind}`. At most one snap per axis (nearest wins). No match on an axis → that axis unchanged, no guide.

- [ ] **Step 1: Failing test** — `apps/web/lib/snapEngine.test.ts`:
```ts
import { describe, expect, it } from "vitest";
import { computeSnap, type SnapTarget } from "./snapEngine";

const box = { left: 100, top: 100, width: 40, height: 20 }; // center-x=120, center-y=110

describe("computeSnap", () => {
  it("snaps center-x to a near vertical center target", () => {
    const t: SnapTarget[] = [{ axis: "x", pos: 124, kind: "center" }]; // 4px from center-x 120
    const r = computeSnap(box, t, 8);
    expect(r.left).toBe(104); // shifted by +4 so center-x lands on 124
    expect(r.guides).toEqual([{ axis: "x", pos: 124, kind: "center" }]);
  });
  it("ignores targets beyond threshold", () => {
    const r = computeSnap(box, [{ axis: "x", pos: 200, kind: "edge" }], 8);
    expect(r.left).toBe(100); expect(r.guides).toEqual([]);
  });
  it("picks the nearest target per axis", () => {
    const t: SnapTarget[] = [
      { axis: "x", pos: 126, kind: "edge" },   // 6px from center-x
      { axis: "x", pos: 122, kind: "center" }, // 2px from center-x — nearer
    ];
    const r = computeSnap(box, t, 8);
    expect(r.left).toBe(102); expect(r.guides).toEqual([{ axis: "x", pos: 122, kind: "center" }]);
  });
  it("snaps a box EDGE (not just center) when it is the nearest feature", () => {
    // left edge = 100; target at 103 (3px) is nearer than center-x→any
    const r = computeSnap(box, [{ axis: "x", pos: 103, kind: "safe" }], 8);
    expect(r.left).toBe(103); expect(r.guides[0]).toEqual({ axis: "x", pos: 103, kind: "safe" });
  });
  it("snaps both axes independently", () => {
    const t: SnapTarget[] = [{ axis: "x", pos: 120, kind: "center" }, { axis: "y", pos: 112, kind: "center" }];
    const r = computeSnap(box, t, 8);
    expect(r.left).toBe(100); // center-x already 120
    expect(r.top).toBe(102);  // center-y 110 → 112
    expect(r.guides.length).toBe(2);
  });
  it("empty targets → identity", () => {
    const r = computeSnap(box, [], 8);
    expect(r).toEqual({ left: 100, top: 100, guides: [] });
  });
});
```
- [ ] **Step 2: Run → FAIL**.
- [ ] **Step 3: Implement** — `apps/web/lib/snapEngine.ts`:
```ts
export type Axis = "x" | "y";
export type GuideKind = "center" | "edge" | "safe" | "element";
export interface DragBox { left: number; top: number; width: number; height: number }
export interface SnapTarget { axis: Axis; pos: number; kind: GuideKind }
export interface GuideLine { axis: Axis; pos: number; kind: GuideKind }
export interface SnapResult { left: number; top: number; guides: GuideLine[] }

export const SNAP_THRESHOLD_PX = 8;

function snapAxis(
  features: number[],
  targets: SnapTarget[],
  threshold: number,
): { delta: number; guide: GuideLine } | null {
  let best: { delta: number; guide: GuideLine; dist: number } | null = null;
  for (const t of targets) {
    for (const f of features) {
      const dist = Math.abs(f - t.pos);
      if (dist <= threshold && (best === null || dist < best.dist)) {
        best = { delta: t.pos - f, dist, guide: { axis: t.axis, pos: t.pos, kind: t.kind } };
      }
    }
  }
  return best ? { delta: best.delta, guide: best.guide } : null;
}

export function computeSnap(box: DragBox, targets: SnapTarget[], threshold: number): SnapResult {
  const guides: GuideLine[] = [];
  let { left, top } = box;
  const xs = snapAxis(
    [box.left, box.left + box.width / 2, box.left + box.width],
    targets.filter((t) => t.axis === "x"),
    threshold,
  );
  if (xs) { left += xs.delta; guides.push(xs.guide); }
  const ys = snapAxis(
    [box.top, box.top + box.height / 2, box.top + box.height],
    targets.filter((t) => t.axis === "y"),
    threshold,
  );
  if (ys) { top += ys.delta; guides.push(ys.guide); }
  return { left, top, guides };
}
```
- [ ] **Step 4: Run → PASS** (6 passed).
- [ ] **Step 5: `just check` + commit** — `feat(editor): pure snap engine (nearest-line snapping)`.

---

### Task 3: `snapTargets` — build the candidate lines

**Files:** Create `apps/web/lib/snapTargets.ts`, `apps/web/lib/snapTargets.test.ts`.

**Interfaces — Consumes:** `SnapTarget` from `./snapEngine`, `SafeBox` from `./safeAreas`. **Produces:**
```ts
export interface RectPx { left: number; top: number; width: number; height: number }
export function buildTargets(renderW: number, renderH: number, other: RectPx | null, safe: SafeBox | null): SnapTarget[];
```
Always emits: centers `{x:W/2,"center"},{y:H/2,"center"}`; edges `{x:0},{x:W},{y:0},{y:H}` (kind "edge").
If `safe`: `{x:left},{x:right},{y:top},{y:bottom}` (kind "safe"). If `other`: its center-x, left, right (x, "element") and center-y, top, bottom (y, "element").

- [ ] **Step 1: Failing test** — `apps/web/lib/snapTargets.test.ts`:
```ts
import { describe, expect, it } from "vitest";
import { buildTargets } from "./snapTargets";

describe("buildTargets", () => {
  it("emits canvas centers + 4 edges with no other/safe", () => {
    const t = buildTargets(200, 400, null, null);
    expect(t).toContainEqual({ axis: "x", pos: 100, kind: "center" });
    expect(t).toContainEqual({ axis: "y", pos: 200, kind: "center" });
    expect(t).toContainEqual({ axis: "x", pos: 0, kind: "edge" });
    expect(t).toContainEqual({ axis: "x", pos: 200, kind: "edge" });
    expect(t).toContainEqual({ axis: "y", pos: 0, kind: "edge" });
    expect(t).toContainEqual({ axis: "y", pos: 400, kind: "edge" });
    expect(t.filter((x) => x.kind === "safe")).toEqual([]);
    expect(t.filter((x) => x.kind === "element")).toEqual([]);
  });
  it("adds safe-area lines", () => {
    const t = buildTargets(200, 400, null, { top: 40, bottom: 320, left: 10, right: 180 });
    expect(t).toContainEqual({ axis: "y", pos: 40, kind: "safe" });
    expect(t).toContainEqual({ axis: "y", pos: 320, kind: "safe" });
    expect(t).toContainEqual({ axis: "x", pos: 10, kind: "safe" });
    expect(t).toContainEqual({ axis: "x", pos: 180, kind: "safe" });
  });
  it("adds the other element's center/edges", () => {
    const t = buildTargets(200, 400, { left: 60, top: 100, width: 80, height: 40 }, null);
    expect(t).toContainEqual({ axis: "x", pos: 100, kind: "element" }); // center-x 60+40
    expect(t).toContainEqual({ axis: "x", pos: 60, kind: "element" });
    expect(t).toContainEqual({ axis: "x", pos: 140, kind: "element" });
    expect(t).toContainEqual({ axis: "y", pos: 120, kind: "element" }); // center-y 100+20
    expect(t).toContainEqual({ axis: "y", pos: 100, kind: "element" });
    expect(t).toContainEqual({ axis: "y", pos: 140, kind: "element" });
  });
});
```
- [ ] **Step 2: Run → FAIL**.
- [ ] **Step 3: Implement** — `apps/web/lib/snapTargets.ts`:
```ts
import type { SafeBox } from "./safeAreas";
import type { SnapTarget } from "./snapEngine";

export interface RectPx { left: number; top: number; width: number; height: number }

export function buildTargets(
  renderW: number,
  renderH: number,
  other: RectPx | null,
  safe: SafeBox | null,
): SnapTarget[] {
  const t: SnapTarget[] = [
    { axis: "x", pos: renderW / 2, kind: "center" },
    { axis: "y", pos: renderH / 2, kind: "center" },
    { axis: "x", pos: 0, kind: "edge" },
    { axis: "x", pos: renderW, kind: "edge" },
    { axis: "y", pos: 0, kind: "edge" },
    { axis: "y", pos: renderH, kind: "edge" },
  ];
  if (safe) {
    t.push({ axis: "x", pos: safe.left, kind: "safe" }, { axis: "x", pos: safe.right, kind: "safe" });
    t.push({ axis: "y", pos: safe.top, kind: "safe" }, { axis: "y", pos: safe.bottom, kind: "safe" });
  }
  if (other) {
    const cx = other.left + other.width / 2;
    const cy = other.top + other.height / 2;
    t.push({ axis: "x", pos: cx, kind: "element" }, { axis: "x", pos: other.left, kind: "element" }, { axis: "x", pos: other.left + other.width, kind: "element" });
    t.push({ axis: "y", pos: cy, kind: "element" }, { axis: "y", pos: other.top, kind: "element" }, { axis: "y", pos: other.top + other.height, kind: "element" });
  }
  return t;
}
```
- [ ] **Step 4: Run → PASS** (3 passed).
- [ ] **Step 5: `just check` + commit** — `feat(editor): build snap targets (centers/edges/safe/element)`.

---

### Task 4: `SnapGuides` — imperative guide-line overlay

**Files:** Create `apps/web/components/editor/SnapGuides.tsx`.

**Interfaces — Consumes:** `GuideLine` from `@/lib/snapEngine`. **Produces:**
```ts
export interface SnapGuidesHandle { show(lines: GuideLine[], renderW: number, renderH: number): void; hide(): void }
// default export: forwardRef<SnapGuidesHandle, {}> component
```

- [ ] **Step 1: Build the component** (`apps/web/components/editor/SnapGuides.tsx`): a `forwardRef` component rendering `absolute inset-0 pointer-events-none z-20` over the render box, with a small fixed pool (e.g. 4) of hidden line `div`s. `show(lines, renderW, renderH)` maps each `GuideLine` to a pool div: vertical (`axis:"x"`) → `left: pos/renderW*100%`, `top:0`, `width:1px`, `height:100%`; horizontal (`axis:"y"`) → `top: pos/renderH*100%`, `left:0`, `height:1px`, `width:100%`; color magenta (`#FF2D9B`), `opacity:1`; extra pool divs `opacity:0`. `hide()` sets all pool divs `opacity:0`. Use `useImperativeHandle`. NO React state per call (mutate refs/style only). English-only (no text).
- [ ] **Step 2: Typecheck** — `pnpm --filter web exec tsc --noEmit` clean.
- [ ] **Step 3: `just check` + commit** — `feat(editor): imperative snap-guide overlay`.

---

### Task 5: `SafeAreaOverlay` — platform safe-zone visualization

**Files:** Create `apps/web/components/editor/SafeAreaOverlay.tsx`.

**Interfaces — Consumes:** `SafePlatform`, `SAFE_AREAS` from `@/lib/safeAreas`. **Produces:**
```ts
function SafeAreaOverlay({ platform }: { platform: SafePlatform | null }): JSX.Element | null
```

- [ ] **Step 1: Build the component**: returns `null` when `platform` is null. Otherwise renders `absolute inset-0 pointer-events-none z-10` and a dashed inset rectangle positioned from `SAFE_AREAS[platform]` as %: `top: top*100%`, `left: left*100%`, `right: (1-right)*100%`, `bottom: (1-bottom)*100%` (use `inset` or explicit top/left/width/height). Style: `border border-dashed border-white/50`, with a small label chip (`"TikTok safe"` / `"Reels safe"` / `"Shorts safe"`, capitalize platform) at the top-left of the rect, English-only. Subtle so it doesn't fight the video.
- [ ] **Step 2: Typecheck** clean.
- [ ] **Step 3: `just check` + commit** — `feat(editor): safe-area overlay on canvas`.

---

### Task 6: `SnapControls` — toggle + platform picker (localStorage)

**Files:** Create `apps/web/components/editor/SnapControls.tsx`, `apps/web/lib/editorPrefs.ts` (+ `editorPrefs.test.ts`).

**Interfaces — Produces:**
```ts
// editorPrefs.ts
export function readSnapPref(): boolean;             // default true
export function writeSnapPref(v: boolean): void;
export function readSafePref(): SafePlatform | null; // default null
export function writeSafePref(v: SafePlatform | null): void;
// SnapControls.tsx
function SnapControls({ snapEnabled, onSnapToggle, platform, onPlatformChange }: {
  snapEnabled: boolean; onSnapToggle: (v: boolean) => void;
  platform: SafePlatform | null; onPlatformChange: (p: SafePlatform | null) => void;
}): JSX.Element
```

- [ ] **Step 1: Failing test for prefs** — `apps/web/lib/editorPrefs.test.ts` (vitest, node env — stub a minimal localStorage):
```ts
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { readSafePref, readSnapPref, writeSafePref, writeSnapPref } from "./editorPrefs";

beforeEach(() => {
  const store: Record<string, string> = {};
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => (k in store ? store[k] : null),
    setItem: (k: string, v: string) => { store[k] = v; },
    removeItem: (k: string) => { delete store[k]; },
  });
});
afterEach(() => vi.unstubAllGlobals());

describe("editorPrefs", () => {
  it("snap defaults true, round-trips", () => {
    expect(readSnapPref()).toBe(true);
    writeSnapPref(false); expect(readSnapPref()).toBe(false);
  });
  it("safe defaults null, round-trips a platform and back to null", () => {
    expect(readSafePref()).toBe(null);
    writeSafePref("tiktok"); expect(readSafePref()).toBe("tiktok");
    writeSafePref(null); expect(readSafePref()).toBe(null);
  });
  it("ignores a corrupt safe value (returns null, no throw)", () => {
    localStorage.setItem("quip.editor.safe", "garbage");
    expect(readSafePref()).toBe(null);
  });
});
```
- [ ] **Step 2: Run → FAIL**.
- [ ] **Step 3: Implement `editorPrefs.ts`**:
```ts
import { SAFE_PLATFORMS, type SafePlatform } from "./safeAreas";

const SNAP_KEY = "quip.editor.snap";
const SAFE_KEY = "quip.editor.safe";

function safeLocalStorage(): Storage | null {
  try { return typeof localStorage !== "undefined" ? localStorage : null; } catch { return null; }
}

export function readSnapPref(): boolean {
  const ls = safeLocalStorage();
  return ls?.getItem(SNAP_KEY) === "off" ? false : true; // default true
}
export function writeSnapPref(v: boolean): void {
  safeLocalStorage()?.setItem(SNAP_KEY, v ? "on" : "off");
}
export function readSafePref(): SafePlatform | null {
  const v = safeLocalStorage()?.getItem(SAFE_KEY);
  return v && (SAFE_PLATFORMS as string[]).includes(v) ? (v as SafePlatform) : null;
}
export function writeSafePref(v: SafePlatform | null): void {
  const ls = safeLocalStorage();
  if (!ls) return;
  if (v) ls.setItem(SAFE_KEY, v); else ls.removeItem(SAFE_KEY);
}
```
- [ ] **Step 4: Run → PASS** (3 passed).
- [ ] **Step 5: Build `SnapControls.tsx`**: a small unobtrusive control row (for placement over the canvas top-right): a magnet toggle button (filled/accent when `snapEnabled`, calls `onSnapToggle(!snapEnabled)`, `aria-pressed`, `title="Snap (S)"` — wiring the `S` key is optional, not required) and a segmented picker `Off · TikTok · Reels · Shorts` calling `onPlatformChange(null|"tiktok"|"reels"|"shorts")`, the active one highlighted. English-only labels. Use lucide `Magnet` icon if available, else text "Snap". Keep it visually light (semi-transparent chip).
- [ ] **Step 6: Typecheck + `just check` + commit** — `feat(editor): snap controls (toggle + safe-area picker) + localStorage prefs`.

---

### Task 7: Wire snapping into the drag + canvas

**Files:** Modify `apps/web/components/editor/OverlaySelectionBox.tsx`, `apps/web/components/editor/ClipEditorScreen.tsx`.

**Interfaces — Consumes:** all of Tasks 1-6. `OverlaySelectionBox` gains props:
```ts
otherRect?: OverlayRect | null;     // the OTHER element's render-box-fraction rect (topPct/leftPct/widthPct/heightPct)
safeInsets?: SafeInsets | null;     // active platform insets, or null
snapEnabled?: boolean;              // default true
guidesRef?: React.RefObject<SnapGuidesHandle | null>;
```

- [ ] **Step 1: OverlaySelectionBox — snap in `onBodyMove`**. After computing the raw `left`/`top` (px in render box) and BEFORE writing `node.style.left/top`, insert:
```ts
let snapLeft = left, snapTop = top;
if (snapEnabled && !e.altKey) {
  const W = box.width, H = box.height;
  const other = otherRect
    ? { left: (otherRect.leftPct / 100) * W, top: (otherRect.topPct / 100) * H,
        width: (otherRect.widthPct / 100) * W, height: (otherRect.heightPct / 100) * H }
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
node.style.left = `${(snapLeft / box.width) * 100}%`;
node.style.top = `${(snapTop / box.height) * 100}%`;
node.style.bottom = "auto";
```
Imports: `buildTargets` from `@/lib/snapTargets`, `computeSnap`, `SNAP_THRESHOLD_PX` from `@/lib/snapEngine`, `safeBoxPx`, `type SafeInsets` from `@/lib/safeAreas`, `type SnapGuidesHandle` from `./SnapGuides`. Add the four new optional props to the interface + destructure (with defaults `snapEnabled = true`). In `onBodyUp` and any cancel path, call `guidesRef?.current?.hide()` so guides clear on release. The commit math (`onBodyUp` reading the final rect) is unchanged — it now reflects the snapped box.

- [ ] **Step 2: ClipEditorScreen — state + render + props.**
  - Add state: `const [snapEnabled, setSnapEnabled] = useState(true);` and `const [safePlatform, setSafePlatform] = useState<SafePlatform | null>(null);` initialized from `readSnapPref()`/`readSafePref()` in a mount effect (not in `useState` initializer if SSR-sensitive — read in `useEffect` then set). Wrap the setters to also `writeSnapPref`/`writeSafePref`.
  - `const guidesRef = useRef<SnapGuidesHandle | null>(null);`
  - `const safeInsets = safePlatform ? SAFE_AREAS[safePlatform] : null;`
  - Inside the PreviewPlayer children (the render box, where `OverlaySelectionBox`es + libass live), render `<SafeAreaOverlay platform={safePlatform} />` and `<SnapGuides ref={guidesRef} />`.
  - Render `<SnapControls .../>` overlaid on the canvas (e.g. top-right of the EditorCanvas / over the video) wired to the persisted setters.
  - Pass to the CAPTION `OverlaySelectionBox`: `otherRect={subRects.hook}`, and to the HOOK one: `otherRect={subRects.caption}`; both get `safeInsets={safeInsets}`, `snapEnabled={snapEnabled}`, `guidesRef={guidesRef}`.
  - Imports: `SAFE_AREAS`, `type SafePlatform` from `@/lib/safeAreas`; `readSnapPref/writeSnapPref/readSafePref/writeSafePref` from `@/lib/editorPrefs`; `SnapGuides`, `type SnapGuidesHandle` from `./SnapGuides`; `SafeAreaOverlay`, `SnapControls`.
- [ ] **Step 3: Typecheck + lint** — `pnpm --filter web exec tsc --noEmit` and `pnpm --filter web lint` clean.
- [ ] **Step 4: `just check` green + commit** — `feat(editor): wire snapping + guides + safe areas into the canvas drag`.
- [ ] **Step 5: Human dogfood (note in report)** — login-gated: drag hook/caption → magenta guide appears + snaps at center/edges; snaps to the other element; pick a platform → safe overlay shows + snaps to it; hold Alt → no snap; toggle off → disabled; smooth, commit persists snapped position; reload keeps the toggle/platform choice.

---

## Self-review
**Spec coverage:** snapEngine→T2; snapTargets→T3; safeAreas (data + px)→T1; SnapGuides→T4; SafeAreaOverlay→T5; SnapControls + localStorage→T6; OverlaySelectionBox/ClipEditorScreen wiring (Alt-suspend, toggle, other-element, threshold, guides, commit)→T7. Threshold 8px = `SNAP_THRESHOLD_PX` (T2, used T7). Magenta guides (T4). All covered.
**Placeholder scan:** none — every code/test step has literal code; component steps (T4/T5/T6.5) specify exact classes/positions/behavior, not "TBD".
**Type consistency:** `SnapTarget`/`GuideLine`/`DragBox`/`SnapResult` defined T2, consumed T3/T4/T7; `SafeInsets`/`SafeBox`/`SafePlatform`/`safeBoxPx`/`SAFE_AREAS` T1, consumed T3/T6/T7; `RectPx`/`buildTargets` T3 used T7; `SnapGuidesHandle` T4 used T7; `readSnapPref` etc. T6 used T7; `OverlayRect` is the existing type from `@/lib/overlayBox`.

## Out of scope (later)
Cross-project persistence of snap/safe prefs (WS-D — v1 localStorage); snapping resize/width gestures; distance labels; a keyboard shortcut for the snap toggle (optional).
