# BACKEND_AUDIT — layer-by-layer debug of Quip (the *class* of bug)

> **Scope (since the 2026-06-24 docs reorg):** this is the **L0–L6 debugging-layer map + regression
> ledger** — the dependency-ordered mental model for the "works here / breaks there" class of bug.
> It is NOT the system overview: for *how Quip works end-to-end* read **`docs/CORE_ARCHITECTURE_AND_FEATURES.md`**
> (the living architecture doc); for the *current-reality baseline* read **`docs/README.md`**.

> Living document. Owner: long-running debug agent (session "debugger").
> Method: `superpowers:systematic-debugging` — no fix without a reproduced root cause +
> evidence at the component boundary. Fix at the source by **unifying divergent paths**, not
> by teaching one path to mimic the other. Bottom → top (L0→L6); after any fix re-run
> `just check` AND re-verify every green item below the changed layer.

**The disease:** the same job/clip/caption/reframe data takes *different code paths* in
different surfaces (grid vs editor) and environments (local disk+SQLite vs cloud R2+Postgres),
and no single owner holds the source of truth. Symptoms: double captions, editor-crop ≠
render-crop, `NotSupportedError`, cloud 404s, "With captions" downloads a caption-less file.

---

## Baseline (regression anchor)

| Date | Branch | `just check` | Tests | Notes |
|------|--------|--------------|-------|-------|
| 2026-06-14 | `main` | ✅ exit 0 | **459 passed** | Untracked WIP in `deploy/modal/worker.py`, `stage0_import.py`, `BENCHMARKS.md` = unrelated yt-dlp/Deno/AV1 reliability work — left untouched. |
| 2026-06-14 | `main` | ✅ exit 0 | **462 passed** | After D1 fix (clean clip + captioned artifact). |
| 2026-06-14 | `main` | ✅ exit 0 | **465 passed** | After D2 fix (reframe plan endpoint). |
| 2026-06-14 | `main` | ✅ exit 0 | **465 passed** | After D3 fix (lazy preview videos; frontend-only). |
| 2026-06-14 | `main` | ✅ exit 0 | **471 passed** | After D6 fix (durable R2 clip URLs). Session "debugger2" baseline was 467 (post billing+modal commits). |
| 2026-06-14 | `main` | ✅ exit 0 | **472 passed** | After D5 fix (source_kind reflects uploads). |
| 2026-06-14 | `main` | ✅ exit 0 | **472 passed** | After D4 doc-fence (legacy planner benchmark-only). |

---

## Layer map (dependency order)

| Layer | Files | Contract / invariant |
|-------|-------|----------------------|
| **L0 Env & parity** | local: disk + SQLite + bundled ffmpeg · cloud: Modal + R2 + Supabase Postgres + static ffmpeg. Gate = `cloud_state.cloud_enabled()` (`STORAGE_BACKEND=r2` + `SUPABASE_URL` + `SERVICE_ROLE_KEY`). | Both paths must produce the same artifacts/URLs. Most bugs are "works local, breaks cloud." |
| **L1 Storage/artifacts** | `app/storage.py` (R2/local clip+source), `app/artifacts.py` (disk-first/cloud-fallback meta/segments/transcript/source) | Every artifact the editor/preview needs must be reachable in **both** envs. R2 keys: `{job}/{clip}.mp4`, `{job}/source.mp4`. |
| **L2 State** | `app/db.py` (router), `app/cloud_state.py` (Postgres), `app/editor/store.py` (clip_edits), `row_to_wire` | One row→wire mapping. `video_url`: http→as-is, relative→`media/<job>/…`. |
| **L3 Pipeline** | `app/run.py` (batch), `app/pipeline/*`, `app/editor/*`, `app/tasks.py` | One reframe path (frame-accurate, Δ=0). Clean-vs-burned file ownership. |
| **L4 API** | `app/main.py` | Each endpoint's returned URL/shape; `/render`, `/ass`, `/export/*`, `/media`, `/source.mp4`. |
| **L5 Frontend data** | `apps/web/lib/api.ts`, `lib/useJob.ts` | URL resolution, auth headers, dual-mode base. |
| **L6 Frontend UI** | `apps/web/components/*` (grid `ClipCard`/`ClipPreview`, editor `ClipEditorScreen`/`PreviewPlayer`, `ExportMenu`) | grid preview == editor preview == exported file (WYSIWYG), one ASS, one renderer. |

### Hard invariants (must not regress)
- **REFRAME_FPS_GRID Δ=0** — mode-region boundaries land exactly on cut frames (no flashes).
  See `docs/REFRAME_FPS_GRID_INVARIANT.md`. Spatial-only changes (aspect, clean/burned) must
  not touch the temporal frame grid.
- **WYSIWYG** — editor preview == grid preview == exported file; one ASS (`captions_v2.compile_ass`),
  one renderer (`stage5_render`).
- **No silent fallbacks / no `except: pass`** — surface as `JobError` + failed status.
- `just check` green before every commit.

---

## Findings (divergences) — root cause + evidence

Status legend: 🔬 investigated (root cause traced) · 🛠 fix in progress · ✅ fixed+verified.

### D1 — Clean-vs-burned clip file collision  ·  L3/L4/L6  ·  ✅ fixed (local-verified)
**The central disease.** `clips/<id>.mp4` means two different things depending on history.

**FIX (commit `feat`→ see git log):** unified on "clean clip forever + separate captioned artifact".
- `tasks.render_clip_edit_job` now renders to `clips/<id>_captioned.mp4` (R2 key `_captioned`) via
  `storage.upload_clip(..., variant="captioned")` — the clean `clips/<id>.mp4` is **never overwritten**.
- New `GET /jobs/{job}/clips/{clip}/export/captioned.mp4` renders the captioned mp4 from the *current*
  edit-state (same ASS as the libass preview) — symmetric to `export/clean.mp4`.
- `storage.py` pure builders gained `variant=` (default unchanged → backward compatible).
- Frontend: `ClipPreview` **always** overlays libass (burned-detection band-aid + `getRenderStatus`
  call deleted) → grid == editor == export in every state. `ExportMenu` "With captions" → baked
  `render_url` if present else the on-demand `export/captioned.mp4` (never the clean clip). `ClipCard`
  stops passing the clean clip as the captioned URL; editor's initial `downloadUrl` no longer points
  at the clean clip.
- **Evidence:** `just check` green, **462 tests** (was 459; +`test_variant_gives_separate_keys`,
  `test_export_captioned_mp4_serves_file`, `test_render_job_writes_captioned_never_overwrites_clean`
  which asserts the clean clip bytes are untouched after an editor render).
- ⚠️ **Cloud not yet exercised** (needs founder secrets) — R2 `_captioned` key path is by construction
  the same code as the clean path; documented for live verification.
- **REAL local proof** (`tmp/verify_d1_real.py`, job `job_060aaf70f05c`, $0): rendered the captioned
  clip via `render_edit_to_file(with_subtitles=True → clips/clip_01_captioned.mp4)`; the clean
  `clip_01.mp4` md5 was **byte-identical before/after** (`bcfaa1e2c17a27dd2f579ea544366186`), and the
  captioned file is a valid separate h264 1080×1920 mp4. Full reframe→render path ran clean (no errors).

<details><summary>original investigation (kept for the record)</summary>

**Evidence (traced):**
- Batch render produces a **clean** clip: `run.py:181-186` calls `render_clip(..., "clips/{clip_id}.mp4")`
  with **no `ass_name`** (default `None`, `stage5_render.py:434`) → no burned captions. Its URL goes
  into `jobs.clips[].video_url` (`run.py:200`, via `storage.upload_clip`).
- Editor render **overwrites the same path with a burned file**: `tasks.py:106-114`
  `render_clip_edit_job` → `render_edit_to_file(with_subtitles=True, out_rel="clips/{clip_id}.mp4")`,
  then `storage.upload_clip(... clips/{clip_id}.mp4 ...)`. In cloud this overwrites the same R2 key
  `{job}/{clip}.mp4` (`storage.py:23,117`).
- **Two URLs for one clip:** `jobs.clips[].video_url` (clean, batch) vs `clip_edits.render_url`
  (burned, editor) — `db.set_render_status` (`tasks.py:115`).
- **Frontend band-aid (anti-pattern):** `ClipPreview.tsx:74-95` calls `getRenderStatus` to detect
  whether the file is burned, then conditionally suppresses the libass overlay (`useLibass`,
  line 147). This teaches the grid to mimic state instead of removing the divergence. **WYSIWYG
  hole:** edit captions but don't re-render → `render_status` stays `"done"` with *stale* burned
  pixels → overlay stays off → grid shows old captions while editor shows new ones.
- **ExportMenu wrong file:** `ExportMenu.tsx:75` "With captions" → `href={subtitledUrl}` =
  `clip.video_url` (`ClipCard.tsx:103,29`) = `clips/<id>.mp4` = the **clean** batch file until an
  editor render overwrites it. So "With captions" downloads a *caption-less* file in the common case
  (seed symptom #6).

**Root cause:** one storage key (`clips/<id>.mp4` / R2 `{job}/{clip}.mp4`) is used as the
artifact for two semantically different things (clean reframe clip vs captioned export). No owner.

**Planned fix (unify, not patch):** the clip file is **clean forever** (reframe-only — batch already
does this; editor render must stop overwriting it). Captioned pixels become a *separate* artifact
produced on demand from the one ASS. Preview (grid + editor) **always** overlays libass on the clean
file → WYSIWYG by construction. "With captions" export resolves to the separately-rendered captioned
file. Delete the `burned`-detection band-aid in `ClipPreview`. (Detailed plan below once L1/L2 model
is fixed first.)
</details>

### D2 — Editor reframe plan 404 on cloud  ·  L4/L6  ·  ✅ fixed (local-verified)
**FIX:** new `GET /jobs/{job}/clips/{clip}/reframe` computes the plan via the **same**
`resolve_regions_accurate` the render uses (cache `analysis/acc_*.json`, source pulled from R2 via
`artifacts.ensure_source`) for the *current* edit intervals, flattened to clip-time by the pure
`regions_to_clip_time`. Frontend (`ClipEditorScreen`) fetches it via `api.getClipReframe` instead of
the raw `/media/...json`, re-fetches after interval edits, and the old `origStart` staleness guard is
gone — so preview-crop == render-crop in **both** environments and after a drag/trim (also resolves
HANDOFF §0.1 #2). Fetch stays non-fatal (falls back to center on error). **Evidence:** `just check`
green; `test_reframe_endpoint_returns_flat_clip_time_regions`, `test_reframe_endpoint_404_missing_clip`,
`test_regions_to_clip_time_offsets_by_interval_durations`. ⚠️ **Cost:** editor-open may run the heavy
ASD planner once per interval if `acc_*.json` is cold (shared with render). Cheaper-but-divergent
alternative (persist batch plan to R2/Postgres) noted as follow-up. Cloud not yet exercised (secrets).

<details><summary>original investigation</summary>
**Evidence:** `ClipEditorScreen.tsx:210` does `fetch(media/<job>/reframe_<clip>.json)` straight off
`/media` StaticFiles. The file is written by the batch reframe to the **run_job** container's scratch
disk (`stage3_reframe.py:653`), and is **never** uploaded to R2 nor stored in Postgres. On cloud the
web/editor container's `/media` doesn't have it → 404 → `setRawRegions(null)` → `frame` useMemo
returns `null` (`ClipEditorScreen.tsx:660`) → `PreviewPlayer` falls back to `mode:"fill", cx:0.5`
(center crop) ≠ the rendered crop.

**Root cause:** the editor's frame preview reads a *batch artifact by raw file path* that only exists
on the batch container's disk, instead of a durable, env-agnostic source.

**Planned fix:** add `GET /jobs/{job}/clips/{clip}/reframe` returning the regions computed by the
**same** `resolve_regions_accurate` the editor render uses — so editor-preview plan == editor-render
plan == one source (and it reflects the *current* edit intervals, also fixing the stale-after-drag
issue, HANDOFF §0.1 #2). Frontend fetches that endpoint instead of the raw `/media/...json`.
</details>

### D3 — PreviewPlayer mounts the source video 4×  ·  L6  ·  ✅ fixed (local-verified)
**FIX:** the blur-bg `<video>` is now rendered only when `mode === "fit"`; each `SplitHalf` sets
`src` only when `active` (split). The master video stays always-on. So in the common `fill` case only
1 decoder loads the source — on cloud that's 1 presigned-R2 fetch, not 4 → no `NotSupportedError ×N`.
**Evidence:** `just check` green (tsc/eslint). Cloud playback across all elements pending live secrets.

<details><summary>original investigation</summary>
**Evidence:** `PreviewPlayer.tsx` renders four `<video src={src}>`: master (`videoRef`, line 201),
blur-bg `auxARef` (line 188), and two `SplitHalf` (line 220-221, src at line 344). The blur-bg and
split halves set `src` **unconditionally** (only hidden via CSS `hidden`/`opacity-0`). All four
decode/fetch the source — on cloud that's 4× presigned-R2 fetches of a large file → `NotSupportedError`
×N + jank (seed symptom).

**Root cause:** secondary videos are always mounted with a live `src` even when their mode is inactive.

**Planned fix:** lazy `src` — set it on blur-bg only in `fit` mode and on split halves only in `split`
mode (mount/unmount or conditional `src`). Master stays always-on.
</details>

### D4 — Duplicate reframe resolver (legacy)  ·  L3  ·  ✅ fenced (commit `6bc7c2a`)
**Evidence:** `app/editor/reframe_cache.py` has TWO planners: `resolve_regions` + `analyze_source_range`
(5fps faces, `detect_cuts` in **seconds**, no ASD) and `resolve_regions_accurate` (frame-accurate,
ASD, the Δ=0 path). Confirmed the legacy pair is called ONLY by `deploy/modal/bench.py` +
`deploy/modal/clipflow_modal.py` + tests — never the product path (editor `/reframe`, editor render
`render_edit_to_file`, batch `run.py` all use `resolve_regions_accurate`).

**The real trap (not a live bug):** `clipflow_modal.py`'s header CLAIMED "exactly the same trio as
`render_edit_to_file`, no dupes" — but it calls the **legacy** planner, while `render_edit_to_file`
moved to `resolve_regions_accurate`. A false "same code" comment that could lure a future agent into
wiring the flash-prone path into the product.

**FIX (decided: fence, not delete):** deleting would force rewriting both deploy/bench scripts +
removing their tests — risky for tooling the founder may run, out of scope. Instead: docstrings on both
legacy functions now warn **LEGACY / BENCHMARK-ONLY (D4)** and point at `resolve_regions_accurate`;
corrected the stale `clipflow_modal.py` header (marked it a superseded spike using the legacy planner).
Docs only, no logic change → Δ=0 invariant untouched.

### D5 — `row_to_wire` hardcodes `source_kind="youtube"`  ·  L2  ·  ✅ fixed (commit `63ebea5`)
**Evidence:** `row_to_wire` always emitted `"source_kind": "youtube"` even when the job came from
`POST /jobs/upload` (inserts `source_type="upload"`). **FIX:** derive `source_kind` from the row's
`source_type` (`"upload"` → upload, else youtube safe default). The row already carries `source_type`
in both SQLite and Postgres. +1 pure test. No UI component reads `source_kind` today (cosmetic wire
accuracy), but the wire is now honest.

### D6 — Stale presigned R2 clip/render URLs → 403  ·  L1/L2/L4  ·  ✅ fixed (commit `db114ae`)
**The central CLOUD disease** (brief's seed bug). `storage.upload_clip` (cloud, no `R2_PUBLIC_URL`)
minted a **presigned** GET URL at write time with `signed_url_ttl` (default 604800 = the R2/S3 SigV4
**max** of 7 days; the founder's `.env` sets **3600 = 1 hour**) and baked it into `jobs.clips[].video_url`
+ `clip_edits.render_url`. On read, `row_to_wire`/`get_render` served it **as-is** (`http → as-is`). So a
user returning to their dashboard an hour (or a week) after generating clips gets **403 on every clip
and download** — the exact "works, then breaks" pattern. The Modal secret command sets `STORAGE_BACKEND=r2`
but **not** `R2_PUBLIC_URL` → the presigned (stale) branch is the live cloud path.

**The divergence:** the **source** video already did this RIGHT — `GET /jobs/{job}/source.mp4` re-presigns
on **every** read (302). Clips and render_url did NOT — they baked a time-bomb into the DB.

**FIX (unify on the durable source-video pattern — re-presign on read):**
- `storage.upload_clip` (cloud, no public URL) now returns a **durable marker** `r2://<key>` (no expiry)
  instead of a presigned URL. `R2_PUBLIC_URL` mode is already durable → unchanged.
- `storage.resolve_media_url(stored)` re-presigns `r2://<key>` with a fresh signed URL (single re-sign
  point for both clips and render_url).
- `db.row_to_wire` (PURE, unchanged purity) leaves `r2://` markers untouched (only true relative paths
  get the `media/<job>/…` prefix). `db.get_job` re-presigns each clip's marker on read (I/O wrapper).
- `main.get_render` re-presigns `render_url` `r2://` markers on read.
- **Backward compat:** historical cloud rows with baked `http` presigned URLs still pass through (they
  were already going to expire); only NEW jobs get the durable marker. No migration needed.
- **Evidence:** `just check` green, **471 tests** (+4: `test_key_ref_round_trips_the_object_key`,
  `test_is_r2_key_ref_rejects_plain_urls_and_paths`, `test_cloud_row_keeps_r2_key_ref_marker_untouched`,
  `test_get_job_re_presigns_r2_key_ref_on_read`). REFRAME_FPS_GRID untouched (URL-resolution only).
- ⚠️ **Cloud not exercised** (needs founder R2 secrets). By construction env-agnostic; the local
  `STORAGE_BACKEND=local` path is unchanged (returns relative `clips/…`). Live check: after `modal deploy`,
  generate a job, wait > `SIGNED_URL_TTL`, reload the dashboard → clips must still play (each `GET /jobs/{id}`
  mints a fresh presign). Or set `R2_PUBLIC_URL` for a permanent CDN domain (also fixes it).
- ⚠️ **ОБНОВЛЕНО 2026-06-17:** в живом Modal-образе `R2_PUBLIC_URL=https://cdn.quip.ink` **уже выставлен**
  (`deploy/modal/worker.py:114`) → новые клипы получают **постоянный CDN-URL**, а ветка `r2://`-re-presign
  стала путём ТОЛЬКО для легаси-строк (до `db114ae`). Тезис выше «but **not** `R2_PUBLIC_URL` → presigned
  is the live cloud path» описывает момент фикса, а не текущий прод. Дефолт `config.py` —
  `signed_url_ttl=604800` (7 дней), не 3600.

---

## Regression checklist (re-run after every fix; never let a lower fix break a verified upper item)

- [x] **L0** `just check` green — **472 tests** (after D4/D5/D6).
- [ ] **L0** Cloud path exercised (or exact repro documented if live cloud needed). D6 repro documented.
- [x] **L1** Clip file on disk after batch = clean; captioned export is a separate artifact
      (`clips/<id>_captioned.mp4`). Verified by `test_render_job_writes_captioned_never_overwrites_clean`.
- [x] **L1/L2** R2 clip/render URLs are durable (D6): DB stores `r2://<key>`, re-presigned on every
      read → no stale-403. Local `clips/…` relative path unchanged. Verified by 4 new tests.
- [x] **L2** `row_to_wire` URL resolution correct (http/`r2://` as-is / relative→media) local + cloud;
      `source_kind` honest for uploads (D5).
- [x] **L3** REFRAME_FPS_GRID Δ=0 unaffected: D1–D3 did NOT touch the temporal grid
      (`reframe_segment`/`plan_regions`/`build_shots_frames`/render). D2 only ADDED a preview-only
      pure flatten helper + an endpoint wrapping the unchanged `resolve_regions_accurate`. The real
      D1 render exercised the full reframe→render path with no errors.
- [x] **L4** `/export/captioned.mp4` renders current edit-state with subtitles; "With captions"
      resolves to a truly-captioned file in every state (D1). `/ass` == ffmpeg ASS: pre-existing,
      unchanged by D1.
- [x] **L6** grid preview == editor preview (both always overlay libass on the clean clip); no
      double captions after an editor render (clean clip never overwritten).
- [x] **L6** editor frame preview crop == rendered crop (D2: both via `resolve_regions_accurate`;
      cloud serves it from the endpoint not a missing `/media` file). Cloud live-check pending secrets.
- [x] **L6** Source video mounted once unless split/fit needs aux (D3). No `NotSupportedError` — cloud
      live-check pending secrets.

---

### S1 — Upload path "two downloads" / redundant transcode  ·  L3  ·  ✅ confirmed not-a-bug
`stage0_import.import_upload` does a `-c copy` remux first (no transcode) and only re-encodes if the
codec is mp4-incompatible — a one-time prep, not a redundant fetch. The "Downloading"→"Preparing"
relabel already landed earlier. The only network round-trip is the inherent client→worker (→R2) upload.

---

## Session summary (2026-06-14, agent "debugger")

**Fixed & committed (each `just check` green; bottom→top):**
- **D1** `bdc554c` — clean clip forever + separate `_captioned.mp4` artifact; grid/editor always
  overlay libass; "With captions" never resolves to the clean clip. Real-verified (clean clip
  byte-identical after an editor render). Kills double-captions + caption-less "With captions".
- **D2** `c3276c8` — `/jobs/{job}/clips/{clip}/reframe` endpoint (same `resolve_regions_accurate` as
  render) replaces the raw `/media/...json` fetch that 404'd on cloud → preview-crop == render-crop
  in both envs and after interval edits.
- **D3** `0310214` — lazy-mount the editor preview's blur-bg + split-half videos → 1 source decoder
  in the common case (no `NotSupportedError ×4` on cloud).

**Structural takeaway:** all three were one disease — *one storage key / one raw file path meaning
different things across surfaces/environments*. Each fix deleted the divergent path (or band-aid) and
routed every surface through a single source: the clean clip + one ASS for captions; one reframe
planner for both preview and render.

**Deferred (documented, low priority, not in product path):** D4 (legacy `resolve_regions`/
`analyze_source_range` duplicate planner — bench-only), D5 (`row_to_wire` hardcodes
`source_kind="youtube"`).

## Session summary (2026-06-14, agent "debugger2" — continued sweep)

Baseline on entry: `main`, `just check` green, **467 tests** (D1–D3 + billing video-minutes +
modal Deno had landed since the first session's audit).

**Fixed & committed (each `just check` green; bottom→top, one commit per fix):**
- **D6** `db114ae` — durable R2 clip/render URLs. The high-value cloud correctness bug: presigned URLs
  with a 1h–7d TTL were baked into the DB and served stale → 403 on every clip/download after the TTL.
  Unified on the source-video pattern (store `r2://<key>`, re-presign on read). +4 tests (467→471).
- **D5** `63ebea5` — `source_kind` reflects upload jobs (was hardcoded `"youtube"`). +1 test (→472).
- **D4** `6bc7c2a` — fenced the legacy reframe planner as benchmark-only (docs); corrected
  `clipflow_modal.py`'s false "same code as the live render path" header. Docs only.

**Structural takeaway (same disease, one more environment):** D6 is the *cloud* face of the exact
divergence D1 was the *render* face of — **one piece of data (a clip's location) taking two code paths
that disagree** (durable re-presign for source, baked-stale presign for clips). The fix deletes the
divergent path and routes clips/render through the single durable pattern source already used. D4/D5
close the audit's two deferred items: D4 fences (not deletes) the dormant second planner with honest
docs so nobody re-wires the flash-prone path; D5 makes the wire honest about upload jobs.

**Verified-clean during the sweep (no fix needed):** no silent `except: pass` in the worker (the lone
`except Exception` in `_meter` logs via `_log.exception` by design — metering must not crash a done job);
`artifacts.py` dual-mode raises `JobError` (no silent fallbacks); editor reframe is fully unified on
`resolve_regions_accurate` (no leftover raw `/media/...reframe.json` fetch); `compile_ass` is the single
ASS source for both libass preview and ffmpeg export (`burn` toggle honored in both → WYSIWYG holds);
the billing video-minutes model (MAX_VIDEO_MINUTES=180, gate after probe) is intact and untouched;
D1's clean-clip-forever model is intact.

**Known limitation noted (not fixed — pre-existing, out of scope):** the dev mock route
(`apps/web/app/api/mock/`) only implements `POST /jobs` + `GET /jobs/{id}`, not the editor endpoints.
With `NEXT_PUBLIC_WORKER_URL` unset the grid works but opening the editor 404s on `/edit`/`/ass`/etc.
That's a demo-mock limitation, not a product divergence; fully emulating the editor in the mock is large
scope. Documented for the founder.

## Open / needs founder
- **Live cloud verification** (Modal+R2+Supabase) — the three fixes are by-construction env-agnostic
  but unverified on real cloud. After `modal deploy` (see `modal-boevoy-deploy-state` memory), verify:
  (1) editor render → R2 key `{job}/{clip}_captioned.mp4` exists and the clean `{job}/{clip}.mp4` is
  untouched; (2) `GET /jobs/{job}/clips/{clip}/reframe` returns regions (not 404) on the web container;
  (3) editor source plays with one `<video>` (no `NotSupportedError`); (4) grid shows captions (libass)
  with no double-draw after a render.
- **Product/UX call:** with "With captions" now always on-demand-correct, the editor's async **Render**
  button + dirty indicator are now an optional "pre-bake" (warm cache + progress), no longer the source
  of the download. Decide whether to simplify that UX (out of scope here; left functional).
- **Cost call (D2):** if cold-cloud editor-open feels slow (heavy ASD on first `/reframe`), persist the
  batch reframe plan to R2/Postgres and serve that for the original interval (follow-up).
- **D6 live verification (cloud):** after `modal deploy`, generate a job, wait longer than
  `SIGNED_URL_TTL` (`.env` = 1h), reload the dashboard → clips must still play and download (each
  `GET /jobs/{id}` re-presigns the `r2://` marker). Alternatively set `R2_PUBLIC_URL` to a Cloudflare
  r2.dev/custom domain — clips then get a permanent CDN URL (also fixes D6, no re-presign needed).
  **Recommendation:** set `R2_PUBLIC_URL` in the Modal secret for the cheapest, most robust path.
- **Historical cloud rows:** jobs created before `db114ae` have baked (expiring) `http` presigned URLs
  in Postgres `jobs.clips`. They'll 403 once expired (they already would have). Only re-running those
  jobs, or a one-off backfill rewriting their `video_url` to `r2://<key>`, recovers them. Not worth a
  migration unless old jobs matter; new jobs are correct.
