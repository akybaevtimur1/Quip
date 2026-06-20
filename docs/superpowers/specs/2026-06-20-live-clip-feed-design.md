# Live Clip Feed — interactive pre-render processing (Variant A)

> Design spec. Goal: kill the dead "waiting" minutes. Today the user uploads, watches a static
> 4-step stepper for several minutes, and only sees anything about *their* video once clips render.
> We already compute the valuable part (each clip's hook, "why it's worth posting", score, type,
> interval) at the **select** stage (~60%) — we just gate it behind the render boundary (80%) and
> show a skeleton. This spec surfaces that value as a **live clip feed** during processing.

## Problem

Pipeline stages (worker `run.py`, with progress %): `queued → downloading(10) → transcribing(35)
→ selecting(60) → rendering(80) → done(100)`. Clips stream into the grid as each renders
(`set_clip_ready`). But the user sees **nothing about their video** until `rendering`:

- `JobProgress.tsx` shows a static stepper + 3 grey pulsing rectangles for the whole 0→80% window.
- Clip metadata (hook/why/score) is persisted only by `set_clips_pending(progress=80)` — the render
  boundary — even though it is **final after `select` (60%)**.

## Research (competitor landscape, 2025-2026)

- **No competitor streams pre-render clip info** (OpusClip, Vizard, Klap, Munch, 2Short, Quso all
  deliver the clip set as one batch at the end). Incremental candidate reveal is unclaimed.
- **Only Vizard narrates the pipeline** during the wait ("Transcribing → Finding Faces →
  Generating Clips") — labels only, no artifacts.
- **"Why this clip" reasoning is always a results-page feature, never during processing.** Best
  reasoning surfaces (OpusClip Hook/Flow/Value/Trend, Quso) are post-result; most show a bare number.
- Interactivity elsewhere is front-loaded into *setup*; the wait itself is universally passive.

We leapfrog by showing each clip's hook + **plain-language "why it's worth posting"** + score
**as it's chosen, before it renders** — using data our pipeline already produces.

## What already exists (do NOT rebuild)

- `ClipCard.tsx` already renders the full rich card for a clip with empty `video_url`: score, hook
  («…»), "Why it works" (`why_works ?? reason`), type chip, time range. Only the **video area** is a
  "Rendering…" skeleton and actions are disabled.
- `dashboard/page.tsx` already swaps the stepper for the grid the moment any clip exists
  (`showProgressiveGrid`). `ClipGrid` already shows "N of M ready" + sorts ready clips to the top.
- `set_clips_pending` already persists all clips (metadata, `video_url=""`) in one row; `set_clip_ready`
  atomically fills each `video_url`. `GET /jobs` returns clips incrementally.
- `build_clip_out(clip_id, segment, transcript.words, video_url)` builds a `ClipOut` from a `Segment`.
  The render fan-out reuses the **same `segments` list** in the same order → `clip_{i:02d}` ordering is
  identical whether built at select or at the render boundary (verified in `run.py`).

So the value layer is built. The work is **timing + the empty windows**, not new card UI.

## Design

### 1. Worker — persist clips at `select`, not at the render boundary (CORE)

Move the `pending_clips` construction + persist to **immediately after `select`** (right after
`segments` is final, ~line 331 of `run.py`), so `GET /jobs` returns full clip metadata at ~60%.

- Build `pending_clips = [build_clip_out(f"clip_{i:02d}", seg, transcript.words, "") …]` and persist
  via the pending path **right after select**.
- **Keep status truthful:** clips must be persisted **without** prematurely flipping status to
  `rendering`. `cloud_state.set_clips_pending` currently hardcodes `status="rendering"`; add a
  `status` parameter (default `"rendering"` for backward compat) so the early call passes the current
  stage (`selecting`). `emit(JobStatus.rendering, 80)` stays where render actually begins. The
  frontend swaps to the grid on *clip presence*, not status, so this is enough.
- Remove the now-redundant persist at progress=80 (or make it idempotent — persisting the identical
  list twice is a no-op for metadata; the render fan-out's `set_clip_ready(idx)` still targets the
  same indices).
- **Invariant:** the clip list/order persisted at select MUST equal the render fan-out order so
  `set_clip_ready(idx)` aligns. Guaranteed today (same `segments`); add a regression test.
- `db.set_clips_pending` (local SQLite path) gets the same `status` parameter for parity.

### 2. Worker — progress detail for live narration (0→60% window)

Add small **optional** fields to the job status payload (`models.py`, then `just types`), populated as
stages complete (all `None` until known → backward compat):

- `source_minutes: float | None` — from probed source duration (set at `downloading`).
- `transcript_words: int | None` — `len(transcript.words)` (set at `transcribing`).
- `moments_found: int | None` — `len(segments)` (set at `selecting`; also == clip count).

These let the narration show real numbers during the windows where no clip exists yet. Plumb through
`emit`/db (cloud jsonb + local SQLite). Pure-logic: none — these are passthrough counts.

### 3. Frontend — `JobProgress` → live narration feed (0→60%)

Replace the static stepper with a self-narrating feed: current stage with a spinner + the completed
stages with their **count artifact** when available:

- `downloading` → "Preparing your video" (+ `source_minutes` once known: "· 18 min").
- `transcribing` → "Transcribing" (+ `transcript_words`: "· 412 words").
- `selecting` → "Finding the moments worth posting" (+ `moments_found`: "· 9 found").
- Keep elapsed timer + Stop button (FREE phase) exactly as today.

This component is shown only while `clips.length === 0`; once clips exist the page already swaps to the
grid (Section 1 makes that happen at ~60%). Keep it lightweight; no backend streaming — it reads the
counts from the existing job poll.

### 4. Frontend — card arrival animation (polish)

When a clip first appears in the grid, animate it in (fade/scale "pop") and **count the score up**
0→N. One-time per card (track seen ids). Respects `prefers-reduced-motion`. Pure-ish: a small
"animate on mount" wrapper; no new state machine.

### 5. Frontend — client-side thumbnail for pending clips (chosen approach)

Fill the grey "Rendering…" video box with a real frame, no backend/storage:

- A `PendingThumb` that mounts a hidden `<video>` pointed at the **preview proxy**
  (`jobs/{jobId}/preview.mp4`, the same source the editor uses), seeks to the clip's `start`, draws
  one frame to a `<canvas>`, and shows it as the card's poster. Keep the small "Rendering…" badge
  overlaid so it's clear the clip isn't playable yet.
- **Graceful fallback:** if the preview proxy isn't ready yet (404/again) or seek fails, keep today's
  skeleton; retry on the next poll. The proxy is built in parallel (`preview_job` spawned right after
  select), so thumbnails appear within seconds-to-a-minute, not blocking the card.
- Crop note: the preview proxy is the **source aspect** (16:9), not the 9:16 reframed clip. v1 shows a
  center-cropped 9:16 poster from that frame (cheap, good enough as a "this is the moment" cue). True
  reframed thumbnails are out of scope (would need worker render).

## Data flow

```
download → (source_minutes) ┐
transcribe → (transcript_lines)
select → build pending ClipOuts (hook/why/score/interval, video_url="") ──► db (status stays "selecting")
        → GET /jobs returns clips ──► frontend swaps stepper→grid (~60%)  ── rich cards, "Rendering…" video
        → preview_job builds proxy in parallel ──► client frame-grab fills thumbnails
render fan-out per clip → set_clip_ready(idx, url) ──► card's video area flips to player (existing)
done → set_done
```

## Files touched

- Worker: `app/run.py` (move persist earlier; emit counts), `app/cloud_state.py` + `app/db.py`
  (`status` param on `set_clips_pending`; persist counts), `app/models.py` (3 optional job fields)
  → `just types`.
- Frontend: `components/JobProgress.tsx` (narration + counts), `components/ClipCard.tsx` +
  new `components/PendingThumb.tsx` (client thumbnail), small arrival-animation wrapper. Read
  `node_modules/next/dist/docs/` before web code (Next 16 caveat, `apps/web/AGENTS.md`).

## Edge cases / risks

- **Clip order/idx alignment** (select-persist vs render fan-out): guaranteed by shared `segments`;
  add a worker regression test asserting the persisted `clip_{i:02d}` order equals the fan-out order.
- **Double persist** (if the 80% call is kept): must be idempotent and must not blank a `video_url`
  already filled by a fast `set_clip_ready`. Prefer removing the 80% call; if kept, it must only
  upsert clips that don't yet exist. Spec choice: **remove the 80% call**, persist once at select.
- **Preview proxy not ready** → thumbnail falls back to skeleton (handled).
- **Cancelled jobs (FREE phase)**: cancellation happens before/at transcription; clips persisted at
  select are after the paid boundary, so no change to the cancel/charge logic (`docs/README.md`
  Stop/cancel). Verify the Stop button still only shows while `cancellable`.
- **Backward compat**: new job fields optional (`None`); old jobs render exactly as today.
- **WYSIWYG / reframe grid**: untouched — this spec adds no render/ASS changes (only timing + UI).

## Testing

- **Worker (TDD, pure logic):** order-invariance test (persisted clip ids/order == fan-out order);
  counts populated at the right stages; `set_clips_pending(status=…)` writes the given status.
- **Frontend:** verify live (real authed editor flow / a `/dev` harness) — narration shows counts;
  cards appear at ~60% with hook/why/score before video; thumbnails frame-grab from the proxy;
  video area flips to player on render; reduced-motion respected. Screens at each state.
- `just check` green before commit; deploy worker (`modal deploy`) + frontend (push `main`).

## Scope

**In v1 (this spec):** all of §1–§5 (core early-persist + narration + arrival animation + client
thumbnail).

**Out of v1 (later):** in-wait *curation* (approve/reject/reorder/trim → that's "Variant B"), live
word-by-word transcript ticker, OpusClip-style Hook/Flow/Value/Trend score breakdown, true reframed
(9:16) pre-render thumbnails.

## Definition of done

User uploads → within the first stage they see a live, self-narrating feed with real counts; at the
`select` boundary (~minutes before render) the grid fills with rich clip cards (hook + "why it's worth
posting" + score) that **pop in** with a frame-grabbed thumbnail; each card's video flips to a player
as it renders. No dead stepper minutes. `just check` green; verified live with screenshots; docs
synced (JOURNAL entry + `docs/README.md` reality note).
