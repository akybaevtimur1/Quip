"""VideoMap helpers: parser (D1.2), moment→interval snap (D1.3), Gemini generation (D1.4).

Pure helpers (parse_video_map, moment_to_interval) never raise — broken input → failed status.
Gemini I/O (generate_video_map) mirrors generate_chapters in app/editor/chapters.py exactly.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.editor.ops import clamp_interval
from app.errors import JobError
from app.models import Segment, VideoChapter, VideoMap, VideoMoment, Word
from app.pipeline.stage2_select import (
    build_indexed_transcript,
    call_gemini_structured,
    indices_to_times,
    snap_end_index,
    snap_start_index,
)

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


# ─────────────────────── Gemini generation (D1.4) ────────────────────────


_STAGE = "video_map"
_PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "video_map.v1.txt"

_DEFAULT_SYSTEM_PROMPT = """\
You are an expert video analyst. Analyze the whole video from its word-indexed transcript
and produce a VideoMap: a connected narrative overview, chapters covering the entire video,
and key moments (kind ∈ {tension, quote, emotional, insight, funny}) inside chapters.
Use word indices from the numbered transcript for all boundaries. Output language = video language.
Never invent facts not in the transcript.
"""


def _load_video_map_prompt() -> str:
    """System prompt from prompts/video_map.v1.txt; inline fallback if file missing."""
    if _PROMPT_PATH.exists():
        return _PROMPT_PATH.read_text(encoding="utf-8")
    return _DEFAULT_SYSTEM_PROMPT


# ── private response schema (word indices, converted to seconds below) ──


class _LlmMoment(BaseModel):
    start_word_index: int
    end_word_index: int
    label: str
    why: str
    kind: str


class _LlmChapter(BaseModel):
    start_word_index: int
    end_word_index: int
    title: str
    summary: str
    moments: list[_LlmMoment] = []


class _LlmVideoMap(BaseModel):
    narrative: str
    chapters: list[_LlmChapter]


def generate_video_map(
    words: list[Word],
    duration: float,
    language: str,
    segments: list[Segment],
    *,
    usage_sink: dict[str, int] | None = None,
) -> VideoMap:
    """Gemini → VideoMap via word indices → seconds → parse_video_map.

    Mirrors generate_chapters (app/editor/chapters.py) exactly.
    Raises JobError on permanent Gemini failure (caller → status=failed).
    Garbage/empty model output → parse_video_map returns status="failed" (never raises).
    """
    indexed = build_indexed_transcript(words)

    # Build clip list so the model can reference [[clip:clip_NN]] in the narrative.
    clip_lines: list[str] = []
    for i, seg in enumerate(segments):
        clip_id = f"clip_{i + 1:02d}"
        start_mm, start_ss = divmod(int(seg.start), 60)
        end_mm, end_ss = divmod(int(seg.end), 60)
        clip_lines.append(
            f"  {clip_id}: [{start_mm:02d}:{start_ss:02d}–{end_mm:02d}:{end_ss:02d}]"
            f"  type={seg.type}"
        )
    clips_block = "\n".join(clip_lines) if clip_lines else "  (no clips selected)"

    user_prompt = (
        f"Language: {language}  Duration: {duration:.0f}s  Words: {len(words)}\n\n"
        f"Selected clips (reference as [[clip:clip_NN]] in narrative):\n{clips_block}\n\n"
        f"Word-indexed transcript (each line starts with the index of its first word):\n"
        f"{indexed}\n\n"
        f"Produce a VideoMap covering the ENTIRE video."
    )

    text = call_gemini_structured(
        user_prompt,
        system_prompt=_load_video_map_prompt(),
        response_schema=_LlmVideoMap,
        stage=_STAGE,
        usage_sink=usage_sink,
    )

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        raise JobError(_STAGE, f"Gemini вернул не-JSON: {e}") from e

    raw_chapters = parsed.get("chapters", [])
    narrative = str(parsed.get("narrative", "")).strip()

    n = len(words)
    chapters_out: list[dict[str, Any]] = []
    for ch_item in raw_chapters:
        try:
            si = max(0, min(int(ch_item["start_word_index"]), n - 1))
            ei = max(0, min(int(ch_item["end_word_index"]), n - 1))
            ch_start = words[si].start
            ch_end = words[ei].end
            if ch_end <= ch_start:
                continue  # degenerate chapter after index clamping — skip
        except (KeyError, TypeError, ValueError, IndexError):
            continue

        moments_out: list[dict[str, Any]] = []
        for m_item in ch_item.get("moments") or []:
            try:
                msi = max(0, min(int(m_item["start_word_index"]), n - 1))
                mei = max(0, min(int(m_item["end_word_index"]), n - 1))
                m_start = words[msi].start
                m_end = words[mei].end
                if m_end <= m_start:
                    continue  # degenerate moment — skip
                moments_out.append(
                    {
                        "start": m_start,
                        "end": m_end,
                        "label": str(m_item.get("label", "")).strip(),
                        "why": str(m_item.get("why", "")).strip(),
                        "kind": str(m_item.get("kind", "")).strip(),
                    }
                )
            except (KeyError, TypeError, ValueError, IndexError):
                continue  # broken moment — skip, don't drop whole chapter

        chapters_out.append(
            {
                "start": ch_start,
                "end": ch_end,
                "title": str(ch_item.get("title", "")).strip(),
                "summary": str(ch_item.get("summary", "")).strip(),
                "moments": moments_out,
            }
        )

    raw: dict[str, Any] = {"narrative": narrative, "chapters": chapters_out}
    return parse_video_map(raw, segments, duration)


# ─────────────────────── dual-mode storage (cross-container) ────────────────────────
# КРИТИЧНО: video_map генерится в ОТДЕЛЬНОМ Modal-контейнере (dispatch.spawn), а отдаётся
# web-контейнером (/video-map). Диск-only кэш (как chapters.json) на облаке НЕВИДИМ — разные
# контейнеры. Поэтому пишем И на диск (local dev / тот же контейнер), И в Postgres job_artifacts
# (cloud_key="video_map") — любой контейнер прочитает. Зеркало transcript/segments/meta.

_VIDEO_MAP_FILE = "video_map.json"
_VIDEO_MAP_KEY = "video_map"


def load_video_map(job_id: str) -> VideoMap | None:
    """Прочитать VideoMap: диск data/<job>/video_map.json, иначе Postgres job_artifacts.video_map.

    None — если карты нет нигде (генерация ещё не стартовала). disk-first, cloud-fallback —
    как artifacts._disk_or_cloud, но без JobError: отсутствие = None (endpoint решает дальше).
    """
    from app import artifacts, db

    p = artifacts.job_dir(job_id) / _VIDEO_MAP_FILE
    if p.exists():
        return VideoMap.model_validate_json(p.read_text(encoding="utf-8"))
    val = db.get_job_artifact(job_id, _VIDEO_MAP_KEY)
    if val is None:
        return None
    return VideoMap.model_validate(val)


def save_video_map(job_id: str, data: VideoMap) -> None:
    """Записать VideoMap НА ДИСК и в Postgres (durable между контейнерами).

    Диск — для local dev / того же контейнера; Postgres (db.put_job_artifact, локально no-op) —
    чтобы web-контейнер /video-map увидел результат, сгенерённый отдельным Modal-контейнером.
    """
    from app import artifacts, db

    out = artifacts.job_dir(job_id)
    out.mkdir(parents=True, exist_ok=True)
    (out / _VIDEO_MAP_FILE).write_text(
        data.model_dump_json(indent=2), encoding="utf-8", newline="\n"
    )
    db.put_job_artifact(job_id, _VIDEO_MAP_KEY, data.model_dump())
