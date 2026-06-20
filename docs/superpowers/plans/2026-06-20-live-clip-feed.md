# Live Clip Feed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface each clip's hook / "why it's worth posting" / score as a live card feed during processing (at the `select` stage, ~minutes before render), and make the pre-clip wait alive with a self-narrating feed + arrival animation + client-side thumbnails.

**Architecture:** The frontend already swaps the stepper for the rich grid the moment any clip exists (`showProgressiveGrid`) and `ClipCard` already renders hook/why/score for clips with empty `video_url`. So the core change is **timing**: persist clip metadata at `select` instead of the render boundary. Plus small additive enhancements (narration counts, thumbnail, animation). No render/ASS/reframe changes.

**Tech Stack:** Worker = Python (FastAPI/Modal, pydantic, pytest, ruff, mypy). Frontend = Next 16 + React (TypeScript, ESLint w/ React Compiler rules). Types codegen: `models.py` → `just types` → `packages/shared`.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-06-20-live-clip-feed-design.md` (authoritative).
- Commit gate before EVERY commit: `just check` green (ruff + mypy + tsc + eslint + unit tests + anti-drift). Commit from PowerShell with PATH refresh: `$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")`. Cyrillic commit messages → write to a Windows-path file, `git commit -F`.
- Types are codegen only: change `models.py` → run `just types` (never hand-edit `packages/shared/*`).
- No silent fallbacks (rule #8): errors surface (JobError / failed status / explicit log).
- UI language: English only for any user-facing string.
- Next 16 caveat: read `node_modules/next/dist/docs/` before web code (`apps/web/AGENTS.md`).
- No changes to trim/fps/regions/ASS (reframe Δ=0 invariant out of scope here).
- Worker deploy = `modal deploy deploy/modal/worker.py` (`$env:PYTHONIOENCODING="utf-8"` first). Frontend = push `main` (Vercel auto).

---

### Task W1: Persist clips at the `select` stage (CORE)

Move clip-metadata persistence from the render boundary (progress=80) to right after `select` (~60%) so `GET /jobs` returns full clip metadata minutes sooner. Keep job status truthful (don't flip to `rendering` early).

**Files:**
- Modify: `services/worker/app/run.py` (the `run_pipeline`/`run` flow around the select stage, currently persists `pending_clips` at the `emit(JobStatus.rendering, 80)` block ~lines 361-371).
- Modify: `services/worker/app/cloud_state.py:124` (`set_clips_pending`) — add a `status` param.
- Modify: `services/worker/app/db.py:157` (`set_clips_pending` local path) — add the same `status` param, thread to cloud + local SQLite.
- Test: `services/worker/tests/unit/test_run_clips_pending.py` (new).

**Interfaces:**
- Consumes: `build_clip_out(clip_id, segment, words, video_url)`, `segments` (final after select), `db.set_clips_pending`.
- Produces: clips persisted (metadata, `video_url=""`) immediately after select; `set_clips_pending(job_id, clips, progress, status="rendering")` signature.

- [ ] **Step 1: Write the failing test** — order invariance (persist order == fan-out order).

`services/worker/tests/unit/test_run_clips_pending.py`:
```python
from app.models import Segment, ClipType, Word
from app.run import build_clip_out

def _seg(start: float, end: float) -> Segment:
    return Segment(start=start, end=end, reason="r", score=0.5, type=ClipType.hook)

def test_build_clip_out_id_and_pending_video_url():
    words = [Word(text="a", start=0.0, end=0.1)]
    c = build_clip_out("clip_03", _seg(1.0, 3.0), words, "")
    assert c.id == "clip_03"
    assert c.video_url == ""          # pending = empty
    assert c.reason == "r" and c.score == 0.5

def test_clip_ids_are_1based_in_segment_order():
    words = [Word(text="a", start=0.0, end=0.1)]
    segs = [_seg(0, 2), _seg(5, 7), _seg(9, 11)]
    ids = [build_clip_out(f"clip_{i:02d}", s, words, "").id for i, s in enumerate(segs, start=1)]
    assert ids == ["clip_01", "clip_02", "clip_03"]   # render fan-out uses the same order
```

- [ ] **Step 2: Run to verify it fails (if `build_clip_out` import path differs, fix the import to match `run.py`).**
Run: `uv run pytest tests/unit/test_run_clips_pending.py -q` — Expected: PASS already if `build_clip_out` is importable (this locks the contract the reorder must preserve). If import fails, adjust to the real module path and re-run.

- [ ] **Step 3: Add `status` param to `cloud_state.set_clips_pending` and `db.set_clips_pending`.**
In `cloud_state.set_clips_pending(job_id, clips, progress=80, status="rendering")`: write the given `status` to the row instead of the hardcoded `"rendering"`. In `db.set_clips_pending(job_id, clips, progress=80, status="rendering")`: pass `status` through to `cs.set_clips_pending(...)` and to the local SQLite update (set the status column to `status`). Mirror the existing dual-path exactly; default `"rendering"` keeps all existing callers behavior-identical.

- [ ] **Step 4: Reorder `run.py` to persist clips right after select.**
After `segments` is final (right after the `db.put_job_artifacts(...)` call ~line 341, BEFORE the source upload), build and persist the pending clips, keeping status at `selecting`:
```python
    # Persist clip metadata (hook/why/score/interval, empty video_url) RIGHT AFTER select so
    # GET /jobs returns the rich cards minutes before render. Status stays "selecting" (truthful);
    # the frontend swaps to the grid on clip-presence, not status. video_url filled later by
    # set_clip_ready (same clip_{i:02d} order → idx aligned with the render fan-out).
    pending_clips = [
        build_clip_out(f"clip_{i:02d}", seg, transcript.words, "")
        for i, seg in enumerate(segments, start=1)
    ]
    db.set_clips_pending(job_id, pending_clips, progress=60, status=JobStatus.selecting)
```
Then DELETE the later duplicate persist at the `emit(JobStatus.rendering, 80)` block (the `pending_clips = [...]` + `db.set_clips_pending(job_id, pending_clips, progress=80)` lines). Keep `emit(JobStatus.rendering, 80)` itself (render genuinely starts there).

- [ ] **Step 5: Run worker tests + lint/types.**
Run: `uv run pytest tests/unit -q && uv run ruff check app tests && uv run mypy app` — Expected: PASS.

- [ ] **Step 6: Commit.**
```
git add services/worker/app/run.py services/worker/app/db.py services/worker/app/cloud_state.py services/worker/tests/unit/test_run_clips_pending.py
git commit -F <msg-file>   # feat(worker): persist clip metadata at select → cards appear pre-render
```

---

### Task W2: Progress-detail counts for live narration

Add optional counts to the job status so the frontend narration shows real numbers during the pre-clip window.

**Files:**
- Modify: `services/worker/app/models.py:148` (`Job`) — add 3 optional fields. Then `just types`.
- Modify: `services/worker/app/db.py` + `services/worker/app/cloud_state.py` — add `set_progress_detail(job_id, *, source_minutes=None, transcript_words=None, moments_found=None)` (cloud jsonb merge + local SQLite columns; mirror `set_clips_pending` dual-path; only write provided keys).
- Modify: `services/worker/app/run.py` — call it at the boundaries.
- Test: `services/worker/tests/unit/test_job_progress_detail.py` (new) — Job accepts/omits the optional fields.

**Interfaces:**
- Consumes: `meta` (source duration), `transcript.words`, `segments`.
- Produces: `Job.source_minutes/transcript_words/moments_found` (all `float|int|None`), `db.set_progress_detail(...)`.

- [ ] **Step 1: Write the failing test.**
`services/worker/tests/unit/test_job_progress_detail.py`:
```python
from app.models import Job, JobStatus, SourceKind

def test_job_progress_detail_fields_optional_default_none():
    j = Job(id="j", status=JobStatus.transcribing, stage=JobStatus.transcribing,
            progress=35, source_kind=SourceKind.upload)
    assert j.source_minutes is None and j.transcript_words is None and j.moments_found is None

def test_job_progress_detail_fields_settable():
    j = Job(id="j", status=JobStatus.selecting, stage=JobStatus.selecting, progress=60,
            source_kind=SourceKind.upload, source_minutes=18.0, transcript_words=412, moments_found=9)
    assert (j.source_minutes, j.transcript_words, j.moments_found) == (18.0, 412, 9)
```
(Use the real `SourceKind` member; check `models.py`.)

- [ ] **Step 2: Run to verify it fails.** Run: `uv run pytest tests/unit/test_job_progress_detail.py -q` — Expected: FAIL (unexpected kwargs).

- [ ] **Step 3: Add the fields to `Job`** (after `cancellable`):
```python
    # Live-narration counts during processing (optional → backward compat). source_minutes set
    # after import; transcript_words after transcribe; moments_found after select (== clip count).
    source_minutes: float | None = None
    transcript_words: int | None = None
    moments_found: int | None = None
```

- [ ] **Step 4: Run `just types`** (regenerates `packages/shared`). Run: `just types` — Expected: exit 0; `packages/shared/src/types.ts` gains the 3 fields on `Job`.

- [ ] **Step 5: Add `set_progress_detail` (db.py + cloud_state.py)** mirroring `set_clips_pending`'s dual path: cloud merges the provided keys into the job row jsonb/columns; local SQLite updates the matching columns (add columns if the local schema is columnar — follow the existing local-state pattern). Only write provided (non-None) keys.

- [ ] **Step 6: Call it at the boundaries in `run.py`:**
  - after import/meta known: `db.set_progress_detail(job_id, source_minutes=round(meta.duration / 60, 1))`
  - after transcribe: `db.set_progress_detail(job_id, transcript_words=len(transcript.words))`
  - after select: `db.set_progress_detail(job_id, moments_found=len(segments))`
(Use the real `meta` duration attribute — check `Meta`/`stage0_import`.)

- [ ] **Step 7: Run gate.** `uv run pytest tests/unit -q && uv run ruff check app tests && uv run mypy app` — Expected: PASS.

- [ ] **Step 8: Commit.** `feat(worker): job progress-detail counts for live narration` (include regenerated `packages/shared`).

---

### Task F1: JobProgress → live narration feed

Replace the static stepper with a self-narrating feed showing the W2 counts.

**Files:**
- Modify: `apps/web/components/JobProgress.tsx`.
- Modify: `apps/web/lib/types.ts` re-export already surfaces `Job` (no change if `Job` is re-exported; verify).

**Interfaces:**
- Consumes: `Job.status`, `Job.source_minutes`, `Job.transcript_words`, `Job.moments_found`, `elapsed`.

- [ ] **Step 1: Update `JobProgress` props** to accept the counts (pass `job` or the 3 fields from `dashboard/page.tsx`). Keep `elapsed`, `cancellable`, `onStop`.

- [ ] **Step 2: Render each step with its count when present.** For each stage row, append a muted count chip when available:
  - "Preparing video" + (`source_minutes != null` ? ` · ${source_minutes} min` : "")
  - "Transcribing" + (`transcript_words != null` ? ` · ${transcript_words.toLocaleString()} words` : "")
  - "Finding the moments worth posting" + (`moments_found != null` ? ` · ${moments_found} found` : "")
  - "Rendering" (unchanged label)
Keep the active spinner / done-check styling. Copy must be English.

- [ ] **Step 3: Pass the fields from `dashboard/page.tsx`** where `<JobProgress .../>` is rendered (the `phase === "tracking"` branch). It only renders while `clips.length === 0`, so no overlap with the grid.

- [ ] **Step 4: Typecheck + lint.** `pnpm --filter web exec tsc --noEmit && pnpm --filter web lint` — Expected: exit 0.

- [ ] **Step 5: Commit.** `feat(web): live narration feed with processing counts`.

---

### Task F2: Client-side thumbnail for pending clips

Fill the "Rendering…" box with a frame grabbed from the preview proxy.

**Files:**
- Create: `apps/web/components/PendingThumb.tsx`.
- Modify: `apps/web/components/ClipCard.tsx` (use `PendingThumb` in the `pending` branch instead of the bare skeleton; keep the small "Rendering…" badge).

**Interfaces:**
- Consumes: `jobId`, `clip.start` (source seconds), the preview proxy URL `resolveUrl(`jobs/${jobId}/preview.mp4`)`.
- Produces: `<PendingThumb jobId clipStart />` rendering a 9:16 poster (center-cropped) or the skeleton fallback.

- [ ] **Step 1: Implement `PendingThumb`** — `"use client"`. On mount, create a hidden `<video crossOrigin="anonymous" muted preload="metadata">` at the preview URL; on `loadeddata`, set `currentTime = clipStart`; on `seeked`, draw the current frame to a `<canvas>` sized to a 9:16 center-crop, set the canvas as the visible poster. State: `ready` boolean. On any error / not-ready, render the existing skeleton (grey pulse + small "Rendering…"). Clean up the video element on unmount. Respect that the proxy may 404 early → keep skeleton, retry on the next render (the parent re-renders on poll).

- [ ] **Step 2: Wire into `ClipCard`** — replace the `pending ?` skeleton block (lines ~48-57) with `<PendingThumb jobId={jobId} clipStart={clip.start} />`, preserving the `aspect-[9/16]` frame and the overlaid "Rendering…" badge.

- [ ] **Step 3: Typecheck + lint.** `pnpm --filter web exec tsc --noEmit && pnpm --filter web lint` — Expected: exit 0. Watch the React Compiler `react-hooks/refs`/`immutability` rules (don't pass refs into hooks; attach listeners via effects/callback refs).

- [ ] **Step 4: Commit.** `feat(web): client-side frame-grab thumbnail for pending clips`.

---

### Task F3: Card arrival animation

Clips pop in and the score counts up the first time a card appears.

**Files:**
- Modify: `apps/web/components/ClipGrid.tsx` (track seen ids) and/or `apps/web/components/ClipCard.tsx` (mount animation + score count-up).

- [ ] **Step 1: Mount animation** — wrap the card in a fade/scale-in (Tailwind transition on a mounted flag, or a tiny `useEffect` toggling a class). Gate on `prefers-reduced-motion: reduce` → no animation.

- [ ] **Step 2: Score count-up** — animate `clip.score` from 0 → value on first appearance (rAF or a small interval), reduced-motion → show final immediately.

- [ ] **Step 3: Typecheck + lint.** `pnpm --filter web exec tsc --noEmit && pnpm --filter web lint` — Expected: exit 0.

- [ ] **Step 4: Commit.** `feat(web): clip card pop-in + score count-up`.

---

### Task INT: Integrate, gate, deploy, verify live

- [ ] **Step 1: Full gate.** `just check` (PowerShell, PATH refresh) — Expected: PASS.
- [ ] **Step 2: Deploy.** Worker: `modal deploy deploy/modal/worker.py` (`$env:PYTHONIOENCODING="utf-8"`). Frontend: push `main` (Vercel auto). Pull/rebase first if origin advanced.
- [ ] **Step 3: Verify live** (real authed editor flow): upload → narration shows counts during transcribe/select; at ~60% the grid fills with rich cards (hook + "why" + score) BEFORE video; thumbnails frame-grab from the proxy; each card's video flips to a player as it renders; cards pop in; reduced-motion respected. Capture screenshots at each state.
- [ ] **Step 4: Docs sync.** JOURNAL entry + `docs/README.md` reality note ("clips' metadata streams at the select stage; processing screen is a live narrated feed").

## Self-Review

- **Spec coverage:** §1 persist-at-select → W1; §2 counts → W2; §3 narration → F1; §4 animation → F3; §5 thumbnail → F2; verify/deploy → INT. ✓
- **Placeholder scan:** db dual-path steps reference the existing `set_clips_pending` pattern to mirror (executor reads it) rather than inventing — acceptable, not a placeholder. Concrete code given for models, run.py reorder, tests, narration chips.
- **Type consistency:** `set_clips_pending(..., status=...)` used identically in W1 db + cloud; `set_progress_detail` keys (`source_minutes`/`transcript_words`/`moments_found`) match the `Job` fields and the F1 narration reads. ✓
- **Parallelization:** W1→W2 sequential (same files, W2 needs `just types`). F1 depends on W2 types. F2, F3 independent of backend → can run parallel to the worker tasks.
