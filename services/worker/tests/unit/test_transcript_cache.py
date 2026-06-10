"""Tests for transcript_cache pure functions and eviction I/O."""

from __future__ import annotations

import os
import time
from pathlib import Path

from app.transcript_cache import cache_key, get_cached, put_cached, select_evictions

# ─── cache_key (PURE) ───────────────────────────────────────────────────────


def test_cache_key_is_deterministic() -> None:
    assert cache_key("abc123", "deepgram", "nova-3") == cache_key("abc123", "deepgram", "nova-3")


def test_cache_key_differs_by_sha() -> None:
    assert cache_key("aaa", "deepgram", "nova-3") != cache_key("bbb", "deepgram", "nova-3")


def test_cache_key_differs_by_provider() -> None:
    assert cache_key("abc", "deepgram", "nova-3") != cache_key("abc", "assemblyai", "best")


def test_cache_key_differs_by_model() -> None:
    assert cache_key("abc", "deepgram", "nova-3") != cache_key("abc", "deepgram", "nova-2")


def test_cache_key_is_filesystem_safe() -> None:
    key = cache_key("abc123", "deepgram", "nova-3")
    assert all(c not in key for c in r"/\: ")
    assert len(key) > 0


# ─── select_evictions (PURE) ────────────────────────────────────────────────


def test_select_evictions_empty() -> None:
    assert select_evictions([], time.time(), max_entries=10, max_age_sec=3600) == []


def test_select_evictions_within_cap_not_expired() -> None:
    now = time.time()
    entries = [("a.json", now - 100), ("b.json", now - 200)]
    result = select_evictions(entries, now, max_entries=5, max_age_sec=3600)
    assert result == []


def test_select_evictions_expired_removed() -> None:
    now = time.time()
    entries = [
        ("old.json", now - 7200),  # 2h old — expired at 1h TTL
        ("new.json", now - 100),
    ]
    result = select_evictions(entries, now, max_entries=10, max_age_sec=3600)
    assert result == ["old.json"]


def test_select_evictions_over_cap_removes_oldest() -> None:
    now = time.time()
    entries = [
        ("a.json", now - 300),
        ("b.json", now - 200),
        ("c.json", now - 100),
    ]
    # cap=2, none expired → oldest (a.json) evicted
    result = select_evictions(entries, now, max_entries=2, max_age_sec=9999)
    assert result == ["a.json"]


def test_select_evictions_expired_then_cap() -> None:
    now = time.time()
    entries = [
        ("old.json", now - 7200),  # expired
        ("a.json", now - 300),
        ("b.json", now - 200),
        ("c.json", now - 100),
    ]
    # TTL=1h → old.json expired; remaining 3 > cap=2 → a.json (oldest) also evicted
    result = select_evictions(entries, now, max_entries=2, max_age_sec=3600)
    assert "old.json" in result
    assert "a.json" in result
    assert "b.json" not in result
    assert "c.json" not in result


# ─── I/O wrappers (use pytest tmp_path — no real disk state) ────────────────


def _make_transcript() -> object:
    from app.models import Transcript, Word

    return Transcript(
        language="en",
        duration=10.0,
        words=[Word(text="Hello", start=0.1, end=0.5, confidence=0.99)],
    )


def test_get_cached_miss(tmp_path: Path) -> None:
    assert get_cached(tmp_path, "nonexistent") is None


def test_put_and_get_cached_roundtrip(tmp_path: Path) -> None:
    t = _make_transcript()
    put_cached(tmp_path, "testkey", t)  # type: ignore[arg-type]
    result = get_cached(tmp_path, "testkey")
    assert result is not None
    assert result.language == "en"
    assert len(result.words) == 1
    assert result.words[0].text == "Hello"


def test_get_cached_corrupt_entry_returns_none(tmp_path: Path) -> None:
    (tmp_path / "badkey.json").write_text("not valid json {{", encoding="utf-8")
    assert get_cached(tmp_path, "badkey") is None


def test_evict_removes_expired(tmp_path: Path) -> None:
    from app.transcript_cache import evict

    t = _make_transcript()
    put_cached(tmp_path, "key1", t)  # type: ignore[arg-type]
    f = tmp_path / "key1.json"
    old_time = time.time() - 2 * 86400
    os.utime(f, (old_time, old_time))
    evict(tmp_path, max_entries=100, max_age_days=1)
    assert not f.exists()


def test_evict_respects_cap(tmp_path: Path) -> None:
    from app.transcript_cache import evict

    t = _make_transcript()
    for i in range(5):
        put_cached(tmp_path, f"key{i}", t)  # type: ignore[arg-type]
        time.sleep(0.01)
    evict(tmp_path, max_entries=3, max_age_days=999)
    remaining = list(tmp_path.glob("*.json"))
    assert len(remaining) == 3


def test_evict_noop_if_dir_missing(tmp_path: Path) -> None:
    from app.transcript_cache import evict

    evict(tmp_path / "nonexistent", max_entries=10, max_age_days=30)  # must not raise
