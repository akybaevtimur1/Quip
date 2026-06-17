# Parallel Clip Render + Preview Decouple — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut end-to-end job wall-time by (#1) rendering the per-clip stages 3–5 in parallel across Modal containers instead of one sequential loop, and (#3) taking the full-source preview transcode off the critical path.

**Architecture:** `run_pipeline` keeps doing import → transcribe → select on the coordinator container, then uploads `source.mp4` to R2 **before** the clip phase. The per-clip body (reframe + render + upload) is extracted into one shared pure-orchestration helper `render_one_clip`. On Modal it is fanned out via a new `reframe_render_clip` Modal function (`starmap`, one container per clip); locally it runs as the same sequential loop (identical behavior). Each fan-out container pulls `source.mp4` from R2 via the existing, proven `artifacts.ensure_source` (the editor's `render_job` already does exactly this). The preview proxy becomes a separate `preview_job` Modal function spawned right after the source upload, so it builds **concurrently** with the clips and never blocks `set_done`; the editor already falls back to source when the proxy is missing.

**Tech Stack:** Python 3.12, Modal (`starmap`/`spawn`), FastAPI worker, ffmpeg, pydantic, pytest.

**Invariant guard:** This plan **never edits** `stage3_reframe.py`, `stage5_render.py`, or `editor/reframe_cache.py` — it only *calls* `reframe_segment` / `render_clip`. The frame-grid flash-fix invariant (`docs/REFRAME_FPS_GRID_INVARIANT.md`, commit `9e57981`) is untouched. No `models.py` changes → no `just types` codegen.

---

## File Structure

- **Modify** `services/worker/app/run.py` — extract per-clip body into `render_one_clip`; add `build_clip_out` + `clip_spawn_args` pure helpers; replace the sequential loop with a dispatcher; move `upload_source` before the clip phase; decouple preview.
- **Modify** `services/worker/app/dispatch.py` — add `map_render_clips(args)` (Modal `starmap`) used by the cloud branch.
- **Modify** `deploy/modal/worker.py` — add `reframe_render_clip` and `preview_job` Modal functions.
- **Create** `services/worker/tests/unit/test_parallel_render.py` — unit tests for the pure helpers (`clip_spawn_args`, `build_clip_out`, local-vs-cloud dispatch selection).

No DB schema / wire-contract / `packages/shared` changes.

---

### Task 1: Pure helper — `clip_spawn_args`

Builds the ordered list of fan-out argument tuples from segments + meta. Pure (no I/O), so unit-testable.

**Files:**
- Modify: `services/worker/app/run.py`
- Test: `services/worker/tests/unit/test_parallel_render.py`

- [ ] **Step 1: Write the failing test**

```python
# services/worker/tests/unit/test_parallel_render.py
from app.models import Segment
from app.pipeline.stage0_import import SourceMeta
from app.run import clip_spawn_args


def _seg(start: float, end: float) -> Segment:
    return Segment(start=start, end=end, reason="r", hook="h", why_works="w")


def _meta() -> SourceMeta:
    return SourceMeta(
        job_id="job_x", source="upload", url=None, title="t",
        duration=120.0, fps=30.0, width=1920, height=1080,
    )


def test_clip_spawn_args_one_tuple_per_segment_indexed_from_one():
    segs = [_seg(0, 10), _seg(20, 35)]
    meta = _meta()
    args = clip_spawn_args("job_x", segs, meta)
    assert len(args) == 2
    # (job_id, clip_index, seg_dict, meta_dict)
    assert args[0][0] == "job_x"
    assert args[0][1] == 1
    assert args[1][1] == 2
    assert args[0][2]["start"] == 0
    assert args[1][2]["end"] == 35
    assert args[0][3]["width"] == 1920
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_parallel_render.py::test_clip_spawn_args_one_tuple_per_segment_indexed_from_one -v` (cwd `services/worker`)
Expected: FAIL — `ImportError: cannot import name 'clip_spawn_args'`.

- [ ] **Step 3: Write minimal implementation**

Add to `services/worker/app/run.py` (near the top-level helpers, after `_gemini_cost`):

```python
def clip_spawn_args(
    job_id: str, segments: list[Segment], meta: SourceMeta
) -> list[tuple[str, int, dict[str, Any], dict[str, Any]]]:
    """Аргументы фан-аута: один кортеж на сегмент (job_id, clip_index, seg, meta). PURE.

    clip_index 1-based (совпадает с clip_id ``clip_{i:02d}``). seg/meta — model_dump для
    переноса через границу Modal (cloudpickle-дружелюбные dict'ы)."""
    md = meta.model_dump()
    return [(job_id, i, seg.model_dump(), md) for i, seg in enumerate(segments, start=1)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: same as Step 2. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/worker/app/run.py services/worker/tests/unit/test_parallel_render.py
git commit -F <msg-file>   # see "Commit messages" note at bottom
```

---

### Task 2: Pure helper — `build_clip_out`

Assembles a `ClipOut` from a segment + transcript words + the rendered `video_url`. Moving this out of the loop lets the coordinator build clips from fan-out results.

**Files:**
- Modify: `services/worker/app/run.py`
- Test: `services/worker/tests/unit/test_parallel_render.py`

- [ ] **Step 1: Write the failing test**

```python
def test_build_clip_out_maps_segment_and_url():
    from app.models import Word
    from app.run import build_clip_out
    seg = _seg(10, 20)
    seg = seg.model_copy(update={"type": "story", "score": 0.8, "hook_style": "bold"})
    words = [Word(text="hello", start=11.0, end=11.5, confidence=0.9)]
    clip = build_clip_out("clip_03", seg, words, "https://cdn/clip_03.mp4")
    assert clip.id == "clip_03"
    assert clip.start == 10
    assert clip.end == 20
    assert clip.duration == 10
    assert clip.video_url == "https://cdn/clip_03.mp4"
    assert clip.hook == "h"
    assert clip.transcript == "hello"
    assert [w.text for w in clip.words] == ["hello"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_parallel_render.py::test_build_clip_out_maps_segment_and_url -v`
Expected: FAIL — `cannot import name 'build_clip_out'`.

- [ ] **Step 3: Write minimal implementation**

Add to `run.py`:

```python
def build_clip_out(
    clip_id: str, seg: Segment, transcript_words: list[Word], video_url: str
) -> ClipOut:
    """Сегмент + слова транскрипта + готовый video_url → ClipOut (wire). PURE.

    Сниппет/слова считаются по окну сегмента — НЕ зависит от того, где рендерился клип
    (локально или на фан-аут-контейнере)."""
    return ClipOut(
        id=clip_id,
        start=seg.start,
        end=seg.end,
        duration=round(seg.end - seg.start, 2),
        reason=seg.reason,
        type=seg.type,
        score=seg.score,
        video_url=video_url,
        thumbnail_url=None,
        transcript=_snippet(transcript_words, seg.start, seg.end),
        words=words_in_segment(transcript_words, seg.start, seg.end),
        hook=seg.hook,
        why_works=seg.why_works,
        hook_style=seg.hook_style,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: same as Step 2. Expected: PASS.

- [ ] **Step 5: Commit** (as in Task 1).

---

### Task 3: `render_one_clip` — the shared per-clip body

The reframe + render + upload for a single clip, returning a picklable result dict. Used by both the local loop and the Modal fan-out function. I/O wrapper (no new unit test of ffmpeg/MediaPipe — covered by e2e); but its result shape is locked by Task 4's dispatch test.

**Files:**
- Modify: `services/worker/app/run.py`

- [ ] **Step 1: Implement `render_one_clip`**

Add to `run.py`:

```python
def render_one_clip(
    out: Path, source_name: str, clip_index: int, seg: Segment, meta: SourceMeta
) -> dict[str, Any]:
    """Stages 3–5 для ОДНОГО клипа: reframe → render → upload. Возвращает picklable result.

    Общее ядро (DRY): локальный цикл и Modal-фан-аут зовут ЭТУ функцию. Настройки берём из
    get_settings() ВНУТРИ (на фан-аут-контейнере свой процесс/env). source_name относительно out.
    НЕ трогает stage3/stage5 — только вызывает (инвариант кадровой сетки цел)."""
    s = get_settings()
    clip_id = f"clip_{clip_index:02d}"
    t0 = time.perf_counter()
    regions, face_found = reframe_segment(
        out / source_name, meta.width, meta.height, seg.start, seg.end,
        clip_id=clip_id, out_dir=out, fps=meta.fps, mode_setting=s.reframe_mode,
        speaker_crop_scale=s.reframe_speaker_crop_scale,
        face_fps=s.reframe_face_fps, smoothing=s.reframe_smoothing,
        min_hold_sec=s.reframe_min_hold_sec,
        speak_threshold=s.reframe_speak_threshold,
        scene_threshold=s.reframe_scene_threshold,
        split_enabled=s.reframe_split_enabled,
        wide_speak_min=s.reframe_wide_speak_min,
    )  # fmt: skip
    reframe_lat = round(time.perf_counter() - t0, 2)
    render_lat = render_clip(
        out, source_name, seg.start, f"clips/{clip_id}.mp4",
        regions=regions, src_w=meta.width, src_h=meta.height, fps=meta.fps,
        engine=s.reframe_engine,
    )  # fmt: skip
    video_url = storage.upload_clip(out / "clips" / f"{clip_id}.mp4", out.name, clip_id)
    n_fit = sum(1 for r in regions if r.mode == "fit")
    print(
        f"  {clip_id}: {seg.start:.1f}-{seg.end:.1f} face={face_found} "
        f"regions={len(regions)} fit={n_fit} render={render_lat}s"
    )
    return {
        "clip_id": clip_id,
        "clip_index": clip_index,
        "video_url": video_url,
        "reframe_lat": reframe_lat,
        "render_lat": render_lat,
        "face_found": face_found,
    }
```

Note: `out.name` is the `job_id` (job dir is `DATA_ROOT/<job_id>`). `upload_clip(path, job_id, clip_id)` matches the current call in the loop.

- [ ] **Step 2: Verify it imports**

Run: `uv run python -c "from app.run import render_one_clip"` (cwd `services/worker`)
Expected: no error.

- [ ] **Step 3: Commit** (as in Task 1).

---

### Task 4: Dispatcher — `dispatch.map_render_clips` + `run._render_all_clips`

Selects Modal fan-out (cloud) vs the in-process loop (local). Unit-test the selection by monkeypatching.

**Files:**
- Modify: `services/worker/app/dispatch.py`
- Modify: `services/worker/app/run.py`
- Test: `services/worker/tests/unit/test_parallel_render.py`

- [ ] **Step 1: Write the failing test (local branch loops in-process)**

```python
def test_render_all_clips_local_uses_loop(monkeypatch, tmp_path):
    import app.run as run_mod
    monkeypatch.setattr(run_mod.dispatch, "modal_spawn_enabled", lambda: False)
    calls = []
    def fake_one(out, source_name, clip_index, seg, meta):
        calls.append(clip_index)
        return {"clip_id": f"clip_{clip_index:02d}", "clip_index": clip_index,
                "video_url": f"u{clip_index}", "reframe_lat": 1.0, "render_lat": 2.0,
                "face_found": True}
    monkeypatch.setattr(run_mod, "render_one_clip", fake_one)
    segs = [_seg(0, 10), _seg(20, 35)]
    results = run_mod._render_all_clips("job_x", tmp_path, "source.mp4", segs, _meta())
    assert calls == [1, 2]
    assert [r["video_url"] for r in results] == ["u1", "u2"]
```

- [ ] **Step 2: Write the failing test (cloud branch fans out via dispatch)**

```python
def test_render_all_clips_cloud_uses_map(monkeypatch, tmp_path):
    import app.run as run_mod
    monkeypatch.setattr(run_mod.dispatch, "modal_spawn_enabled", lambda: True)
    seen = {}
    def fake_map(args):
        seen["args"] = args
        return [{"clip_id": f"clip_{a[1]:02d}", "clip_index": a[1], "video_url": f"u{a[1]}",
                 "reframe_lat": 1.0, "render_lat": 2.0, "face_found": True} for a in args]
    monkeypatch.setattr(run_mod.dispatch, "map_render_clips", fake_map)
    segs = [_seg(0, 10), _seg(20, 35)]
    results = run_mod._render_all_clips("job_x", tmp_path, "source.mp4", segs, _meta())
    assert len(seen["args"]) == 2
    assert [r["clip_index"] for r in results] == [1, 2]
```

- [ ] **Step 3: Run both tests to verify they fail**

Run: `uv run pytest tests/unit/test_parallel_render.py -k render_all_clips -v`
Expected: FAIL — `_render_all_clips` / `map_render_clips` not defined.

- [ ] **Step 4: Implement `map_render_clips` in `dispatch.py`**

```python
def map_render_clips(args: list[tuple[Any, ...]]) -> list[dict[str, Any]]:
    """Фан-аут per-clip рендера на Modal: одна функция-контейнер на клип (starmap).

    Возвращает результаты В ПОРЯДКЕ входа (Modal starmap сохраняет порядок). Вызывается ТОЛЬКО
    в Modal-режиме (coordinator run_job блокируется тут, пока клипы рендерятся параллельно)."""
    import modal

    fn = modal.Function.from_name(_MODAL_APP, "reframe_render_clip")
    return list(fn.starmap(args))
```

Add `from typing import Any` is already imported in dispatch.py (it imports `Any`). Confirm.

- [ ] **Step 5: Implement `_render_all_clips` in `run.py`**

Add `from app import dispatch` to run.py imports, then:

```python
def _render_all_clips(
    job_id: str, out: Path, source_name: str, segments: list[Segment], meta: SourceMeta
) -> list[dict[str, Any]]:
    """Stages 3–5 для ВСЕХ клипов. Modal → фан-аут (контейнер на клип, параллельно);
    локально → последовательный цикл (идентично прежнему поведению). Результаты — в порядке
    сегментов (для стабильного clip_index/ассемблинга ClipOut)."""
    if dispatch.modal_spawn_enabled():
        return dispatch.map_render_clips(clip_spawn_args(job_id, segments, meta))
    return [
        render_one_clip(out, source_name, i, seg, meta)
        for i, seg in enumerate(segments, start=1)
    ]
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_parallel_render.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit** (as in Task 1).

---

### Task 5: Wire `_render_all_clips` into `run_pipeline` + move `upload_source` up + decouple preview

Replace the old sequential loop block (`run.py:194-259`, the `for i, seg ...` loop through the preview-proxy block) with: upload source → kick off preview (cloud spawn / local inline-after) → fan-out → assemble clips.

**Files:**
- Modify: `services/worker/app/run.py`

- [ ] **Step 1: Replace the clip loop + preview block**

Replace the region from `# ── Stages 3–5: per-clip ...` through the `stages["preview_proxy"] = ...` block with:

```python
    # ── Источник в R2 ДО фан-аута: каждый клип-контейнер качает source из R2 (artifacts.ensure_source,
    #    тот же путь, что у editor-render). Локально upload_source — no-op (исходник на диске). ──
    storage.upload_source(out / "source.mp4", job_id)

    # ── #3 Preview-прокси СНЯТ с критического пути: на Modal — отдельная функция preview_job,
    #    спавним СЕЙЧАС → она строит прокси ПАРАЛЛЕЛЬНО с клипами и не держит set_done. Редактор
    #    фолбэчит на source, пока прокси не готов (storage.preview_read_url). Локально строим
    #    inline ПОСЛЕ клипов (dev: один процесс, клипы уже отданы). ──
    if dispatch.modal_spawn_enabled():
        dispatch.spawn("preview_job", job_id)

    # ── Stages 3–5: фан-аут per-clip (Modal) либо последовательный цикл (local). ──
    emit(JobStatus.rendering, 80)
    results = _render_all_clips(job_id, out, "source.mp4", segments, meta)
    results.sort(key=lambda r: r["clip_index"])
    clips: list[ClipOut] = [
        build_clip_out(r["clip_id"], seg, transcript.words, r["video_url"])
        for seg, r in zip(segments, results, strict=True)
    ]
    reframe_t = round(sum(r["reframe_lat"] for r in results), 2)
    render_t = round(sum(r["render_lat"] for r in results), 2)
    stages["reframe"] = reframe_t
    stages["render"] = render_t

    # Локально (нет Modal) preview строим inline ПОСЛЕ клипов (cloud уже спавнил выше).
    if not dispatch.modal_spawn_enabled():
        t0 = time.perf_counter()
        build_preview_proxy(
            out / "source.mp4", out / "preview.mp4",
            height=min(s.preview_height, meta.height), crf=s.preview_crf,
        )  # fmt: skip
        stages["preview_proxy"] = round(time.perf_counter() - t0, 2)
        storage.upload_preview(out / "preview.mp4", job_id)
```

- [ ] **Step 2: Remove the now-duplicated tail block**

Delete the old `# ── persist для облака ...` lines that did `storage.upload_source` + `storage.upload_preview` (both now handled above / by `preview_job`). KEEP `db.put_job_artifacts(...)`. Remove the now-unused `ttfc` variable and its `time_to_first_clip_sec` (set it to `None` in the run-line; with parallel rendering a per-clip TTFC is no longer meaningful from the coordinator).

Resulting run-line:
```python
        "time_to_first_clip_sec": None,
```

- [ ] **Step 3: Verify imports compile**

Run: `uv run python -c "import app.run"` (cwd `services/worker`)
Expected: no error. (Confirm `reframe_segment` import is still used by `render_one_clip`; the standalone `_extract`/loop no longer references it directly but the import stays.)

- [ ] **Step 4: Run the full worker unit suite**

Run: `uv run pytest tests/unit -q` (cwd `services/worker`)
Expected: PASS (no regressions; `test_tasks.py` etc. still green).

- [ ] **Step 5: Commit** (as in Task 1).

---

### Task 6: Add `reframe_render_clip` + `preview_job` Modal functions

**Files:**
- Modify: `deploy/modal/worker.py`

- [ ] **Step 1: Add the fan-out clip function**

After `render_job` (mirroring its decorator/bootstrap pattern, `cpu=4, memory=4096, serialized=True`):

```python
# Фан-аут per-clip (perf #1): один контейнер на клип, параллельно. source.mp4 скачивается из
# R2 (artifacts.ensure_source — тот же путь, что editor-render). timeout=1800 с запасом на
# длинный клип (reframe ASD ~реалтайм + рендер). Возвращает picklable result-dict (run.py
# собирает ClipOut). НЕ трогает stage3/stage5 — только зовёт reframe_segment/render_clip.
@app.function(
    secrets=[_SECRET, _BILLING_SECRET],
    timeout=1800,
    cpu=4,
    memory=4096,
    min_containers=0,
    serialized=True,
)
def reframe_render_clip(
    job_id: str, clip_index: int, seg: dict, meta: dict
) -> dict:
    """Stages 3–5 одного клипа на своём контейнере (параллельный фан-аут run_job)."""
    import sys

    if "/root" not in sys.path:
        sys.path.insert(0, "/root")
    from app import artifacts
    from app.models import Segment
    from app.pipeline.stage0_import import SourceMeta
    from app.run import render_one_clip

    src = artifacts.ensure_source(job_id)  # качает из R2 на свежий контейнер
    return render_one_clip(
        src.parent, src.name, clip_index, Segment.model_validate(seg), SourceMeta.model_validate(meta)
    )
```

- [ ] **Step 2: Add the preview function**

```python
# Preview-прокси (perf #3) — отдельная функция, спавнится run_job ПАРАЛЛЕЛЬНО с клипами, не
# держит set_done. Качает source из R2, строит ≤720p H.264 faststart, льёт preview в R2.
@app.function(
    secrets=[_SECRET, _BILLING_SECRET],
    timeout=1800,
    cpu=2,
    memory=2048,
    min_containers=0,
    serialized=True,
)
def preview_job(job_id: str) -> None:
    """Построить и залить preview.mp4 в R2 (вне критического пути джоба)."""
    import sys

    if "/root" not in sys.path:
        sys.path.insert(0, "/root")
    from app import artifacts, storage
    from app.config import get_settings
    from app.pipeline.stage0_import import build_preview_proxy

    s = get_settings()
    src = artifacts.ensure_source(job_id)
    meta = artifacts.load_meta(job_id)
    dst = src.parent / "preview.mp4"
    build_preview_proxy(src, dst, height=min(s.preview_height, meta.height), crf=s.preview_crf)
    storage.upload_preview(dst, job_id)
```

Note: `preview_job` reads `meta` from Postgres `job_artifacts`. **`run_pipeline` must `db.put_job_artifacts` before the source upload/spawn** OR `preview_job` clamps height differently. Decision: in Task 5, move `db.put_job_artifacts(...)` to run **before** `storage.upload_source` so `preview_job` (and any fan-out introspection) can read meta. (It already only needs meta/segments/transcript, all known after select.) Adjust Task 5 accordingly when implementing.

- [ ] **Step 3: Lint check the worker module locally**

Run: `uv run python -c "import ast; ast.parse(open('deploy/modal/worker.py').read())"` (cwd repo root)
Expected: no error. (Full `modal deploy` happens in Task 7.)

- [ ] **Step 4: Commit** (as in Task 1).

---

### Task 7: Gate + deploy + smoke

**Files:** none (verification only).

- [ ] **Step 1: Run the full commit gate**

Run (PowerShell, PATH refresh): `just check`
Expected: ruff + mypy + tsc + eslint + unit + anti-drift all green. If ruff-format reformats, `git add` + recommit.

- [ ] **Step 2: Deploy the worker**

Run (PowerShell): `$env:PYTHONIOENCODING="utf-8"; modal deploy deploy/modal/worker.py`
Expected: deploy succeeds; functions `reframe_render_clip` and `preview_job` appear.

- [ ] **Step 3: Smoke test a real job**

Trigger a small upload job via the app (or a known cached source), watch `modal app logs quip-worker`:
- Expect multiple `clip_NN:` render lines arriving ~concurrently (not 60s apart).
- Expect job reaches `done` without waiting on preview.
- Open the editor for that job → video loads (preview or source fallback).

- [ ] **Step 4: Push the branch**

```bash
git push -u origin perf/parallel-clip-render
```

---

## Commit messages (Cyrillic → file + `-F`)

Per `CLAUDE.md`: write the message to a UTF-8 (no BOM) file and `git commit -F <file>` from PowerShell (piping Cyrillic corrupts encoding). End commit bodies with the Co-Authored-By trailer. Conventional-commit subjects, e.g.:
- `perf(render): фан-аут per-clip рендера по контейнерам Modal (#1)`
- `perf(import): preview-прокси снят с критического пути (отдельный preview_job, #3)`

## Self-review notes

- **Spec coverage:** #1 = Tasks 1–6 (parallel fan-out, local loop preserved). #3 = Task 5 (source upload moved up, preview spawned parallel) + Task 6 `preview_job`.
- **No stage3/stage5/reframe_cache edits** → flash-fix invariant safe; **no models.py** → no codegen.
- **Dual-mode preserved:** local path = identical sequential loop + inline preview; cloud path = fan-out + spawned preview.
- **Cancellation:** fan-out is past the FREE→PAID boundary (`on_cancellable(False)`), where Stop is no longer offered, so no orphaned child containers.
- **Type consistency:** result dict keys (`clip_id`, `clip_index`, `video_url`, `reframe_lat`, `render_lat`, `face_found`) are identical across Task 3 (producer), Task 4 (dispatch/tests), Task 5 (consumer), Task 6 (Modal wrapper).
</content>
</invoke>
