"""Content-addressed cache for transcription results.

Avoids paying Deepgram again for audio already transcribed under any job_id.
Key = sha256(wav_bytes) + provider + model → identical audio = same key.

Pure functions (cache_key, select_evictions) are unit-tested without disk I/O.
Thin I/O wrappers (audio_sha, get_cached, put_cached, evict) are used by run.py Stage 1.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

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

    Returns list of filenames sorted for deterministic test assertions.
    """
    expired = {name for name, mtime in entries if (now - mtime) > max_age_sec}
    remaining = [(name, mtime) for name, mtime in entries if name not in expired]
    overflow: list[str] = []
    if len(remaining) > max_entries:
        remaining.sort(key=lambda x: x[1])
        n_to_evict = len(remaining) - max_entries
        overflow = [name for name, _ in remaining[:n_to_evict]]
    return sorted(expired) + overflow


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
    (cache_dir / f"{key}.json").write_text(transcript.model_dump_json(indent=2), encoding="utf-8")


def evict(cache_dir: Path, *, max_entries: int, max_age_days: float) -> None:
    """Remove expired and over-cap entries from cache_dir.

    Reads mtime from filesystem, calls select_evictions (PURE), then deletes.
    No-op if cache_dir doesn't exist.
    """
    if not cache_dir.exists():
        return
    entries: list[tuple[str, float]] = [
        (p.name, p.stat().st_mtime) for p in cache_dir.glob("*.json")
    ]
    to_delete = select_evictions(
        entries,
        time.time(),
        max_entries=max_entries,
        max_age_sec=max_age_days * 86400,
    )
    for name in to_delete:
        (cache_dir / name).unlink(missing_ok=True)
