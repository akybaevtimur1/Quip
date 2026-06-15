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

from app.billing import MAX_VIDEO_MINUTES
from app.errors import JobError
from app.models import SourceKind

_STAGE = "import"
# Технический потолок длины одного исходника (всегда, даже без биллинга). Единый источник —
# billing.MAX_VIDEO_MINUTES. Это НЕ план-лимит: план/баланс по минутам гейтит _quota_gate
# (tasks.py) после probe. Раньше тут стоял плоский 90, не связанный с кредит-моделью.
MAX_SOURCE_MINUTES = MAX_VIDEO_MINUTES


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
    if fps <= 0:
        # 0 fps → ZeroDivisionError в round(start*fps)/fps (stage5_render);
        # отрицательный → битая кадровая математика. Явный отказ вместо тихого брака.
        raise JobError(_STAGE, f"неположительный fps: {rate!r} → {fps}")
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
        dur = float(raw)
    except (TypeError, ValueError) as e:
        raise JobError(_STAGE, f"битая длительность {raw!r}: {e}") from e
    if dur <= 0:
        raise JobError(_STAGE, f"неположительная длительность: {dur}")
    return dur


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
    if width <= 0 or height <= 0:
        raise JobError(_STAGE, f"невалидные размеры кадра: {width}x{height}")
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


def download_youtube(
    url: str, out_dir: Path, *, cookies_browser: str = "", cookies_file: str = ""
) -> Path:
    """yt-dlp → ``out_dir/source.mp4`` (+ source.info.json). Возвращает путь к mp4."""
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "yt-dlp",
        "-f",
        # Предпочитаем H.264 (avc1) — софт-декод AV1 в reframe-анализе в ~2-5× медленнее и
        # засыпает лог hw-accel-ошибками. Фолбэки: mp4(av1) → любой 1080 → best.
        "bestvideo[height<=1080][vcodec^=avc1]+bestaudio[ext=m4a]/bestvideo[height<=1080][ext=mp4]+bestaudio/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "--merge-output-format",
        "mp4",
        "--no-playlist",
        # YouTube nsig/«n»-челлендж теперь требует JS-рантайм (Deno в образе) + EJS-скрипты
        # решателя. ejs:github подтягивает их с GitHub в рантайме (yt-dlp #15012, wiki EJS).
        # Без этого — «n challenge solving failed → Some formats may be missing» (exit 1).
        "--remote-components",
        "ejs:github",
        "--max-filesize",
        "2G",
        "--write-info-json",
        "--restrict-filenames",
        "-o",
        str(out_dir / "source.%(ext)s"),
    ]
    if cookies_file:
        cmd += ["--cookies", cookies_file]
    elif cookies_browser:
        cmd += ["--cookies-from-browser", cookies_browser]
    cmd.append(url)
    _run(cmd)
    mp4 = out_dir / "source.mp4"
    if not mp4.exists():
        raise JobError(_STAGE, f"yt-dlp не создал {mp4}")
    return mp4


def has_audio_stream(mp4: Path) -> bool:
    """ffprobe: есть ли в файле хоть один аудио-поток. Видео без звука → False."""
    proc = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=index",
            "-of",
            "csv=p=0",
            str(mp4),
        ]  # fmt: skip
    )
    return bool(proc.stdout.strip())


def extract_audio(mp4: Path, wav: Path) -> None:
    """ffmpeg: source.mp4 → 16000 Hz mono pcm_s16le WAV (для транскрипции).

    Нет аудио-потока (видео без звука) → ЧЁТКАЯ ошибка до ffmpeg (иначе пустой WAV → «Output file
    does not contain any stream», код 234 — непонятно юзеру). Quip режет по РЕЧИ → звук обязателен.
    """
    if not has_audio_stream(mp4):
        raise JobError(
            _STAGE,
            "This video has no audio track. Quip finds clips from speech, "
            "so please upload a video that has sound.",
        )
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


def build_preview_cmd(src: Path, dst: Path, *, height: int = 720, crf: int = 30) -> list[str]:
    """ffmpeg-команда для лёгкого preview-прокси редактора. PURE.

    Полный source.mp4 (1080p, 50-100МБ, иногда AV1) грузился в редакторе долго. Прокси =
    масштаб до ``height`` (``-2`` = чётная ширина по аспекту), H.264 (hw-декод в браузере, не
    софт-AV1), low-bitrate ``crf``, ``+faststart`` (moov вперёд → мгновенный старт/seek). Рендер
    финального клипа идёт из ПОЛНОГО source → качество не падает. ``height`` вызывающий клампит
    высотой источника (без апскейла).
    """
    return [
        "ffmpeg", "-y", "-i", str(src),
        "-vf", f"scale=-2:{height}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf),
        "-c:a", "aac", "-b:a", "96k",
        "-movflags", "+faststart",
        str(dst),
    ]  # fmt: skip


def build_preview_proxy(src: Path, dst: Path, *, height: int = 720, crf: int = 30) -> None:
    """Сгенерировать preview.mp4 из source.mp4 (кэш по наличию). JobError при сбое ffmpeg."""
    if dst.exists():
        return  # уже есть — не перекодируем (повторный прогон = $0/0с)
    _run(build_preview_cmd(src, dst, height=height, crf=crf))
    if not dst.exists():
        raise JobError(_STAGE, f"ffmpeg не создал preview {dst}")


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
            f"This video is {meta.duration / 60:.0f} min long, but the limit is "
            f"{MAX_SOURCE_MINUTES} min. Trim it or pick a shorter source and try again.",
        )


def import_youtube(
    url: str,
    out_dir: Path,
    *,
    job_id: str,
    cookies_browser: str = "",
    cookies_file: str = "",
) -> SourceMeta:
    """Полный Stage 0 для YouTube: download → audio → probe → meta.json. Возвращает SourceMeta."""
    mp4 = download_youtube(url, out_dir, cookies_browser=cookies_browser, cookies_file=cookies_file)
    extract_audio(mp4, out_dir / "source.wav")
    probe = probe_video(mp4)
    title = _read_title(out_dir, fallback=url)
    meta = build_source_meta(probe, job_id=job_id, source=SourceKind.youtube, url=url, title=title)
    _check_limits(meta)
    (out_dir / "meta.json").write_text(meta.model_dump_json(indent=2), encoding="utf-8")
    return meta


def _ensure_mp4(src: Path, mp4: Path) -> None:
    """Загруженный файл → source.mp4. Быстрый remux (-c copy); при несовместимости кодеков
    с mp4-контейнером — честный ре-энкод (план §B2). JobError, если ffmpeg нет/оба сбоят.

    Это НЕ тихий фолбэк (правило №8): первый шаг — оптимизация скорости; при ненулевом коде
    мы явно логируем причину переходом на ре-энкод, а ошибки ре-энкода поднимаются JobError.
    """
    try:
        proc = subprocess.run(
            ["ffmpeg", "-y", "-i", str(src), "-c", "copy", "-movflags", "+faststart", str(mp4)],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as e:
        raise JobError(_STAGE, f"не найден ffmpeg: {e}") from e
    if proc.returncode == 0 and mp4.exists():
        return
    # remux -c copy не прошёл (кодек несовместим с mp4) → ре-энкод в h264/aac
    _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(mp4),
        ]  # fmt: skip
    )
    if not mp4.exists():
        raise JobError(_STAGE, f"ffmpeg не создал {mp4}")


def import_upload(src: Path, out_dir: Path, *, job_id: str, title: str) -> SourceMeta:
    """Полный Stage 0 для загруженного файла: → source.mp4 → audio → probe → meta.json.

    src — путь к загруженному файлу (любой контейнер). Готовит те же артефакты, что и
    import_youtube, поэтому downstream-пайплайн (run_pipeline) видит их как кэш и не качает.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    if not src.exists():
        raise JobError(_STAGE, f"нет загруженного файла: {src}")
    mp4 = out_dir / "source.mp4"
    _ensure_mp4(src, mp4)
    extract_audio(mp4, out_dir / "source.wav")
    probe = probe_video(mp4)
    meta = build_source_meta(probe, job_id=job_id, source=SourceKind.upload, url=None, title=title)
    _check_limits(meta)
    (out_dir / "meta.json").write_text(meta.model_dump_json(indent=2), encoding="utf-8")
    return meta
