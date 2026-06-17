"""Unit-тесты pure-хелперов параллельного фан-аута рендера (perf #1).

Тестируем ЧИСТУЮ часть: сборку аргументов фан-аута, ассемблинг ClipOut и выбор
ветки dispatch (Modal-фан-аут vs локальный цикл). Реальный ffmpeg/MediaPipe/ASD —
не здесь (это e2e), их обёртка render_one_clip замоканивается.
"""

from __future__ import annotations

from pathlib import Path

from app.models import Segment, Word
from app.pipeline.stage0_import import SourceMeta


def _seg(start: float, end: float) -> Segment:
    return Segment(
        start=start,
        end=end,
        reason="r",
        score=0.7,
        type="complete_thought",
        hook="h",
        why_works="w",
    )


def _meta() -> SourceMeta:
    return SourceMeta(
        job_id="job_x",
        source="upload",
        url=None,
        title="t",
        duration=120.0,
        fps=30.0,
        width=1920,
        height=1080,
    )


def test_clip_spawn_args_one_tuple_per_segment_indexed_from_one() -> None:
    from app.run import clip_spawn_args

    segs = [_seg(0, 10), _seg(20, 35)]
    args = clip_spawn_args("job_x", segs, _meta())
    assert len(args) == 2
    # (job_id, clip_index, seg_dict, meta_dict)
    assert args[0][0] == "job_x"
    assert args[0][1] == 1
    assert args[1][1] == 2
    assert args[0][2]["start"] == 0
    assert args[1][2]["end"] == 35
    assert args[0][3]["width"] == 1920


def test_build_clip_out_maps_segment_and_url() -> None:
    from app.run import build_clip_out

    seg = _seg(10, 20).model_copy(
        update={"type": "strong_quote", "score": 0.8, "hook_style": "bold"}
    )
    words = [Word(text="hello", start=11.0, end=11.5, confidence=0.9)]
    clip = build_clip_out("clip_03", seg, words, "https://cdn/clip_03.mp4")
    assert clip.id == "clip_03"
    assert clip.start == 10
    assert clip.end == 20
    assert clip.duration == 10
    assert clip.video_url == "https://cdn/clip_03.mp4"
    assert clip.hook == "h"
    assert clip.hook_style == "bold"
    assert clip.transcript == "hello"
    assert [w.text for w in clip.words] == ["hello"]


def test_render_all_clips_local_uses_loop(monkeypatch, tmp_path: Path) -> None:
    import app.run as run_mod

    monkeypatch.setattr(run_mod.dispatch, "modal_spawn_enabled", lambda: False)
    calls: list[int] = []

    def fake_one(
        out: Path, source_name: str, clip_index: int, seg: Segment, meta: SourceMeta
    ) -> dict:
        calls.append(clip_index)
        return {
            "clip_id": f"clip_{clip_index:02d}",
            "clip_index": clip_index,
            "video_url": f"u{clip_index}",
            "reframe_lat": 1.0,
            "render_lat": 2.0,
            "face_found": True,
        }

    monkeypatch.setattr(run_mod, "render_one_clip", fake_one)
    segs = [_seg(0, 10), _seg(20, 35)]
    results = run_mod._render_all_clips("job_x", tmp_path, "source.mp4", segs, _meta())
    assert calls == [1, 2]
    assert [r["video_url"] for r in results] == ["u1", "u2"]


def test_render_all_clips_cloud_uses_map(monkeypatch, tmp_path: Path) -> None:
    import app.run as run_mod

    monkeypatch.setattr(run_mod.dispatch, "modal_spawn_enabled", lambda: True)
    seen: dict[str, list] = {}

    def fake_map(args: list[tuple]) -> list[dict]:
        seen["args"] = args
        return [
            {
                "clip_id": f"clip_{a[1]:02d}",
                "clip_index": a[1],
                "video_url": f"u{a[1]}",
                "reframe_lat": 1.0,
                "render_lat": 2.0,
                "face_found": True,
            }
            for a in args
        ]

    monkeypatch.setattr(run_mod.dispatch, "map_render_clips", fake_map)
    segs = [_seg(0, 10), _seg(20, 35)]
    results = run_mod._render_all_clips("job_x", tmp_path, "source.mp4", segs, _meta())
    assert len(seen["args"]) == 2
    assert [r["clip_index"] for r in results] == [1, 2]
