"""PURE helpers: VideoMap parser (D1.2) + moment_to_interval snap helper (D1.3).

No I/O, no Gemini calls (those live in D1.4). All defensive: broken input → failed status,
never raises. Mirror style of postprocess_chapters in app/editor/chapters.py.
"""

from __future__ import annotations

import math
from typing import Any

from app.editor.ops import clamp_interval
from app.models import Segment, VideoChapter, VideoMap, VideoMoment, Word
from app.pipeline.stage2_select import indices_to_times, snap_end_index, snap_start_index

# Valid moment kinds (spec §2/§6). Unknown kind → fallback "insight" (moment kept).
_VALID_KINDS = {"tension", "quote", "emotional", "insight", "funny"}
_DEFAULT_KIND = "insight"


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(v, hi))


def _finite(v: object) -> bool:
    """Return True iff v is a real finite number (int or float, not nan/inf)."""
    try:
        return math.isfinite(float(v))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False


def _parse_moment(raw: object, source_dur: float) -> VideoMoment | None:
    """Parse one moment dict, clamping times to [0, source_dur].

    Returns None if the moment is irrecoverably malformed (missing fields, end<=start after clamp).
    Unknown kind is coerced to _DEFAULT_KIND — moment is kept.
    """
    if not isinstance(raw, dict):
        return None

    try:
        start_raw = raw["start"]
        end_raw = raw["end"]
        label = str(raw.get("label", "")).strip()
        why = str(raw.get("why", "")).strip()
        kind = str(raw.get("kind", "")).strip()
    except (KeyError, TypeError):
        return None

    if not (_finite(start_raw) and _finite(end_raw)):
        return None

    start = _clamp(float(start_raw), 0.0, source_dur)
    end = _clamp(float(end_raw), 0.0, source_dur)

    if end <= start:
        return None

    # Coerce unknown kind instead of dropping
    if kind not in _VALID_KINDS:
        kind = _DEFAULT_KIND

    return VideoMoment(start=start, end=end, label=label, why=why, kind=kind)


def _overlaps(ch_start: float, ch_end: float, seg_start: float, seg_end: float) -> bool:
    """True iff (ch_start, ch_end) and (seg_start, seg_end) share interior (open intervals)."""
    return ch_start < seg_end and seg_start < ch_end


def _clip_ids_for_chapter(ch_start: float, ch_end: float, segments: list[Segment]) -> list[str]:
    """Return clip ids (1-based, 'clip_NN') for segments that overlap the chapter interval."""
    ids: list[str] = []
    for i, seg in enumerate(segments):
        if _overlaps(ch_start, ch_end, seg.start, seg.end):
            ids.append(f"clip_{i + 1:02d}")
    return ids


def _parse_chapter(raw: object, segments: list[Segment], source_dur: float) -> VideoChapter | None:
    """Parse one chapter dict. Returns None if irrecoverably malformed."""
    if not isinstance(raw, dict):
        return None

    try:
        start_raw = raw["start"]
        end_raw = raw["end"]
        title = str(raw["title"]).strip()
        summary = str(raw["summary"]).strip()
    except (KeyError, TypeError):
        return None

    if not (_finite(start_raw) and _finite(end_raw)):
        return None

    start = _clamp(float(start_raw), 0.0, source_dur)
    end = _clamp(float(end_raw), 0.0, source_dur)

    # Degenerate chapter after clamping — drop
    if end <= start:
        return None

    moments: list[VideoMoment] = []
    raw_moments = raw.get("moments") or []
    if isinstance(raw_moments, list):
        for m_raw in raw_moments:
            m = _parse_moment(m_raw, source_dur)
            if m is not None:
                moments.append(m)

    clip_ids = _clip_ids_for_chapter(start, end, segments)

    return VideoChapter(
        start=start,
        end=end,
        title=title,
        summary=summary,
        clip_ids=clip_ids,
        moments=moments,
    )


def parse_video_map(
    raw: dict[str, Any],
    segments: list[Segment],
    source_dur: float,
) -> VideoMap:
    """Parse a raw Gemini response dict into a validated VideoMap.

    PURE — no I/O, no network. All errors surface as VideoMap(status="failed", error=...).
    Never raises (rule #8).

    Args:
        raw: The raw dict from Gemini (narrative + chapters).
        segments: Ordered list of selected Segments; clip id is f"clip_{i+1:02d}" (1-based).
        source_dur: Total video duration in seconds; all times clamped to [0, source_dur].

    Returns:
        VideoMap with status="done" on success, status="failed" with non-empty error otherwise.
    """
    # Guard: raw must be a dict
    if not isinstance(raw, dict):
        return VideoMap(status="failed", error="raw response is not a dict")

    # narrative: best-effort string
    narrative_raw = raw.get("narrative", "")
    narrative = str(narrative_raw).strip() if narrative_raw is not None else ""

    # chapters list must exist and be a list
    chapters_raw = raw.get("chapters")
    if chapters_raw is None:
        return VideoMap(
            status="failed",
            error="raw response missing 'chapters' key",
        )
    if not isinstance(chapters_raw, list):
        return VideoMap(
            status="failed",
            error=f"'chapters' must be a list, got {type(chapters_raw).__name__}",
        )

    chapters: list[VideoChapter] = []
    for ch_raw in chapters_raw:
        ch = _parse_chapter(ch_raw, segments, source_dur)
        if ch is not None:
            chapters.append(ch)

    # Sort chapters by start time (defensive; LLM might not order them)
    chapters.sort(key=lambda c: c.start)

    return VideoMap(status="done", narrative=narrative, chapters=chapters, error=None)


# ─────────────────────── moment → snapped interval (D1.3) ────────────────────────


def _nearest_word_index(words: list[Word], t: float) -> int:
    """Map a source time t (seconds) to the index of the nearest word.

    Priority order:
      1. Any word whose [start, end] contains t (containment).
      2. The word whose midpoint is closest to t (fallback when t falls in a gap).
    """
    # containment pass
    for i, w in enumerate(words):
        if w.start <= t <= w.end:
            return i
    # closest midpoint
    return min(range(len(words)), key=lambda i: abs((words[i].start + words[i].end) / 2.0 - t))


def moment_to_interval(
    start: float,
    end: float,
    words: list[Word],
    *,
    source_dur: float,
    min_sec: float = 20.0,
) -> tuple[float, float]:
    """Snap a [start, end] moment to word boundaries and expand to ≥ min_sec.

    Steps:
      1. Map input seconds to nearest word indices via midpoint proximity.
      2. Snap indices to clean sentence boundaries (snap_start_index / snap_end_index).
      3. Convert snapped indices back to source seconds (indices_to_times).
      4. Clamp / expand to [min_sec, source_dur] using clamp_interval.

    Args:
        start:      Moment start in source seconds.
        end:        Moment end in source seconds.
        words:      Word-level transcript (Word.start / Word.end in source seconds).
        source_dur: Total source duration in seconds; clamp ceiling.
        min_sec:    Minimum interval length (default 20.0s).

    Returns:
        (source_start, source_end) in source seconds, snapped and ≥ min_sec.
    """
    if not words:
        # Degenerate: no words — fall back to raw clamp only.
        return clamp_interval(start, end, duration=source_dur, min_sec=min_sec, max_sec=source_dur)

    start_idx = _nearest_word_index(words, start)
    end_idx = _nearest_word_index(words, end)

    # Ensure indices are ordered (snap may not guarantee this for very short moments)
    if start_idx > end_idx:
        start_idx, end_idx = end_idx, start_idx

    snapped_start_idx = snap_start_index(words, start_idx)
    snapped_end_idx = snap_end_index(words, end_idx)

    # After snapping, start may have moved forward past end — re-order defensively.
    if snapped_start_idx > snapped_end_idx:
        snapped_start_idx, snapped_end_idx = snapped_end_idx, snapped_start_idx

    s, e = indices_to_times(words, snapped_start_idx, snapped_end_idx)

    return clamp_interval(s, e, duration=source_dur, min_sec=min_sec, max_sec=source_dur)
