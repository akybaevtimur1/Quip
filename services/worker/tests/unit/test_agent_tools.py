"""W3: тулзы агента — pure (compute_nudge) + интеграция диспетчера на tmp-store."""

from __future__ import annotations

import json

import pytest

from app import db
from app.agent import tools
from app.agent.tools import apply_tool, compute_nudge, words_in_window
from app.editor import store
from app.models import Segment, SourceKind, Transcript, Word
from app.pipeline.stage0_import import SourceMeta


class TestComputeNudge:
    def test_move_start_earlier(self) -> None:
        assert compute_nudge(10.0, 40.0, "start", -3.0) == (7.0, 40.0)

    def test_move_end_later(self) -> None:
        assert compute_nudge(10.0, 40.0, "end", 5.0) == (10.0, 45.0)

    def test_bad_edge_raises(self) -> None:
        with pytest.raises(ValueError):
            compute_nudge(10.0, 40.0, "middle", 1.0)


class TestWordsInWindow:
    def _words(self, n: int) -> list[Word]:
        # слово i живёт в [i, i+0.8]
        return [Word(text=f"w{i}", start=float(i), end=float(i) + 0.8) for i in range(n)]

    def test_includes_words_overlapping_window_only(self) -> None:
        words = self._words(60)
        # окно [10, 20]: w10..w20 пересекаются (w20 начинается на 20.0 == end → включаем)
        got = words_in_window(words, 10.0, 20.0, max_words=400)
        texts = [w["text"] for w in got]
        assert "w9" not in texts  # w9 = [9, 9.8] — целиком вне (end < 10)
        assert "w10" in texts
        assert "w20" in texts
        assert "w21" not in texts  # w21 = [21, 21.8] — целиком вне (start > 20)

    def test_word_shape_text_start_end_rounded(self) -> None:
        words = [Word(text="hi", start=1.23456, end=2.98765)]
        got = words_in_window(words, 0.0, 5.0, max_words=400)
        assert got == [{"text": "hi", "start": 1.23, "end": 2.99}]

    def test_max_words_cap_respected(self) -> None:
        words = self._words(100)
        got = words_in_window(words, 0.0, 100.0, max_words=10)
        assert len(got) == 10
        # cap берёт ПЕРВЫЕ max_words в окне (по порядку транскрипта)
        assert [w["text"] for w in got] == [f"w{i}" for i in range(10)]

    def test_empty_words(self) -> None:
        assert words_in_window([], 0.0, 50.0, max_words=400) == []

    def test_window_with_no_overlap(self) -> None:
        words = self._words(10)
        assert words_in_window(words, 500.0, 600.0, max_words=400) == []


def _setup(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "jobs.db")
    monkeypatch.setattr(store, "DATA_ROOT", tmp_path / "data")
    db.init_db()
    job = "jobA"
    d = tmp_path / "data" / job
    d.mkdir(parents=True)
    # клип 0..50с из сегмента; источник 120с
    (d / "segments.json").write_text(
        json.dumps([Segment(start=0.0, end=50.0, reason="r", score=0.5, type="hook").model_dump()]),
        encoding="utf-8",
    )
    words = [Word(text=f"w{i}", start=float(i), end=float(i) + 0.8) for i in range(60)]
    (d / "transcript.json").write_text(
        Transcript(language="ru", duration=120.0, words=words).model_dump_json(),
        encoding="utf-8",
    )
    (d / "meta.json").write_text(
        SourceMeta(
            job_id=job, source=SourceKind.upload, url=None, title="t",
            duration=120.0, fps=30.0, width=1920, height=1080,
        ).model_dump_json(),
        encoding="utf-8",
    )  # fmt: skip
    return job


def test_get_clip_state_returns_context(monkeypatch, tmp_path):
    job = _setup(monkeypatch, tmp_path)
    r = apply_tool("get_clip_state", {}, job_id=job, clip_id="clip_01")
    assert r["ok"] is True
    assert r["interval"] == [0.0, 50.0]
    assert r["source_seconds"] == 120.0
    assert r["language"] == "ru"
    assert "w0" in r["transcript"]


def test_set_interval_applies_and_reports(monkeypatch, tmp_path):
    job = _setup(monkeypatch, tmp_path)
    r = apply_tool(
        "set_interval", {"start_sec": 10.0, "end_sec": 40.0}, job_id=job, clip_id="clip_01"
    )
    assert r["ok"] is True
    assert r["after"] == "10.0-40.0s"
    state = apply_tool("get_clip_state", {}, job_id=job, clip_id="clip_01")
    assert state["interval"] == [10.0, 40.0]


def test_set_interval_clamps_beyond_source(monkeypatch, tmp_path):
    job = _setup(monkeypatch, tmp_path)
    # конец за пределами источника (120с) → кламп
    r = apply_tool(
        "set_interval", {"start_sec": 100.0, "end_sec": 200.0}, job_id=job, clip_id="clip_01"
    )
    assert r["ok"] is True
    assert "clamped" in r["summary"]


def test_set_interval_bad_args_returns_error(monkeypatch, tmp_path):
    job = _setup(monkeypatch, tmp_path)
    r = apply_tool("set_interval", {"start_sec": "x"}, job_id=job, clip_id="clip_01")
    assert "error" in r


def test_nudge_moves_edge(monkeypatch, tmp_path):
    job = _setup(monkeypatch, tmp_path)
    r = apply_tool(
        "nudge_interval", {"edge": "end", "delta_sec": -10.0}, job_id=job, clip_id="clip_01"
    )
    assert r["ok"] is True
    assert apply_tool("get_clip_state", {}, job_id=job, clip_id="clip_01")["interval"] == [
        0.0,
        40.0,
    ]


def test_regenerate_hook_uses_gemini_and_saves(monkeypatch, tmp_path):
    job = _setup(monkeypatch, tmp_path)
    from app.editor import hook_ops

    monkeypatch.setattr(hook_ops, "regenerate_hook", lambda *a, **k: ("Новый хук", "shock"))
    r = apply_tool("regenerate_hook", {"style_hint": "шок"}, job_id=job, clip_id="clip_01")
    assert r["ok"] is True and r["after"] == "Новый хук"
    assert apply_tool("get_clip_state", {}, job_id=job, clip_id="clip_01")["hook"] == "Новый хук"


def test_set_hook_text(monkeypatch, tmp_path):
    job = _setup(monkeypatch, tmp_path)
    r = apply_tool("set_hook_text", {"text": "  Ручной хук "}, job_id=job, clip_id="clip_01")
    assert r["after"] == "Ручной хук"


def test_request_render_triggers_render(monkeypatch, tmp_path):
    job = _setup(monkeypatch, tmp_path)
    called: list = []
    monkeypatch.setattr(tools, "_t_request_render", tools._t_request_render)  # keep
    import app.tasks as tasks_mod

    monkeypatch.setattr(tasks_mod, "render_clip_edit_job", lambda j, c: called.append((j, c)))
    monkeypatch.setattr(db, "set_render_status", lambda *a, **k: None)
    r = apply_tool("request_render", {}, job_id=job, clip_id="clip_01")
    assert r["ok"] is True and called == [(job, "clip_01")]


def test_get_surrounding_transcript_returns_window_with_source_ts(monkeypatch, tmp_path):
    job = _setup(monkeypatch, tmp_path)  # клип 0..50с, источник 120с, слова w0..w59
    r = apply_tool(
        "get_surrounding_transcript", {"seconds_around": 5.0}, job_id=job, clip_id="clip_01"
    )
    assert r["ok"] is True
    assert r["interval"] == [0.0, 50.0]
    assert "note" in r
    assert r["window"] == [0.0, 55.0]  # [0-5, 50+5] клампнуто к источнику снизу
    texts = [w["text"] for w in r["words"]]
    # окно [0, 55] → слова w0..w55 (start<=55)
    assert "w0" in texts
    assert "w55" in texts
    assert "w56" not in texts
    # каждое слово имеет source-таймстемпы
    assert all({"text", "start", "end"} <= set(w) for w in r["words"])


def test_get_surrounding_transcript_default_and_caps(monkeypatch, tmp_path):
    job = _setup(monkeypatch, tmp_path)
    r = apply_tool("get_surrounding_transcript", {}, job_id=job, clip_id="clip_01")
    assert r["ok"] is True
    # дефолт seconds_around=30 → окно [0, 80] клампнуто к [0, 120]
    assert r["window"][0] == 0.0
    assert r["window"][1] == 80.0


def test_unknown_tool_returns_error(monkeypatch, tmp_path):
    job = _setup(monkeypatch, tmp_path)
    r = apply_tool("delete_everything", {}, job_id=job, clip_id="clip_01")
    assert "error" in r and "unknown" in r["error"]


# ─────────────────────── get_video_map tests ───────────────────────


def _write_video_map(tmp_path, job: str, data: dict) -> None:
    """Write a video_map.json into the job data dir (mirrors save_video_map disk path)."""
    d = tmp_path / "data" / job
    d.mkdir(parents=True, exist_ok=True)
    (d / "video_map.json").write_text(json.dumps(data), encoding="utf-8")


def test_get_video_map_done_returns_compact_summary(monkeypatch, tmp_path):
    job = _setup(monkeypatch, tmp_path)
    vm_data = {
        "status": "done",
        "error": None,
        "narrative": "A long interview about AI covering many topics.",
        "chapters": [
            {
                "start": 0.0,
                "end": 60.0,
                "title": "Introduction",
                "summary": "Host introduces the guest.",
                "clip_ids": ["clip_01"],
                "moments": [
                    {
                        "start": 5.0,
                        "end": 10.0,
                        "label": "opening joke",
                        "why": "funny",
                        "kind": "funny",
                    }
                ],
            },
            {
                "start": 60.0,
                "end": 120.0,
                "title": "Main topic",
                "summary": "Deep dive into AI.",
                "clip_ids": [],
                "moments": [],
            },
        ],
    }
    _write_video_map(tmp_path, job, vm_data)

    r = apply_tool("get_video_map", {}, job_id=job, clip_id="clip_01")
    assert r["ok"] is True
    assert r["status"] == "done"
    assert "Introduction" in str(r["chapters"])
    assert "Main topic" in str(r["chapters"])
    # narrative present
    assert "AI" in r["narrative"]
    # chapters are a list of dicts with expected keys
    ch0 = r["chapters"][0]
    assert "range" in ch0
    assert ch0["title"] == "Introduction"
    assert "opening joke" in ch0["moment_labels"]
    assert ch0["clip_ids"] == ["clip_01"]


def test_get_video_map_missing_returns_not_available(monkeypatch, tmp_path):
    job = _setup(monkeypatch, tmp_path)
    # No video_map.json written — should report not_available
    r = apply_tool("get_video_map", {}, job_id=job, clip_id="clip_01")
    assert r["ok"] is False
    assert r["status"] == "not_available"
    assert "note" in r


def test_get_video_map_pending_returns_pending(monkeypatch, tmp_path):
    job = _setup(monkeypatch, tmp_path)
    _write_video_map(
        tmp_path, job, {"status": "pending", "error": None, "narrative": "", "chapters": []}
    )
    r = apply_tool("get_video_map", {}, job_id=job, clip_id="clip_01")
    assert r["ok"] is False
    assert r["status"] == "pending"


def test_get_video_map_failed_returns_error(monkeypatch, tmp_path):
    job = _setup(monkeypatch, tmp_path)
    _write_video_map(
        tmp_path,
        job,
        {"status": "failed", "error": "Gemini timeout", "narrative": "", "chapters": []},
    )
    r = apply_tool("get_video_map", {}, job_id=job, clip_id="clip_01")
    assert r["ok"] is False
    assert r["status"] == "failed"
    assert "Gemini timeout" in r["error"]


def test_get_video_map_narrative_truncated(monkeypatch, tmp_path):
    job = _setup(monkeypatch, tmp_path)
    long_narrative = "x" * 1000
    _write_video_map(
        tmp_path,
        job,
        {
            "status": "done",
            "error": None,
            "narrative": long_narrative,
            "chapters": [],
        },
    )
    r = apply_tool("get_video_map", {}, job_id=job, clip_id="clip_01")
    assert r["ok"] is True
    assert len(r["narrative"]) <= 601  # 600 chars + ellipsis
