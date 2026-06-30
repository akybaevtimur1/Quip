# Render optimization — PROPOSAL (2026-06-30)

> **Status: PROPOSAL ONLY** (founder asked to research + propose, not implement, for the batch
> render path). The one exception — compositing captions onto the already-rendered clip instead of
> re-rendering from source — is being implemented in the **download** track (it lives in
> `tasks.render_edit_to_file`, the export path the founder explicitly asked to fix), not here.
> This doc is the menu of remaining batch-render levers + a recommendation. Source of the numbers:
> read-only recon of `stage5_render.py` / `stage3_reframe.py` / `run.py` + real `services/worker/data/runs.jsonl`.

## 1. Where render latency actually comes from (measured)

From `runs.jsonl` (local sequential, founder machine, 1080p ~29.97fps, 4 clips, ~7-8 min source):

| run | clips | reframe (sum) | render/encode (sum) | per-clip reframe | per-clip encode |
|-----|-------|--------------|---------------------|------------------|-----------------|
| job_17bb726bc1ec | 4 | 360 s | 185 s | ~90 s | ~46 s |
| job_b530fc7f5488 | 4 | 217 s | 138 s | ~54 s | ~35 s |
| job_060aaf70f05c | 4 | 330 s | 117 s | ~82 s | ~29 s |

**Key finding: the founder said "render is slow", but the encode (libx264) is only ~1/3 of per-clip
compute. The dominant cost is the reframe/ASD CV stage (~2/3).** In the cloud the per-clip
containers run fully parallel (`reframe_render_clip.starmap`), so job wall-clock ≈ `max(per-clip)` +
cold-start + the sequential pre-work (download→transcribe→select), not the sum above.

Drivers, ranked by impact:
1. **Reframe CV+ASD** (~50-90 s/clip): MediaPipe per-frame face detect + torch ASD forward + PySceneDetect. All CPU.
2. **Redundant source decode** — each clip span is decoded **3×**: (a) a full ultrafast re-encode just to feed PySceneDetect (`stage3_reframe.py:650`), (b) JPG frame extract @25fps for ASD (`asd_reframe.py:88`), (c) the render filtergraph (`stage5_render.py:412`) — plus a wav extract.
3. **Encode** (~29-46 s/clip): libx264 `veryfast`(free)/`medium`(paid) at 1080×1920; **audio is always re-encoded to AAC 128k** even when unedited.
4. **Per-clip source re-download from R2** (fan-out): N clips = N downloads + N decodes of the same 50-160 MB source.
5. **Container cold start** (`min_containers=0`): torch + mediapipe import + ASD weight load, once per container.

## 2. The "applied after render" inventory (the founder's phrase, precisely)

The base clip `clips/<id>.mp4` is **reframed + (free) watermarked, but has NO captions/hook burned in**
(`run.py:184` calls `render_clip` with no `ass_name`). Captions + hook are a **browser libass overlay**;
they are burned into pixels only on demand (`export/captioned.mp4` → `render_edit_to_file`), which today
**re-runs the entire reframe+encode from source**. That is the biggest waste, and it is what the
download track's composite-ASS fast path eliminates (`ffmpeg -i clips/<id>.mp4 -vf subtitles=… -c:a copy`).

## 3. Levers (ranked: impact · risk · grid-invariant flag)

> Grid rule: anything that changes `trim=start_frame`/`fps`/region boundaries in
> `stage3_reframe`/`stage5_render` is **HIGH RISK** (re-read `REFRAME_FPS_GRID_INVARIANT.md`).

| # | Lever | What | Impact | Risk | Grid |
|---|-------|------|--------|------|------|
| **L1** | **Composite-ASS (already in download track)** | Burn captions onto the existing baked clip, not re-render from source | **Very high** for export/editor | Med | **SAFE** |
| **L2** | **Audio stream-copy** | `-c:a copy` when the clip is a single contiguous span with no audio edit (keep AAC fallback for multi-interval concat / non-AAC sources) | Medium (drops an encode + decode) | Low-Med | **SAFE** |
| **L5** | **Preset tuning** | Paid is `medium`; `medium → veryfast` at a slightly lower CRF (~crf17/veryfast) gives ~equal perceptual quality at a fraction of encode time | Medium (encode is ~1/3) | Low (quality/size tradeoff only) | **SAFE** (encoder-only, Δ=0) |
| **L6** | **Stop re-downloading source per fan-out container** | Modal Volume / shared cache for `source.mp4`, or batch a few clips per container to amortize download + model-load | Medium (wall-clock + decode; R2 egress is free) | Low-Med (Modal plumbing) | **SAFE** (infra) |
| **L7** | **Cut cold start** | Small warm pool or trim lazy torch/mediapipe imports + pre-load ASD weights | Low-Med (seconds/clip) | Low (cost) | **SAFE** |
| **L3** | **Deduplicate the per-clip decode** | Extract the aligned segment ONCE (frames + wav) and feed PySceneDetect + ASD + render from it, instead of 3 decodes | **High** (removes 1-2 full segment decodes/clip — the #2 driver) | **HIGH** — touches `detect_scene_cuts` frame numbering / `_scene_cut_offset` / fps resample = exactly the grid invariant. Must be done frame-grid-faithful + validated. | **HIGH — flag** |
| **L8** | **Hardware encode (NVENC)** | — | encode-only | **Reject**: NVENC needs a GPU; bench proved GPU ≈1.0× for the CPU-bound reframe, so you'd pay GPU price for the whole reframe stage, and NVENC 1080p quality at these CRFs is worse per-bit than x264 | n/a |

## 4. Recommendation

**Do (safe, high ROI, no grid risk):**
- **L1** — already happening in the download track (the single biggest win for the "after render" pain).
- **L2 (audio copy)** + **L5 (preset)** — small, encoder-only, Δ=0 grid-safe; together they meaningfully cut the encode third with no quality loss. Good "phase 2" once the download/upload/i18n/font work lands.
- **L6 / L7** — infra levers for when concurrency/scale matters; measure first.

**Defer / careful:**
- **L3** (dedupe decode) is the biggest *reframe-stage* win but it is the highest grid risk — it must be
  done against the 29.97fps grid fixture with `verify_grid_fix.py` (Δ=0) **and** eyeballed frame-by-frame
  on a real render at a content seam, per the reframe rules. Worth a dedicated, isolated session — not a
  casual change.

**Reject:**
- **L8** NVENC — confirmed cost-negative + quality-negative for this CPU-bound pipeline.

## 5. How to benchmark before/after (no prod, no cloud)
- `runs.jsonl` already records per-stage `reframe`/`render` seconds.
- Isolated encode A/B: a small `uv run python` harness importing `stage5_render.render_clip`, timed across
  `crf/preset` and `-c:a copy` variants on a cached job (`services/worker/data/job_17bb726bc1ec`, 29.97fps).
- Any L3 change MUST also run `tmp/verify_grid_fix.py` (expect MAX frame-error 0.00000) on a ≠25fps fixture.
