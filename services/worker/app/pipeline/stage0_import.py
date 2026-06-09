"""Stage 0 (Import): source → source.mp4, source.wav (16k mono), meta.json.

Вход: YouTube URL ИЛИ локальный файл (upload). Выход в ``data/<job_id>/``:
- ``source.mp4``         — видео (≤1080p),
- ``source.wav``         — 16000 Hz, mono, pcm_s16le (для транскрипции),
- ``meta.json``          — SourceMeta.

Границы: pure-логика (``parse_fps``, ``build_source_meta``) изолирована и покрыта
unit-тестами. I/O (yt-dlp/ffmpeg/ffprobe) — тонкие обёртки; при любом сбое кидают
``JobError`` (правило №8: без тихих фолбэков).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.errors import JobError
from app.models import SourceKind

_STAGE = "import"
MAX_SOURCE_MINUTES = 90  # лимит плана; вынесем в config.py при появлении настроек


class SourceMeta(BaseModel):
    """Локальный артефакт Stage 0 (НЕ часть wire-контракта) — пишется в meta.json."""

    job_id: str
    source: SourceKind
    url: str | None
    title: str
    duration: float  # секунды
    fps: float
    width: int
    height: int


# ─────────────────────────── pure-логика (unit-тесты) ───────────────────────────


def parse_fps(rate: str) -> float:
    """``'30000/1001'`` → 29.97, ``'25'`` → 25.0.

    JobError при пустой/битой строке или нулевом знаменателе. Округление до 3 знаков
    (даёт 23.976, 29.97 — стандартные NTSC-частоты).
    """
    rate = rate.strip()
    if not rate:
        raise JobError(_STAGE, "пустой r_frame_rate")
    try:
        if "/" in rate:
            num_s, den_s = rate.split("/", 1)
            num, den = float(num_s), float(den_s)
            if den == 0:
                raise JobError(_STAGE, f"нулевой знаменатель fps: {rate!r}")
            fps = num / den
        else:
            fps = float(rate)
    except JobError:
        raise
    except ValueError as e:
        raise JobError(_STAGE, f"не разобрать r_frame_rate {rate!r}: {e}") from e
    return round(fps, 3)


def _video_stream(probe: dict[str, Any]) -> dict[str, Any]:
    streams = probe.get("streams") or []
    if not streams:
        raise JobError(_STAGE, "ffprobe не вернул видеопоток")
    stream: dict[str, Any] = streams[0]
    return stream


def _duration(probe: dict[str, Any], stream: dict[str, Any]) -> float:
    raw: Any = stream.get("duration")
    if raw in (None, "", "N/A"):
        fmt = probe.get("format")
        raw = fmt.get("duration") if isinstance(fmt, dict) else None
    if raw in (None, "", "N/A"):
        raise JobError(_STAGE, "ffprobe не вернул длительность")
    try:
        return float(raw)
    except (TypeError, ValueError) as e:
        raise JobError(_STAGE, f"битая длительность {raw!r}: {e}") from e


def build_source_meta(
    probe: dict[str, Any],
    *,
    job_id: str,
    source: SourceKind,
    url: str | None,
    title: str,
) -> SourceMeta:
    """ffprobe JSON (+контекст) → SourceMeta. JobError при отсутствии потока/длительности."""
    stream = _video_stream(probe)
    try:
        width = int(stream["width"])
        height = int(stream["height"])
    except (KeyError, TypeError, ValueError) as e:
        raise JobError(_STAGE, f"нет width/height в ffprobe: {e}") from e
    fps = parse_fps(str(stream.get("r_frame_rate", "")))
    duration = _duration(probe, stream)
    return SourceMeta(
        job_id=job_id,
        source=source,
        url=url,
        title=title,
        duration=duration,
        fps=fps,
        width=width,
        height=height,
    )


# ─────────────────────────── I/O-обёртки (yt-dlp / ffmpeg / ffprobe) ───────────────────────────


def _run(cmd: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Запустить процесс; JobError при отсутствии бинарника или ненулевом коде."""
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    except FileNotFoundError as e:
        raise JobError(_STAGE, f"не найден бинарник {cmd[0]!r}: {e}") from e
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip()[-500:]
        raise JobError(_STAGE, f"{cmd[0]} код {proc.returncode}: {tail}")
    return proc


def download_youtube(url: str, out_dir: Path, *, cookies_browser: str = "") -> Path:
    """yt-dlp → ``out_dir/source.mp4`` (+ source.info.json). Возвращает путь к mp4."""
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "yt-dlp",
        "-f",
        "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
        "--merge-output-format",
        "mp4",
        "--no-playlist",
        "--max-filesize",
        "2G",
        "--write-info-json",
        "--restrict-filenames",
        "-o",
        str(out_dir / "source.%(ext)s"),
    ]
    if cookies_browser:
        cmd += ["--cookies-from-browser", cookies_browser]
    cmd.append(url)
    _run(cmd)
    mp4 = out_dir / "source.mp4"
    if not mp4.exists():
        raise JobError(_STAGE, f"yt-dlp не создал {mp4}")
    return mp4


def extract_audio(mp4: Path, wav: Path) -> None:
    """ffmpeg: source.mp4 → 16000 Hz mono pcm_s16le WAV (для транскрипции)."""
    _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(mp4),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(wav),
        ]
    )
    if not wav.exists():
        raise JobError(_STAGE, f"ffmpeg не создал {wav}")


def probe_video(mp4: Path) -> dict[str, Any]:
    """ffprobe → dict (streams[0]: width/height/r_frame_rate/duration + format.duration)."""
    proc = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,r_frame_rate,duration:format=duration",
            "-of",
            "json",
            str(mp4),
        ]
    )
    data: dict[str, Any] = json.loads(proc.stdout)
    return data


def _read_title(out_dir: Path, fallback: str) -> str:
    """Заголовок из source.info.json (yt-dlp). При отсутствии — fallback."""
    info = out_dir / "source.info.json"
    if not info.exists():
        return fallback
    data: dict[str, Any] = json.loads(info.read_text(encoding="utf-8"))
    title = data.get("title")
    return title if isinstance(title, str) and title else fallback


def _check_limits(meta: SourceMeta) -> None:
    if meta.duration > MAX_SOURCE_MINUTES * 60:
        raise JobError(
            _STAGE,
            f"источник {meta.duration / 60:.1f} мин > лимита {MAX_SOURCE_MINUTES} мин",
        )


def import_youtube(
    url: str, out_dir: Path, *, job_id: str, cookies_browser: str = ""
) -> SourceMeta:
    """Полный Stage 0 для YouTube: download → audio → probe → meta.json. Возвращает SourceMeta."""
    mp4 = download_youtube(url, out_dir, cookies_browser=cookies_browser)
    extract_audio(mp4, out_dir / "source.wav")
    probe = probe_video(mp4)
    title = _read_title(out_dir, fallback=url)
    meta = build_source_meta(probe, job_id=job_id, source=SourceKind.youtube, url=url, title=title)
    _check_limits(meta)
    (out_dir / "meta.json").write_text(meta.model_dump_json(indent=2), encoding="utf-8")
    return meta
