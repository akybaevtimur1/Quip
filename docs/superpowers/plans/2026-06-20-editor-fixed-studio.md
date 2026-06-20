# Editor "Fixed Studio" (Workstream A) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the clip editor as a fixed 3-zone "Fixed Studio" where the 9:16 canvas is sized by the viewport and never by panel content (killing the framing-panel "video shrinks" bug), with instant in-page clip switching, a de-overloaded inspector, and the perf/keyboard wins that fall out of the restructure.

**Architecture:** Keep ALL of `ClipEditorScreen`'s mutation/ASS-reconciliation state machine intact (it's correctness-critical); only re-home the JSX into new presentational components (`EditorRail`, `EditorCanvas`, `Inspector`) and convert `clipId` from a route param into editor state. Pure helpers (prefetch cache, frame-identity stabilizer, keyboard dispatcher) are extracted and unit-tested.

**Tech Stack:** Next.js 16 (App Router, React 19), TypeScript, Tailwind v4, Python worker (FastAPI/Pydantic) for preset names. New: vitest for web unit tests.

## Global Constraints

- **English-only** for every new/edited user-facing string (UI, toasts, labels, errors). Verbatim from CLAUDE.md.
- **Type contract is codegen**: never hand-edit `packages/shared/*`; contract changes go in `services/worker/app/models.py` → `just types`. WS-A changes NO contract types.
- **No silent fallbacks**: errors surface (log/visible state), never `except: pass` / swallowed catch.
- **`just check` green before every commit** (run from PowerShell; pre-commit hook needs `just` on the refreshed PATH). PATH refresh each PS call: `$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")`.
- **Next 16 is not the Next you know**: read `apps/web/node_modules/next/dist/docs/` for any routing/client-component API before using it (esp. shallow URL updates in Task 7).
- **Reframe frame-grid Δ=0**: WS-A does not touch `stage3_reframe`/`stage5_render`/`reframe_cache`. Live Frame mode only changes *when* `setCropOverride` is called, not the crop math.
- **Branch**: all work on `editor-fixed-studio` (already created; spec already committed there). Do NOT push/merge to `main` (auto-deploys) without explicit user approval.
- **Commits**: Conventional Commits; end every commit message with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- **Verify visually**: interactive changes are dogfooded in the live authed editor (Playwright MCP persistent browser — see memory `live-editor-browser-access`), not assumed from green types.

---

### Task 1: Stabilize the canvas (framing-bug fix, shippable on its own)

Fixes the #1 trust bug with the smallest possible change, inside the *current* tab layout, before the shell is restructured. Decouples the preview's height from the tab column's content height.

**Files:**
- Modify: `apps/web/components/editor/ClipEditorScreen.tsx` (main grid `:997`, preview wrapper `:1001-1002`, right column `:1135`, tab panel `:1160`)
- Modify: `apps/web/components/editor/FrameTab.tsx:78` (panel root: ensure it scrolls internally, never sets the row's min-content)

**Interfaces:**
- Consumes: nothing new.
- Produces: a stable-canvas layout contract later tasks preserve — the editor body row is `min-h-0 overflow-hidden`; the canvas height derives from the row, not from sibling content; inspector/tab content scrolls internally.

- [ ] **Step 1: Reproduce the bug in the live editor (evidence baseline)**

Drive the live authed editor (Playwright MCP). Open a clip, screenshot the 9:16 preview on the **Captions** tab, then click **Frame** and screenshot again. Confirm the video box visibly changes height. Save both as `before-captions.png` / `before-frame.png`.

- [ ] **Step 2: Decouple the row from tab content**

In `ClipEditorScreen.tsx` `<main>` (currently `:997`):
```tsx
// BEFORE: lg:overflow-visible lets the shared grid row grow to the tallest tab
// AFTER: the body never overflows; each side scrolls internally
<main className="grid min-h-0 grid-cols-1 gap-4 overflow-hidden p-4 lg:grid-cols-[minmax(280px,380px)_minmax(0,1fr)]">
```
Remove `overflow-y-auto` + `lg:overflow-visible`; add `overflow-hidden`. (On mobile the two stacked zones each get their own scroll in Step 3/4.)

- [ ] **Step 3: Give the preview an independent, viewport-based height**

Preview wrapper (currently `:1001-1002`) — drop the `flex-1`-of-shared-row coupling; the canvas box sizes to the column with its own min-height-0:
```tsx
<div className="flex min-h-0 flex-col bg-bg lg:static">
  <div className="grid min-h-0 flex-1 place-items-center">
    <PreviewPlayer …/>   {/* video: w-full max-h-full aspect-… object-contain */}
  </div>
  {edit && <div className="shrink-0"><FitTimeline …/></div>}
</div>
```
Verify `PreviewPlayer`'s root keeps `max-h-full max-w-full` + the aspect class so it letterboxes inside the stable box (it already does — `aspectClass` at `ClipEditorScreen.tsx:927-930`).

- [ ] **Step 4: Make the right (tab) column scroll internally**

Tab column (`:1135`) and tab-panel container (`:1160`):
```tsx
<div className="flex min-h-0 flex-col gap-3 overflow-hidden">
  …banner…  …tab bar…
  <div className="flex min-h-0 flex-1 flex-col overflow-y-auto rounded-xl border border-line bg-surface p-4">
    {/* active tab */}
  </div>
</div>
```
In `FrameTab.tsx:78` keep `overflow-y-auto` but ensure the root is `min-h-0 flex-1` so it fills (not expands) the panel.

- [ ] **Step 5: Typecheck**

Run (PowerShell, PATH refreshed): `pnpm --filter web exec tsc --noEmit`
Expected: no errors.

- [ ] **Step 6: Verify the fix in the live editor**

Repeat Step 1 navigation. Screenshot Captions → Frame again (`after-captions.png` / `after-frame.png`). **Acceptance: the video box is pixel-identical in height across all 5 tabs and on 9:16/1:1/4:5/16:9.** Toggle a narrow viewport (resize to ~700px) and confirm the same.

- [ ] **Step 7: Commit**

```powershell
$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
git add apps/web/components/editor/ClipEditorScreen.tsx apps/web/components/editor/FrameTab.tsx
git commit -F <msg-file>   # "fix(editor): decouple preview size from panel content (framing-panel no longer resizes the video)"
```

---

### Task 2: Add a vitest harness to `apps/web` and gate it

Web has no JS test runner; the pure helpers in Tasks 3–5 need TDD per the project rules.

**Files:**
- Create: `apps/web/vitest.config.ts`
- Modify: `apps/web/package.json` (devDeps + `test` script)
- Modify: `justfile` (add `test-web` to the `check` gate)
- Create: `apps/web/lib/__tests__/smoke.test.ts`

**Interfaces:**
- Produces: `pnpm --filter web exec vitest run` runs web unit tests; `just check` includes them.

- [ ] **Step 1: Add vitest config**

`apps/web/vitest.config.ts`:
```ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: { environment: "node", include: ["lib/**/*.test.ts"] },
});
```

- [ ] **Step 2: Add devDep + script**

`apps/web/package.json`: add `"vitest": "^3"` to `devDependencies` and `"test": "vitest run"` to `scripts`. Then install:
```powershell
$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
pnpm install
```

- [ ] **Step 3: Smoke test (proves the harness runs)**

`apps/web/lib/__tests__/smoke.test.ts`:
```ts
import { describe, expect, it } from "vitest";
describe("harness", () => { it("runs", () => expect(1 + 1).toBe(2)); });
```
Run: `pnpm --filter web exec vitest run` → Expected: 1 passed.

- [ ] **Step 4: Wire into the gate**

`justfile`: change `test-unit:` group so `check` also runs web tests. Add:
```just
test-web:
    pnpm --filter web exec vitest run
```
and update `check: lint typecheck test-unit test-web anti-drift`.

- [ ] **Step 5: Run the gate**

Run: `just check` → Expected: all green (incl. `test-web`).

- [ ] **Step 6: Commit**

```
git add apps/web/vitest.config.ts apps/web/package.json apps/web/lib/__tests__/smoke.test.ts justfile pnpm-lock.yaml
# chore(web): add vitest harness for pure-logic unit tests + gate in just check
```

---

### Task 3: `frameIdentity` — stable crop-state object identity

Stops `PreviewPlayer` re-rendering every ~250ms timeupdate tick when the resolved crop is unchanged.

**Files:**
- Create: `apps/web/lib/frameIdentity.ts`
- Create: `apps/web/lib/frameIdentity.test.ts`
- Modify (consumer): `apps/web/components/editor/ClipEditorScreen.tsx` (the `frame` useMemo, `:898-924`)

**Interfaces:**
- Produces: `frameEqual(a: FrameState | null, b: FrameState | null): boolean` and `stableFrame(prev: FrameState | null, next: FrameState | null): FrameState | null` (returns `prev` when `frameEqual`). `FrameState = { mode: "fill"|"fit"|"split"; cx: number; cxB: number }` (imported from `./PreviewPlayer`).

- [ ] **Step 1: Failing test**

`apps/web/lib/frameIdentity.test.ts`:
```ts
import { describe, expect, it } from "vitest";
import { frameEqual, stableFrame } from "./frameIdentity";

const f = (cx: number) => ({ mode: "fill" as const, cx, cxB: 0.7 });

describe("frameIdentity", () => {
  it("equal when fields match", () => expect(frameEqual(f(0.5), f(0.5))).toBe(true));
  it("not equal when cx differs", () => expect(frameEqual(f(0.5), f(0.51))).toBe(false));
  it("null handling", () => { expect(frameEqual(null, null)).toBe(true); expect(frameEqual(null, f(0.5))).toBe(false); });
  it("stableFrame returns prev ref when equal", () => { const p = f(0.5); expect(stableFrame(p, f(0.5))).toBe(p); });
  it("stableFrame returns next when changed", () => { const n = f(0.6); expect(stableFrame(f(0.5), n)).toBe(n); });
});
```

- [ ] **Step 2: Run → FAIL**

Run: `pnpm --filter web exec vitest run lib/frameIdentity.test.ts` → Expected: FAIL (module not found).

- [ ] **Step 3: Implement**

`apps/web/lib/frameIdentity.ts`:
```ts
import type { FrameState } from "../components/editor/PreviewPlayer";

export function frameEqual(a: FrameState | null, b: FrameState | null): boolean {
  if (a === b) return true;
  if (!a || !b) return false;
  return a.mode === b.mode && a.cx === b.cx && a.cxB === b.cxB;
}

export function stableFrame(prev: FrameState | null, next: FrameState | null): FrameState | null {
  return frameEqual(prev, next) ? prev : next;
}
```

- [ ] **Step 4: Run → PASS**

Run: `pnpm --filter web exec vitest run lib/frameIdentity.test.ts` → Expected: 5 passed.

- [ ] **Step 5: Wire the consumer**

In `ClipEditorScreen.tsx`, hold the previous frame in a ref and pass `frame` through `stableFrame` so the memo returns a stable reference when the crop didn't change:
```tsx
const prevFrameRef = useRef<FrameState | null>(null);
const frame = useMemo<FrameState | null>(() => {
  const next = /* …existing computation… */;
  const stable = stableFrame(prevFrameRef.current, next);
  prevFrameRef.current = stable;
  return stable;
}, [edit, outerStart, outerEnd, rawRegions, nowSec]);
```
(Reading/writing a ref inside useMemo is acceptable here — it only memoizes identity, never triggers renders.)

- [ ] **Step 6: Gate + commit**

Run: `just check` (green). Commit: `git add apps/web/lib/frameIdentity.ts apps/web/lib/frameIdentity.test.ts apps/web/components/editor/ClipEditorScreen.tsx` → `perf(editor): stabilize resolved-frame identity to cut per-tick re-renders`.

---

### Task 4: `clipCache` — bounded prefetch cache for instant clip switching

**Files:**
- Create: `apps/web/lib/clipCache.ts`
- Create: `apps/web/lib/clipCache.test.ts`

**Interfaces:**
- Produces: `createClipCache<T>(max: number)` → `{ get(id): T | undefined; set(id, v): void; has(id): boolean; size(): number }`. LRU-ish: when over `max`, evict the oldest-inserted. Used in Task 7 to hold `{ edit, ass, words, regions }` per clipId.

- [ ] **Step 1: Failing test**

`apps/web/lib/clipCache.test.ts`:
```ts
import { describe, expect, it } from "vitest";
import { createClipCache } from "./clipCache";

describe("clipCache", () => {
  it("stores and reads", () => { const c = createClipCache<number>(2); c.set("a", 1); expect(c.get("a")).toBe(1); expect(c.has("a")).toBe(true); });
  it("evicts oldest beyond max", () => {
    const c = createClipCache<number>(2);
    c.set("a", 1); c.set("b", 2); c.set("c", 3);
    expect(c.has("a")).toBe(false); expect(c.has("b")).toBe(true); expect(c.has("c")).toBe(true); expect(c.size()).toBe(2);
  });
  it("re-set refreshes recency", () => {
    const c = createClipCache<number>(2);
    c.set("a", 1); c.set("b", 2); c.set("a", 1); c.set("c", 3);
    expect(c.has("a")).toBe(true); expect(c.has("b")).toBe(false);
  });
});
```

- [ ] **Step 2: Run → FAIL** (`pnpm --filter web exec vitest run lib/clipCache.test.ts`).

- [ ] **Step 3: Implement**

`apps/web/lib/clipCache.ts`:
```ts
export interface ClipCache<T> {
  get(id: string): T | undefined;
  set(id: string, v: T): void;
  has(id: string): boolean;
  size(): number;
}

export function createClipCache<T>(max: number): ClipCache<T> {
  const m = new Map<string, T>(); // Map preserves insertion order → front = oldest
  return {
    get: (id) => m.get(id),
    has: (id) => m.has(id),
    size: () => m.size,
    set(id, v) {
      if (m.has(id)) m.delete(id);     // refresh recency
      m.set(id, v);
      while (m.size > max) m.delete(m.keys().next().value as string);
    },
  };
}
```

- [ ] **Step 4: Run → PASS** (3 passed).

- [ ] **Step 5: Gate + commit**

`just check` → commit `feat(editor): bounded clip prefetch cache (pure)`.

---

### Task 5: Keyboard-shortcut dispatcher (pure map + hook)

**Files:**
- Create: `apps/web/lib/editorShortcuts.ts` (pure key→action resolver)
- Create: `apps/web/lib/editorShortcuts.test.ts`
- Create: `apps/web/components/editor/useEditorShortcuts.ts` (thin hook wiring `keydown`)

**Interfaces:**
- Produces: `resolveShortcut(e: { key: string; target: { tagName?: string; isContentEditable?: boolean } }): EditorAction | null` where `EditorAction = "playPause" | "prevClip" | "nextClip" | "render" | "closeOverlay" | { tab: number }`. Returns `null` when focus is in an input/textarea/contenteditable (typing must not trigger shortcuts). `useEditorShortcuts(handlers)` calls the matching handler.

- [ ] **Step 1: Failing test**

`apps/web/lib/editorShortcuts.test.ts`:
```ts
import { describe, expect, it } from "vitest";
import { resolveShortcut } from "./editorShortcuts";

const ev = (key: string, tag = "BODY", ce = false) => ({ key, target: { tagName: tag, isContentEditable: ce } });

describe("resolveShortcut", () => {
  it("space → playPause", () => expect(resolveShortcut(ev(" "))).toBe("playPause"));
  it("brackets → prev/next clip", () => { expect(resolveShortcut(ev("["))).toBe("prevClip"); expect(resolveShortcut(ev("]"))).toBe("nextClip"); });
  it("r → render", () => expect(resolveShortcut(ev("r"))).toBe("render"));
  it("Escape → closeOverlay", () => expect(resolveShortcut(ev("Escape"))).toBe("closeOverlay"));
  it("digits → tab index", () => expect(resolveShortcut(ev("3"))).toEqual({ tab: 3 }));
  it("ignores when typing in input", () => expect(resolveShortcut(ev(" ", "INPUT"))).toBeNull());
  it("ignores when contenteditable", () => expect(resolveShortcut(ev("r", "DIV", true))).toBeNull());
  it("unknown key → null", () => expect(resolveShortcut(ev("q"))).toBeNull());
});
```

- [ ] **Step 2: Run → FAIL**.

- [ ] **Step 3: Implement the pure resolver**

`apps/web/lib/editorShortcuts.ts`:
```ts
export type EditorAction =
  | "playPause" | "prevClip" | "nextClip" | "render" | "closeOverlay" | { tab: number };

export function resolveShortcut(e: {
  key: string;
  target: { tagName?: string; isContentEditable?: boolean };
}): EditorAction | null {
  const t = e.target;
  if (t.isContentEditable || t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT") return null;
  switch (e.key) {
    case " ": return "playPause";
    case "[": return "prevClip";
    case "]": return "nextClip";
    case "r": case "R": return "render";
    case "Escape": return "closeOverlay";
    default:
      if (/^[1-6]$/.test(e.key)) return { tab: Number(e.key) };
      return null;
  }
}
```

- [ ] **Step 4: Run → PASS** (8 passed).

- [ ] **Step 5: Hook (wired in the shell during Task 6)**

`apps/web/components/editor/useEditorShortcuts.ts`:
```tsx
import { useEffect } from "react";
import { type EditorAction, resolveShortcut } from "@/lib/editorShortcuts";

export function useEditorShortcuts(dispatch: (a: EditorAction) => void) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const action = resolveShortcut({
        key: e.key,
        target: { tagName: target?.tagName, isContentEditable: target?.isContentEditable },
      });
      if (action === null) return;
      if (action === "playPause") e.preventDefault(); // stop page scroll on Space
      dispatch(action);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [dispatch]);
}
```

- [ ] **Step 6: Gate + commit**

`just check` → commit `feat(editor): keyboard-shortcut resolver + hook (pure-tested)`.

---

### Task 6: Extract the Fixed-Studio shell (`EditorRail`, `Inspector`, `EditorCanvas`)

Move the existing tab bodies into a 3-zone shell: a left icon-rail replaces the top tab-bar; a fixed-width contextual inspector on the right; a dedicated canvas component in the center. **No behavior change** — same handlers, same components, re-homed. Wire the shortcut hook.

**Files:**
- Create: `apps/web/components/editor/EditorRail.tsx`
- Create: `apps/web/components/editor/Inspector.tsx`
- Create: `apps/web/components/editor/EditorCanvas.tsx`
- Modify: `apps/web/components/editor/ClipEditorScreen.tsx` (compose the three; remove the old top tab-bar; keep all state/handlers)

**Interfaces:**
- `EditorRail`: props `{ active: Tab; onSelect(tab: Tab): void; agentActive?: boolean }` — renders the 6 items (Agent/Captions/Hook/Style/Frame/Presets) as an icon+label vertical rail with an active state and a badge dot slot on Agent (inert in A; `agentActive` reserved for WS-B). `Tab` extended to include `"presets"`.
- `Inspector`: props `{ active: Tab; children: ReactNode; onClose?(): void; overlay?: boolean }` — fixed-width (`--inspector-w: 360px`) container, `overflow-hidden` + inner `overflow-y-auto`; when `overlay` (narrow viewport) it renders as an absolutely-positioned right sheet over the canvas gutter with a close button. The parent passes the active panel as children.
- `EditorCanvas`: props `{ children: ReactNode; aspectClass: string }` — the stable-sizing box (`grid place-items-center min-h-0`) that hosts `PreviewPlayer` + overlays (passed as children) and a `shrink-0` FitTimeline slot.

- [ ] **Step 1: Build `EditorRail`** with the 6 items and a `"presets"` entry that, when selected, renders the existing preset gallery (today inside `StyleTab`/`PresetStrip`) as the inspector body. Active styling mirrors the current tab-bar (`ClipEditorScreen.tsx:1142-1158`). Badge dot is a positioned `<span>` shown when `agentActive`.

- [ ] **Step 2: Build `Inspector`** preserving the stable-canvas contract from Task 1 (outer `overflow-hidden`, inner `overflow-y-auto`, fixed width). Add the narrow-viewport `overlay` variant (absolute right sheet, canvas unaffected). English copy only.

- [ ] **Step 3: Build `EditorCanvas`** by lifting the preview block (`ClipEditorScreen.tsx:1001-1131`) into it; it receives the `PreviewPlayer` subtree + overlays as `children` and renders the FitTimeline slot below.

- [ ] **Step 4: Recompose `ClipEditorScreen`** — replace the `lg:grid-cols-[…]` main + top tab-bar with `grid-cols-[auto_minmax(0,1fr)_var(--inspector-w)]` (rail / canvas / inspector). Keep every handler and the whole mutation/flush state machine untouched. Switch the active panel by `active` rail selection. Wire `useEditorShortcuts` with a dispatcher mapping actions to existing handlers (`playPause`→video play/pause, `prev/nextClip`→Task 7 switch, `render`→`handleRender`, `{tab:n}`→select rail item n, `closeOverlay`→close inline edit / inspector overlay).

- [ ] **Step 5: Typecheck** — `pnpm --filter web exec tsc --noEmit` → no errors.

- [ ] **Step 6: Dogfood** — live editor: all 6 rail items open the right panel; canvas still never resizes; shortcuts work (Space/[ ]/1-6/R/Esc); narrow viewport shows the inspector overlay without resizing the canvas. Screenshot `shell-after.png`.

- [ ] **Step 7: Gate + commit** — `just check` → `refactor(editor): Fixed-Studio shell (rail + contextual inspector + canvas)`.

---

### Task 7: In-page clip switcher (no remount)

`clipId` becomes editor state; switching never remounts the shell. Reuse the existing per-clip reset/flush effects; isolate the mutation queue; sync the URL shallowly; prefetch neighbors.

**Files:**
- Modify: `apps/web/app/(app)/edit/[jobId]/[clipId]/page.tsx` (pass the route clip as the *initial* clip)
- Modify: `apps/web/components/editor/ClipEditorScreen.tsx` (own `activeClipId` state; reset on switch; URL sync; prefetch via Task 4 cache)
- Modify: `apps/web/components/editor/EditorHeader.tsx` (prev/next call an `onSwitchClip` callback instead of `router.push`)

**Interfaces:**
- Consumes: `createClipCache` (Task 4).
- Produces: `onSwitchClip(clipId: string): void` used by `EditorHeader` and the `prevClip`/`nextClip` shortcuts.

- [ ] **Step 1: Read the Next 16 shallow-URL doc**

Read `apps/web/node_modules/next/dist/docs/` for the supported way to change the URL without a navigation/remount (confirm whether `window.history.replaceState`/`pushState` is the sanctioned App-Router approach in 16.2.7). Use the documented mechanism; do NOT guess.

- [ ] **Step 2: Make `clipId` initial-only at the route**

`page.tsx`: keep awaiting params, pass as `initialClipId`:
```tsx
return <ClipEditorScreen jobId={jobId} initialClipId={clipId} />;
```
`ClipEditorScreen` signature → `{ jobId, initialClipId }`; internally `const [clipId, setActiveClipId] = useState(initialClipId);`. Every existing `clipId` reference keeps working (now reads state).

- [ ] **Step 3: Implement `onSwitchClip` with queue isolation + URL sync**
```tsx
const onSwitchClip = useCallback((nextId: string) => {
  if (nextId === clipId) return;
  void flushPending();                 // durability: persist outgoing edits first (B-#5)
  patchChain.current = Promise.resolve(); // isolate: drop the outgoing clip's mutation chain
  pendingCaptionsRef.current = null;
  if (flushTimerRef.current) { clearTimeout(flushTimerRef.current); flushTimerRef.current = null; }
  assSeq.current++; optGenRef.current++; // invalidate any in-flight ASS/optimistic reconcile
  setActiveClipId(nextId);             // existing load effect ([jobId, clipId]) resets & loads
  // shallow URL update per Step 1's documented API (no remount):
  window.history.replaceState(null, "", `/edit/${jobId}/${nextId}`);
}, [clipId, jobId, flushPending]);
```
The keepalive flush effect (`:433-456`) already runs `persistNow()` on `clipId` change, so the outgoing clip is also covered on hard unload.

- [ ] **Step 4: Wire header + shortcuts**

`EditorHeader`: add `onSwitchClip` prop; prev/next buttons call `onSwitchClip(prevId/nextId)` instead of `leaveTo(/edit/…)`. The "All clips" back button keeps `leaveTo` (real navigation). Map the `prevClip`/`nextClip` shortcut actions to `onSwitchClip`.

- [ ] **Step 5: Prefetch neighbors**

After a clip loads, idle-prefetch `±1` neighbor's `getClipEdit`/`getClipAss`/`getClipReframe`/`getClipAnalysis` into a `createClipCache(3)` instance; the load effect checks the cache first and uses warm data when present (falling back to fetch). Prefetch failures are best-effort but logged (no silent swallow).

- [ ] **Step 6: Typecheck** — `pnpm --filter web exec tsc --noEmit`.

- [ ] **Step 7: Dogfood the switch** — live editor: ‹ › switches clips with **no white flash / no remount**, place preserved; make a caption edit then immediately switch and confirm it persisted (reopen the clip); URL reflects the active clip and browser back works; rapid ‹ ›‹ › doesn't 409. Screenshot a before/after of switch latency if measurable.

- [ ] **Step 8: Gate + commit** — `just check` → `feat(editor): in-page clip switching (no remount) + neighbor prefetch`.

---

### Task 8: Live Frame mode (remove the explicit "Apply")

Frame mode applies live like every other control; drop the Apply button and the "approximate crop" caveat.

**Files:**
- Modify: `apps/web/components/editor/FrameTab.tsx` (remove `apply`/`applying`/`applied`; call `onApply` live on `mode`/`center`/`centerB` change, debounced)
- Modify: `apps/web/components/editor/ClipEditorScreen.tsx` (`handleFrameApply` already exists `:636-662`; ensure it's debounce-friendly)

**Interfaces:** unchanged `onApply(mode, center, centerB)`.

- [ ] **Step 1: Make Frame controls live**

In `FrameTab.tsx`: on `setMode`/`setCenter`/`setCenterB`, schedule a debounced `onApply(mode, mode==="fill"||"split"?center:null, mode==="split"?centerB:null)` (~250ms, mirroring the caption debounce feel). Remove the `<Button>Apply to clip</Button>` (`:155-165`) and the `applied` caveat block (`:167-171`). Replace the bottom helper text with a calm live hint + a "Reset to Auto" affordance (sets `mode="auto"`).

- [ ] **Step 2: Typecheck** — `pnpm --filter web exec tsc --noEmit`.

- [ ] **Step 3: Dogfood** — changing Frame mode/center updates the preview live with no Apply; "Reset to Auto" restores the AI decision; canvas does not move. Screenshot.

- [ ] **Step 4: Gate + commit** — `just check` → `feat(editor): live Frame mode (drop explicit Apply; matches Preview-is-live)`.

---

### Task 9: De-overload the Hook inspector

Split the long Hook panel into a compact primary section + a collapsible "Style" section. Reorganization only — no new capabilities.

**Files:**
- Modify: `apps/web/components/editor/HookTab.tsx` (`:86-355`)

**Interfaces:** unchanged props (`edit`, `busy`, `onHookChange`, `onRegenerate`, `regenerating`).

- [ ] **Step 1: Reorder into two sections**

Primary (always visible): Show toggle · hook text · "Regenerate for current clip" · timing (Whole clip / First seconds + duration). Secondary (collapsible `<details>`/disclosure, default collapsed): the full style block (color/font/plaque/outline/size/position/animation/uppercase) + "Remove hook" moved to the primary section's header as a clear destructive affordance. English copy only.

- [ ] **Step 2: Typecheck** — `pnpm --filter web exec tsc --noEmit`.

- [ ] **Step 3: Dogfood** — Hook panel no longer requires deep scroll for the common actions; collapsing/expanding Style does NOT resize the canvas (inspector scrolls internally). Screenshot.

- [ ] **Step 4: Gate + commit** — `just check` → `refactor(editor): de-overload Hook inspector (primary + collapsible style)`.

---

### Task 10: Merge FitTimeline into the Frame context

Remove the duplicate per-shot framing UI: FitTimeline shows only when the Frame rail item is active (it's a framing tool), eliminating the always-on strip competing with FrameTab modes.

**Files:**
- Modify: `apps/web/components/editor/EditorCanvas.tsx` (render the FitTimeline slot only when `active === "frame"`)
- Modify: `apps/web/components/editor/ClipEditorScreen.tsx` (pass `active` down; keep `handleApplyRange`)

**Interfaces:** `EditorCanvas` gains `showFitTimeline?: boolean`.

- [ ] **Step 1: Gate FitTimeline on the Frame context** — pass `showFitTimeline={active === "frame"}`; render the FitTimeline slot conditionally. Its `shrink-0` placement keeps the canvas stable whether shown or not (the canvas is `flex-1` of its own column; FitTimeline appearing just consumes the reserved bottom slot without resizing the video — verify).

- [ ] **Step 2: Typecheck + dogfood** — FitTimeline appears only on Frame; canvas height unchanged when it toggles. Screenshot.

- [ ] **Step 3: Gate + commit** — `just check` → `refactor(editor): scope FitTimeline to the Frame context (remove duplicate framing UI)`.

---

### Task 11: English-ify built-in preset names (worker)

**Files:**
- Modify: `services/worker/app/editor/preset_seeds.py` (the `name=` strings)
- Create: `services/worker/tests/unit/test_preset_seeds_english.py`

**Interfaces:** none (server `name` strings only; no contract change).

- [ ] **Step 1: Failing test**

`services/worker/tests/unit/test_preset_seeds_english.py`:
```python
from app.editor.preset_seeds import seed_presets

def test_preset_names_are_ascii_english():
    for p in seed_presets():
        assert p.name.isascii(), f"non-English preset name: {p.id}={p.name!r}"
```

- [ ] **Step 2: Run → FAIL**

Run (PowerShell, PATH refreshed): `cd services/worker; uv run pytest tests/unit/test_preset_seeds_english.py -q` → Expected: FAIL (Cyrillic names).

- [ ] **Step 3: Translate the names**

Replace `name=` values: `Активное слово`→`Active Word`, `Цветное слово`→`Color Word`, `Чистая строка`→`Clean Line`, `Неон`→`Neon`, `Минимал`→`Minimal`, `Подкаст`→`Podcast`, `Караоке-грин`→`Karaoke Green`, `Жирный белый`→`Bold White`, `Контур-поп`→`Outline Pop`, `Нижняя треть`→`Lower Third`, `Поп-слова`→`Pop Words`. Leave already-English names (`Hormozi`, `MrBeast`, `Anton Bold`, `Beasty Yellow`, `Bold Pop White`, `Bebas Condensed`, `Karaoke Fill`, `Highlight Box`, `Sticker Round`, `Gamer Tech`) unchanged. Also fix the stale docstring line claiming a `apps/web/lib/presets.ts` mirror (that file doesn't exist).

- [ ] **Step 4: Run → PASS** (`uv run pytest tests/unit/test_preset_seeds_english.py -q`).

- [ ] **Step 5: Gate + commit** — `just check` → `fix(worker): English-only built-in preset names (UI-rule compliance)`.

---

### Task 12: Final creator dogfood pass + before/after

Validate the full WS-A against the spec's "Creator's-eye lens" — felt quality, not just green checks.

**Files:** none (verification + a short report appended to the spec).

- [ ] **Step 1: Run the full creator journey** in the live authed editor: open a real job, switch across ≥4 clips via ‹ › and shortcuts, on each tweak captions + hook + framing, across 9:16/1:1/4:5/16:9, then render one. Capture screenshots at each step.

- [ ] **Step 2: Check every smoothness principle** from the spec (zero layout jank · live-not-modal · invisible autosave · minimal/predictable clicks · keyboard+mouse · fast perceived perf · forgiving). Note any that fail.

- [ ] **Step 3: Fix anything weak** found in Step 2 (small follow-up commits), then re-verify.

- [ ] **Step 4: Update docs** — append an "Implemented (WS-A)" note to `docs/superpowers/specs/2026-06-20-editor-fixed-studio-design.md` and add a one-line entry to `docs/JOURNAL.md` + the editor reality bullet in `docs/README.md`.

- [ ] **Step 5: Gate + commit** — `just check` → `docs(editor): record Fixed-Studio (WS-A) shipped + creator dogfood notes`.

---

## Self-review

**Spec coverage:** Fixed Studio shell → T6; framing-bug fix → T1 (+ preserved by T6); in-page clip switcher → T7; live Frame mode → T8; Hook de-overload → T9; FitTimeline merge → T10; English preset names → T11; perf (frame identity / memoized inspector / scoped recompute) → T3 + T6; keyboard shortcuts → T5 (+ wired T6); prefetch → T4 + T7; creator-UX lens / dogfooding → T1, T6, T7, T12; responsive overlay → T6. `replyRanges` scoping (spec perf bullet) is folded into T6 Step 4 (recompose) — **note:** when recomposing, change the `replyRanges`/`activeReplyIndex` memo deps from `edit` to `edit.captions.replies` + `words` + `outerStart`.

**Placeholder scan:** no TBD/TODO; pure-logic tasks have full code + tests; presentational tasks (T6/T7/T9/T10) specify exact files, interfaces, the load-bearing code, and acceptance criteria rather than reproducing 300-line components verbatim (codebase-pattern fidelity per the skill).

**Type consistency:** `FrameState` shape consistent across T3 and the `frame` memo; `EditorAction` consistent T5↔T6; `ClipCache<T>` consistent T4↔T7; `onSwitchClip(clipId)` consistent T7 (ClipEditorScreen) ↔ EditorHeader; `Tab` extended with `"presets"` in T6 and used in T10's `active` gating.

## Out of scope (later workstreams)
B (background-agent store/notifications/multi-run) · C (alignment guides/snapping/safe-areas) · D (preset persistence/scopes/brand kit) · E (deep perf instrumentation + editor Lighthouse budget). A leaves the seams: rail Agent badge (`agentActive`), Presets rail item, canvas as snapping host.
