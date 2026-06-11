# Transcript Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Content-addressed cache for Deepgram transcriptions so repeated runs of the same video across different job_ids cost $0 for transcription.

**Architecture:** New pure module `app/transcript_cache.py` (cache_key + select_evictions PURE; audio_sha/get_cached/put_cached/evict thin I/O wrappers). Two new Settings fields (max_entries, max_age_days). Wire into `run.py` Stage 1 block — upstream/downstream untouched.

**Tech Stack:** Python stdlib (`hashlib`, `shutil`, `pathlib`), Pydantic (already in use), pytest (existing test suite).

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| **Create** | `services/worker/app/transcript_cache.py` | All cache logic (pure + thin I/O) |
| **Create** | `services/worker/tests/unit/test_transcript_cache.py` | Unit tests for all PURE functions + evict I/O |
| **Modify** | `services/worker/app/config.py` | Add `transcript_cache_enabled`, `transcript_cache_max_entries`, `transcript_cache_max_age_days` |
| **Modify** | `services/worker/app/run.py` | Wire cache into Stage 1 block (lines ~90–102) |
| **Modify** | `services/worker/.env.example` | Document new env vars |

---

## Task 1: PURE functions + failing tests

**Files:**
- Create: `services/worker/tests/unit/test_transcript_cache.py`
- Create: `services/worker/app/transcript_cache.py` (stub)

- [ ] **Step 1.1: Write failing tests for `cache_key`**

Create `services/worker/tests/unit/test_transcript_cache.py`:

```python
"""Tests for transcript_cache pure functions and eviction I/O."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from app.transcript_cache import cache_key, select_evictions


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
    # no slashes, colons, spaces — safe as filename
    assert all(c not in key for c in r"/\: ")
    assert len(key) > 0
```

- [ ] **Step 1.2: Run tests — verify they FAIL**

```powershell
$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
Set-Location "C:\Users\user\Desktop\ClipClow\services\worker"
uv run pytest tests/unit/test_transcript_cache.py -v 2>&1 | Select-Object -First 20
```

Expected: `ModuleNotFoundError` or `ImportError` (module doesn't exist yet).

- [ ] **Step 1.3: Create stub module with `cache_key` implementation**

Create `services/worker/app/transcript_cache.py`:

```python
"""Content-addressed cache for transcription results.

Avoids paying Deepgram again for audio already transcribed.
Key = sha256(wav_bytes) + provider + model → identical audio = same key regardless of job_id.

Pure functions (cache_key, select_evictions) are unit-tested without disk I/O.
Thin I/O wrappers (audio_sha, get_cached, put_cached, evict) are used by run.py Stage 1.
"""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from typing import Any

from app.models import Transcript


def cache_key(audio_sha: str, provider: str, model: str) -> str:
    """PURE. Stable cache key from audio hash + provider + model.

    Including provider+model ensures a model change produces a new key,
    preventing stale transcripts from being returned.

    Returns a hex string safe for use as a filename.
    """
    raw = f"{audio_sha}|{provider}|{model}"
    return hashlib.sha256(raw.encode()).hexdigest()


def select_evictions(
    entries: list[tuple[str, float]],
    now: float,
    *,
    max_entries: int,
    max_age_sec: float,
) -> list[str]:
    """PURE. Given [(name, mtime), ...] return names to delete.

    Eviction policy (applied in order):
    1. All entries older than max_age_sec (TTL expiry).
    2. If count still > max_entries, delete oldest-by-mtime until within cap.

    entries: list of (filename, mtime) — order not assumed.
    now: current timestamp (seconds since epoch).
    Returns list of filenames to remove (may be empty).
    """
    expired = {name for name, mtime in entries if (now - mtime) > max_age_sec}
    remaining = [(name, mtime) for name, mtime in entries if name not in expired]
    overflow: list[str] = []
    if len(remaining) > max_entries:
        # sort oldest first, evict until within cap
        remaining.sort(key=lambda x: x[1])
        n_to_evict = len(remaining) - max_entries
        overflow = [name for name, _ in remaining[:n_to_evict]]
    return sorted(expired) + overflow  # sorted for deterministic test assertions


def audio_sha(wav: Path) -> str:
    """SHA-256 hex digest of wav file bytes (thin I/O wrapper)."""
    return hashlib.sha256(wav.read_bytes()).hexdigest()


def get_cached(cache_dir: Path, key: str) -> Transcript | None:
    """Load and validate transcript from cache. Returns None on miss or corrupt entry."""
    path = cache_dir / f"{key}.json"
    if not path.exists():
        return None
    try:
        return Transcript.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — corrupt cache entry = miss, not a crash
        return None


def put_cached(cache_dir: Path, key: str, transcript: Transcript) -> None:
    """Write transcript to cache directory (creates dir if needed)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{key}.json").write_text(
        transcript.model_dump_json(indent=2), encoding="utf-8"
    )


def evict(cache_dir: Path, *, max_entries: int, max_age_days: float) -> None:
    """Remove expired and over-cap entries from cache_dir.

    Reads mtime from filesystem, calls select_evictions (PURE), then deletes.
    No-op if cache_dir doesn't exist.
    """
    if not cache_dir.exists():
        return
    entries: list[tuple[str, float]] = [
        (p.name, p.stat().st_mtime)
        for p in cache_dir.glob("*.json")
    ]
    to_delete = select_evictions(
        entries,
        time.time(),
        max_entries=max_entries,
        max_age_sec=max_age_days * 86400,
    )
    for name in to_delete:
        (cache_dir / name).unlink(missing_ok=True)
```

- [ ] **Step 1.4: Run `cache_key` tests — verify PASS**

```powershell
$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
Set-Location "C:\Users\user\Desktop\ClipClow\services\worker"
uv run pytest tests/unit/test_transcript_cache.py::test_cache_key_is_deterministic tests/unit/test_transcript_cache.py::test_cache_key_differs_by_sha tests/unit/test_transcript_cache.py::test_cache_key_differs_by_provider tests/unit/test_transcript_cache.py::test_cache_key_differs_by_model tests/unit/test_transcript_cache.py::test_cache_key_is_filesystem_safe -v
```

Expected: `5 passed`.

---

## Task 2: `select_evictions` PURE tests

**Files:**
- Modify: `services/worker/tests/unit/test_transcript_cache.py` (add tests)

- [ ] **Step 2.1: Add `select_evictions` tests**

Append to `services/worker/tests/unit/test_transcript_cache.py`:

```python
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
        ("old.json", now - 7200),   # 2h old — expired at 1h TTL
        ("new.json", now - 100),    # fresh
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
    # cap=2, none expired → oldest one (a.json) evicted
    result = select_evictions(entries, now, max_entries=2, max_age_sec=9999)
    assert result == ["a.json"]


def test_select_evictions_expired_then_cap() -> None:
    now = time.time()
    entries = [
        ("old.json", now - 7200),   # expired
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
```

- [ ] **Step 2.2: Run `select_evictions` tests — verify PASS**

```powershell
$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
Set-Location "C:\Users\user\Desktop\ClipClow\services\worker"
uv run pytest tests/unit/test_transcript_cache.py -v
```

Expected: `10 passed`.

---

## Task 3: I/O function tests (`get_cached`, `put_cached`, `evict`)

**Files:**
- Modify: `services/worker/tests/unit/test_transcript_cache.py` (add I/O tests using tmp_path)

- [ ] **Step 3.1: Add I/O tests**

Append to `services/worker/tests/unit/test_transcript_cache.py`:

```python
# ─── I/O wrappers (use pytest tmp_path — no real disk state) ────────────────


def _make_transcript() -> "Transcript":
    from app.models import Transcript, Word
    return Transcript(
        language="en",
        duration=10.0,
        words=[Word(text="Hello", start=0.1, end=0.5, confidence=0.99)],
    )


def test_get_cached_miss(tmp_path: Path) -> None:
    assert get_cached(tmp_path, "nonexistent") is None


def test_put_and_get_cached_roundtrip(tmp_path: Path) -> None:
    from app.transcript_cache import get_cached, put_cached
    t = _make_transcript()
    put_cached(tmp_path, "testkey", t)
    result = get_cached(tmp_path, "testkey")
    assert result is not None
    assert result.language == "en"
    assert len(result.words) == 1
    assert result.words[0].text == "Hello"


def test_get_cached_corrupt_entry_returns_none(tmp_path: Path) -> None:
    from app.transcript_cache import get_cached
    (tmp_path / "badkey.json").write_text("not valid json {{", encoding="utf-8")
    assert get_cached(tmp_path, "badkey") is None


def test_evict_removes_expired(tmp_path: Path) -> None:
    from app.transcript_cache import evict, put_cached
    t = _make_transcript()
    put_cached(tmp_path, "key1", t)
    # backdate mtime to 2 days ago
    f = tmp_path / "key1.json"
    old_time = time.time() - 2 * 86400
    os.utime(f, (old_time, old_time))
    evict(tmp_path, max_entries=100, max_age_days=1)
    assert not f.exists()


def test_evict_respects_cap(tmp_path: Path) -> None:
    from app.transcript_cache import evict, put_cached
    t = _make_transcript()
    for i in range(5):
        put_cached(tmp_path, f"key{i}", t)
        time.sleep(0.01)  # ensure distinct mtimes
    evict(tmp_path, max_entries=3, max_age_days=999)
    remaining = list(tmp_path.glob("*.json"))
    assert len(remaining) == 3


def test_evict_noop_if_dir_missing(tmp_path: Path) -> None:
    from app.transcript_cache import evict
    evict(tmp_path / "nonexistent", max_entries=10, max_age_days=30)  # must not raise
```

Update the imports at the top of the test file to include the I/O functions:

```python
from app.transcript_cache import cache_key, select_evictions, get_cached, put_cached
```

- [ ] **Step 3.2: Run all transcript_cache tests — verify PASS**

```powershell
$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
Set-Location "C:\Users\user\Desktop\ClipClow\services\worker"
uv run pytest tests/unit/test_transcript_cache.py -v
```

Expected: `17 passed`.

---

## Task 4: Add config fields

**Files:**
- Modify: `services/worker/app/config.py`
- Modify: `services/worker/.env.example`

- [ ] **Step 4.1: Add three fields to `Settings` in `config.py`**

After the `max_clips` line (after `max_clips: int = 8`), insert:

```python
    # transcript cache
    transcript_cache_enabled: bool = True
    transcript_cache_max_entries: int = 200  # LRU cap by mtime
    transcript_cache_max_age_days: float = 60.0  # TTL for cache entries
```

- [ ] **Step 4.2: Document in `.env.example`**

In `services/worker/.env.example`, after the `MAX_CLIPS=8` line (or equivalent pipeline section), add:

```bash
# ── TRANSCRIPT CACHE ──
TRANSCRIPT_CACHE_ENABLED=true
TRANSCRIPT_CACHE_MAX_ENTRIES=200   # LRU cap (oldest evicted first)
TRANSCRIPT_CACHE_MAX_AGE_DAYS=60   # TTL in days
```

---

## Task 5: Wire into `run.py` Stage 1

**Files:**
- Modify: `services/worker/app/run.py`

- [ ] **Step 5.1: Add import of cache module**

At the top of `services/worker/app/run.py`, after the existing pipeline imports, add:

```python
from app.transcript_cache import audio_sha, cache_key, evict, get_cached, put_cached
```

- [ ] **Step 5.2: Replace Stage 1 block**

In `run.py`, find the Stage 1 block (lines ~90–102):

```python
    # ── Stage 1: Transcribe (кэш по transcript.json) ──
    emit(JobStatus.transcribing, 35)
    t0 = time.perf_counter()
    tr_path = out / "transcript.json"
    transcribe_cost = 0.0
    if tr_path.exists():
        transcript = Transcript.model_validate_json(tr_path.read_text(encoding="utf-8"))
        print(f"[1] transcribe: cached ({len(transcript.words)} words)")
    else:
        transcript = transcribe_to_file(out / "source.wav", tr_path)
        transcribe_cost = round(transcript.duration / 60 * DEEPGRAM_NOVA_USD_PER_MIN, 4)
        print(f"[1] transcribe: {len(transcript.words)} words (${transcribe_cost})")
    stages["transcription"] = round(time.perf_counter() - t0, 2)
```

Replace it entirely with:

```python
    # ── Stage 1: Transcribe (уровень 1: transcript.json; уровень 2: content-hash кэш) ──
    emit(JobStatus.transcribing, 35)
    t0 = time.perf_counter()
    tr_path = out / "transcript.json"
    transcribe_cost = 0.0
    cache_dir = DATA_ROOT / "_cache" / "transcripts"

    if tr_path.exists():
        # Level 1: job-local cache (same job_id re-run)
        transcript = Transcript.model_validate_json(tr_path.read_text(encoding="utf-8"))
        print(f"[1] transcribe: cached/local ({len(transcript.words)} words)")
    else:
        wav_path = out / "source.wav"
        # Level 2: content-addressed cache (same audio, different job_id)
        cached_tr: Transcript | None = None
        ck: str | None = None
        if s.transcript_cache_enabled:
            sha = audio_sha(wav_path)
            ck = cache_key(sha, s.transcription_provider, s.deepgram_model)
            cached_tr = get_cached(cache_dir, ck)

        if cached_tr is not None:
            transcript = cached_tr
            tr_path.write_text(transcript.model_dump_json(indent=2), encoding="utf-8")
            print(f"[1] transcribe: cached/hash ({len(transcript.words)} words, $0)")
        else:
            transcript = transcribe_to_file(wav_path, tr_path)
            transcribe_cost = round(transcript.duration / 60 * DEEPGRAM_NOVA_USD_PER_MIN, 4)
            print(f"[1] transcribe: {len(transcript.words)} words (${transcribe_cost})")
            if s.transcript_cache_enabled and ck is not None:
                put_cached(cache_dir, ck, transcript)
                evict(
                    cache_dir,
                    max_entries=s.transcript_cache_max_entries,
                    max_age_days=s.transcript_cache_max_age_days,
                )
    stages["transcription"] = round(time.perf_counter() - t0, 2)
```

---

## Task 6: `just check` + commit

**Files:** none new — validation only.

- [ ] **Step 6.1: Run full test suite**

```powershell
$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
Set-Location "C:\Users\user\Desktop\ClipClow"
just check
```

Expected: all green (lint + mypy + tsc + test-unit + anti-drift). Fix any mypy errors before proceeding.

- [ ] **Step 6.2: Commit**

Write commit message to `services/worker/tmp/COMMIT_MSG.txt` (UTF-8, no BOM):

```
feat(cache): content-addressed transcript cache (cap+TTL)

New module app/transcript_cache.py: cache_key+select_evictions (PURE,
unit-tested) + audio_sha/get_cached/put_cached/evict (thin I/O).
data/_cache/transcripts/<sha256>.json — повторный UI-джоб того же
видео не платит Deepgram ($0 на стадию 1).

Eviction: TTL=60d + LRU cap=200 записей (configurable).
+17 unit-тестов. just check green.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

```powershell
$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
Set-Location "C:\Users\user\Desktop\ClipClow"
git add services/worker/app/transcript_cache.py
git add services/worker/tests/unit/test_transcript_cache.py
git add services/worker/app/config.py
git add services/worker/app/run.py
git add services/worker/.env.example
git commit -F "services/worker/tmp/COMMIT_MSG.txt"
```

---

## Task 7: DoD verification

- [ ] **Step 7.1: Run video under `job_A`**

```powershell
$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
Set-Location "C:\Users\user\Desktop\ClipClow\services\worker"
# First, remove any existing transcript for comedy01 to force a fresh run:
Remove-Item -Force "data\comedy01\transcript.json" -ErrorAction SilentlyContinue
uv run python -m app.run comedy01
```

Expected: `[1] transcribe: NNNN words ($0.14)` (pays Deepgram, writes to cache).

- [ ] **Step 7.2: Run same video under new `job_B` — verify $0**

```powershell
$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
Set-Location "C:\Users\user\Desktop\ClipClow\services\worker"
# Copy source files to a new job dir (simulates a new UI job for the same video)
New-Item -ItemType Directory -Force "data\job_dod_cache" | Out-Null
Copy-Item "data\comedy01\source.mp4" "data\job_dod_cache\source.mp4"
Copy-Item "data\comedy01\source.wav" "data\job_dod_cache\source.wav"
Copy-Item "data\comedy01\meta.json" "data\job_dod_cache\meta.json"
Copy-Item "data\comedy01\segments.json" "data\job_dod_cache\segments.json"
uv run python -m app.run job_dod_cache
```

Expected: `[1] transcribe: cached/hash (NNNN words, $0)`.

- [ ] **Step 7.3: Verify cache file exists**

```powershell
$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
Set-Location "C:\Users\user\Desktop\ClipClow\services\worker"
Get-ChildItem "data\_cache\transcripts\" | Select-Object Name, Length
```

Expected: one `.json` file present, size > 0.

- [ ] **Step 7.4: Verify `runs.jsonl` shows $0 transcription for job_B**

```powershell
Get-Content "C:\Users\user\Desktop\ClipClow\services\worker\data\runs.jsonl" | Select-Object -Last 2
```

Expected: last entry has `"transcription"` stage cost = 0 in total_usd.
