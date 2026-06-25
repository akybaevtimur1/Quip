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
        raise JobError(_STAGE, "empty r_frame_rate")
    try:
        if "/" in rate:
            num_s, den_s = rate.split("/", 1)
            num, den = float(num_s), float(den_s)
            if den == 0:
                raise JobError(_STAGE, f"zero fps denominator: {rate!r}")
            fps = num / den
        else:
            fps = float(rate)
    except JobError:
        raise
    except ValueError as e:
        raise JobError(_STAGE, f"cannot parse r_frame_rate {rate!r}: {e}") from e
    if fps <= 0:
        # 0 fps → ZeroDivisionError в round(start*fps)/fps (stage5_render);
        # отрицательный → битая кадровая математика. Явный отказ вместо тихого брака.
        raise JobError(_STAGE, f"non-positive fps: {rate!r} → {fps}")
    return round(fps, 3)


# yt-dlp скачивание best-effort: с DC-IP (Modal) YouTube периодически режет бот-гейтом. Когда
# не вышло — НЕ молчим: классифицируем stderr в понятное ENG-сообщение, КАЖДОЕ оканчивается
# призывом «скачай сам и загрузи файл» (graceful fallback на upload-путь).
_YT_UPLOAD_HINT = (
    " Please download it yourself — e.g. with a Telegram downloader bot or another "
    "site — and upload the file."
)


def classify_youtube_error(stderr_tail: str) -> str:
    """yt-dlp stderr → понятное пользователю ENG-сообщение. PURE.

    Маппит известные сигнатуры провала yt-dlp в ясный текст. Регистронезависимо (yt-dlp
    меняет регистр/формулировки между версиями). КАЖДОЕ сообщение заканчивается actionable-
    подсказкой ``_YT_UPLOAD_HINT`` (best-effort: автоскачивание — удобство, не гарантия;
    всегда есть путь «залей файл сам»).
    """
    s = (stderr_tail or "").lower()

    # ВАЖЕН ПОРЯДОК: «Sign in to confirm your AGE» — частный случай «sign in to confirm»,
    # поэтому возрастной гейт проверяем РАНЬШЕ бот-гейта (иначе age-видео ловится как бот).
    if "confirm your age" in s or "age-restricted" in s or "inappropriate for some users" in s:
        return (
            "This video is age-restricted and requires a sign-in we don’t have." + _YT_UPLOAD_HINT
        )

    # bot-gate / rate-limit / forbidden — самый частый провал с дата-центрового IP.
    bot_signatures = (
        "sign in to confirm you",  # "...you're not a bot" (юникод-апостроф варьируется)
        "not a bot",
        "http error 429",
        "too many requests",
        "http error 403",
        "forbidden",
        "failed to extract any player response",
    )
    if any(sig in s for sig in bot_signatures):
        return (
            "We could not fetch this video automatically (YouTube blocked our server)."
            + _YT_UPLOAD_HINT
        )

    # приватное / только для участников канала.
    if "members-only" in s or "join this channel" in s:
        return "This video is members-only, so we can’t fetch it." + _YT_UPLOAD_HINT
    if "is private" in s or "private video" in s:
        return "This video is private, so we can’t fetch it." + _YT_UPLOAD_HINT

    # удалено / недоступно.
    if "video unavailable" in s or "has been removed" in s or "no longer available" in s:
        return "This video is no longer available on YouTube." + _YT_UPLOAD_HINT

    # региональная блокировка.
    if "available in your country" in s or "blocked it in your country" in s or "geo" in s:
        return (
            "This video is not available in our server’s region (region-locked)." + _YT_UPLOAD_HINT
        )

    # лайв / премьера (ещё не вышло целиком).
    if "live event will begin" in s or "premiere" in s or "premieres in" in s or "is live" in s:
        return "This is a live stream or premiere, which we can’t process yet." + _YT_UPLOAD_HINT

    # неизвестная сигнатура — общий честный фолбэк (всё ещё с upload-подсказкой).
    return "We could not fetch this video from YouTube automatically." + _YT_UPLOAD_HINT


def build_youtube_cmd(
    url: str,
    out_dir: Path,
    *,
    cookies_browser: str = "",
    cookies_file: str = "",
    proxy: str = "",
    pot_server_home: str = "",
) -> list[str]:
    """Собрать yt-dlp-команду для скачивания ``url`` → ``out_dir/source.mp4``. PURE.

    Ключевые гарантии:
    - **avc1-first ≤1080p** — предпочитаем H.264 (софт-декод AV1 в reframe-анализе ~2-5×
      медленнее); потолок 1080p (reframe-safety + стоимость). 1080p мукс = adaptive
      video+audio + ffmpeg-merge (см. ``--merge-output-format mp4``).
    - **faststart** — ``--postprocessor-args`` двигает moov-atom в начало файла; иначе yt-dlp
      кладёт moov в EOF → preview range-requests тянут весь файл перед стартом (gotcha).
    - **match-filter** — отклоняет лайвстримы и видео длиннее ``MAX_SOURCE_MINUTES`` ДО
      скачивания (не качаем то, что всё равно упрётся в ``_check_limits``).
    - **--no-playlist** — один URL = одно видео (ссылка из плейлиста не тянет весь плейлист).
    - **proxy** (опц.) — будущий рычаг надёжности (обход DC-IP бот-гейта); пусто = без прокси.
    - **pot_server_home** (опц.) — bgutil PO-token provider в SCRIPT-режиме поверх cookies.
      Заполнен → добавляем ``--extractor-args youtubepot-bgutilscript:server_home=<path>``
      (yt-dlp вызывает Deno-генератор PO-токена per-token). Пусто = без POT (локальный dev,
      провайдер не собран). Pip-плагин bgutil-ytdlp-pot-provider авто-подхватывается yt-dlp.
    """
    max_seconds = MAX_SOURCE_MINUTES * 60
    cmd = [
        "yt-dlp",
        "-f",
        # Предпочитаем H.264 (avc1) — софт-декод AV1 в reframe-анализе в ~2-5× медленнее и
        # засыпает лог hw-accel-ошибками. Фолбэки: mp4(av1) → любой 1080 → best.
        "bestvideo[height<=1080][vcodec^=avc1]+bestaudio[ext=m4a]/bestvideo[height<=1080][ext=mp4]+bestaudio/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "--merge-output-format",
        "mp4",
        "--no-playlist",
        # Отсекаем лайв/премьеры и переростки ДО скачивания (живой стрим качать нельзя; видео
        # длиннее техпотолка всё равно отвалится в _check_limits — не тратим трафик/время).
        "--match-filter",
        f"!is_live & duration < {max_seconds}",
        # moov-atom → начало файла (faststart): без этого yt-dlp кладёт его в EOF и preview
        # range-requests тянут весь файл перед стартом плеера (gotcha из памяти команды).
        "--postprocessor-args",
        "ffmpeg:-movflags +faststart",
        # YouTube nsig/«n»-челлендж требует JS-рантайм (Deno в образе) + EJS-скрипты решателя.
        # ejs:github подтягивает их с GitHub в рантайме (yt-dlp #15012). С yt-dlp[default] в
        # образе решатель локален — этот флаг остаётся безопасным фолбэком.
        "--remote-components",
        "ejs:github",
        "--max-filesize",
        "2G",
        "--write-info-json",
        "--restrict-filenames",
        "-o",
        str(out_dir / "source.%(ext)s"),
    ]
    if proxy:
        cmd += ["--proxy", proxy]
    if cookies_file:
        cmd += ["--cookies", cookies_file]
    elif cookies_browser:
        cmd += ["--cookies-from-browser", cookies_browser]
    # bgutil PO-token (SCRIPT mode): the pip plugin (bgutil-ytdlp-pot-provider) auto-loads and the
    # `server_home` points at the bgutil `server/` dir built into the image. yt-dlp spawns the Deno
    # generator per-token (no HTTP server). Layered on TOP of cookies, not a replacement.
    if pot_server_home:
        cmd += ["--extractor-args", f"youtubepot-bgutilscript:server_home={pot_server_home}"]
    cmd.append(url)
    return cmd


def _video_stream(probe: dict[str, Any]) -> dict[str, Any]:
    streams = probe.get("streams") or []
    if not streams:
        raise JobError(_STAGE, "ffprobe returned no video stream")
    stream: dict[str, Any] = streams[0]
    return stream


def _duration(probe: dict[str, Any], stream: dict[str, Any]) -> float:
    raw: Any = stream.get("duration")
    if raw in (None, "", "N/A"):
        fmt = probe.get("format")
        raw = fmt.get("duration") if isinstance(fmt, dict) else None
    if raw in (None, "", "N/A"):
        raise JobError(_STAGE, "ffprobe returned no duration")
    try:
        dur = float(raw)
    except (TypeError, ValueError) as e:
        raise JobError(_STAGE, f"malformed duration {raw!r}: {e}") from e
    if dur <= 0:
        raise JobError(_STAGE, f"non-positive duration: {dur}")
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
        raise JobError(_STAGE, f"no width/height in ffprobe: {e}") from e
    if width <= 0 or height <= 0:
        raise JobError(_STAGE, f"invalid frame dimensions: {width}x{height}")
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
        raise JobError(_STAGE, f"binary not found {cmd[0]!r}: {e}") from e
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip()[-500:]
        raise JobError(_STAGE, f"{cmd[0]} exit code {proc.returncode}: {tail}")
    return proc


def download_youtube(
    url: str,
    out_dir: Path,
    *,
    cookies_browser: str = "",
    cookies_file: str = "",
    proxy: str = "",
    pot_server_home: str = "",
) -> Path:
    """yt-dlp → ``out_dir/source.mp4`` (+ source.info.json). Возвращает путь к mp4.

    Best-effort: на DC-IP (Modal) YouTube периодически режет бот-гейтом. При провале yt-dlp
    НЕ молчим — классифицируем stderr в понятное ENG-сообщение (``classify_youtube_error``),
    которое всегда зовёт юзера залить файл вручную (graceful fallback на upload-путь, правило №8).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = build_youtube_cmd(
        url,
        out_dir,
        cookies_browser=cookies_browser,
        cookies_file=cookies_file,
        proxy=proxy,
        pot_server_home=pot_server_home,
    )
    try:
        _run(cmd)
    except JobError as e:
        # _run кидает JobError с хвостом stderr → перекладываем в дружелюбный текст. raise from e
        # сохраняет техдетали в цепочке исключений (лог), но юзер видит actionable-сообщение.
        raise JobError(_STAGE, classify_youtube_error(e.reason)) from e
    mp4 = out_dir / "source.mp4"
    if not mp4.exists():
        # yt-dlp вышел с кодом 0, но файла нет (например match-filter отсёк лайв/переросток до
        # скачивания). Тоже best-effort-провал → понятный текст + upload-подсказка.
        raise JobError(_STAGE, classify_youtube_error(f"yt-dlp did not create {mp4}"))
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
        raise JobError(_STAGE, f"ffmpeg did not create {wav}")


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
        raise JobError(_STAGE, f"ffmpeg did not create preview {dst}")


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
    proxy: str = "",
    pot_server_home: str = "",
) -> SourceMeta:
    """Полный Stage 0 для YouTube: download → audio → probe → meta.json. Возвращает SourceMeta."""
    mp4 = download_youtube(
        url,
        out_dir,
        cookies_browser=cookies_browser,
        cookies_file=cookies_file,
        proxy=proxy,
        pot_server_home=pot_server_home,
    )
    extract_audio(mp4, out_dir / "source.wav")
    probe = probe_video(mp4)
    title = _read_title(out_dir, fallback=url)
    meta = build_source_meta(probe, job_id=job_id, source=SourceKind.youtube, url=url, title=title)
    _check_limits(meta)
    (out_dir / "meta.json").write_text(meta.model_dump_json(indent=2), encoding="utf-8")
    return meta


def _try_ffmpeg(cmd: list[str], out: Path) -> bool:
    """Прогнать одну ffmpeg-попытку. True ⇔ код 0 И файл создан. ffmpeg не найден → JobError."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError as e:
        raise JobError(_STAGE, f"ffmpeg not found: {e}") from e
    return proc.returncode == 0 and out.exists()


def _ensure_mp4(src: Path, mp4: Path) -> None:
    """Загруженный файл → source.mp4 МИНИМАЛЬНОЙ работой (без скрытого full-транскода зря):

      1) remux ``-c copy`` — мгновенно, если кодеки уже mp4-совместимы (обычный H.264 mp4/mov);
      2) видео ``copy`` + только аудио в aac — частый случай .mkv (H.264-видео + Opus/AC3-аудио):
         избегаем ПОЛНОГО видео-ре-энкода (для 3 ч это десятки минут CPU);
      3) полный ре-энкод h264/aac (``-threads 0``) — последний резерв (реально несовместимое видео).

    Выбранный путь печатаем (виден в логах Modal) — раньше fallback был «тихим» (docstring врал).
    JobError (правило №8), если даже полный ре-энкод не создал файл.
    """
    if _try_ffmpeg(
        ["ffmpeg", "-y", "-i", str(src), "-c", "copy", "-movflags", "+faststart", str(mp4)], mp4
    ):
        print("[import] source.mp4 via remux (-c copy)")
        return
    if _try_ffmpeg(
        ["ffmpeg", "-y", "-i", str(src), "-c:v", "copy", "-c:a", "aac",
         "-movflags", "+faststart", str(mp4)],
        mp4,
    ):  # fmt: skip
        print("[import] source.mp4 via audio-only re-encode (video copied)")
        return
    print("[import] source.mp4 via FULL re-encode (incompatible video codec)")
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
            "-threads",
            "0",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(mp4),
        ]  # fmt: skip
    )
    if not mp4.exists():
        raise JobError(_STAGE, f"ffmpeg did not create {mp4}")


def import_upload(src: Path, out_dir: Path, *, job_id: str, title: str) -> SourceMeta:
    """Полный Stage 0 для загруженного файла: → source.mp4 → audio → probe → meta.json.

    src — путь к загруженному файлу (любой контейнер). Готовит те же артефакты, что и
    import_youtube, поэтому downstream-пайплайн (run_pipeline) видит их как кэш и не качает.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    if not src.exists():
        raise JobError(_STAGE, f"no uploaded file: {src}")
    mp4 = out_dir / "source.mp4"
    _ensure_mp4(src, mp4)
    extract_audio(mp4, out_dir / "source.wav")
    probe = probe_video(mp4)
    meta = build_source_meta(probe, job_id=job_id, source=SourceKind.upload, url=None, title=title)
    _check_limits(meta)
    (out_dir / "meta.json").write_text(meta.model_dump_json(indent=2), encoding="utf-8")
    return meta
