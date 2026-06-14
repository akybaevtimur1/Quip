"""ClipFlow/Quip — БОЕВОЙ воркер на Modal (CPU, scale-to-zero).

Архитектура (решена замером, BENCHMARKS §7 — НИКАКОГО GPU):
  • ``web``      — FastAPI (app.main) как ``@modal.asgi_app()`` на CPU, scale-to-zero.
  • ``run_job``  — отдельная долгоживущая CPU-функция: весь пайплайн (download→…→render→R2).
  • ``render_job`` — пере-рендер клипа из редактора (скачивает source из R2).

⚠️ POST /jobs в app.main делает ``run_job.spawn(...)`` (через app.dispatch), а НЕ
BackgroundTask — иначе scale-to-zero web-контейнер гаснет и нарезка умирает на полпути.

Стейт — в Supabase Postgres (PostgREST/service_role, app.cloud_state); клипы — в Cloudflare
R2 (app.storage). Включается env'ом из секрета (STORAGE_BACKEND=r2 + ключи) → тот же код, что
локально на SQLite/диске.

Образ:
  • ffmpeg — СОВРЕМЕННЫЙ статик (John Van Sickle ≥7.x), НЕ apt (debian-ffmpeg 5/6 крашит наш
    crop-рендер: «Parsed_crop_4: Failed to configure input pad»). Кладём в /usr/local/bin (ранее
    /usr/bin в PATH → наш бинарь выигрывает).
  • пакет ``app`` + ``fonts`` + ASD-веса + blaze_face.tflite монтируются в /root (PYTHONPATH=/root).
  • include_source=False — НЕ авто-инклюдить deploy/modal/ (там .venv-modal). Функции serialized.

Деплой (фаундер / агент):
  modal secret create quip-worker  DEEPGRAM_API_KEY=... GEMINI_API_KEY=... LLM_MODEL=... \
      SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... R2_ACCOUNT_ID=... R2_ACCESS_KEY_ID=... \
      R2_SECRET_ACCESS_KEY=... R2_BUCKET=quip R2_ENDPOINT=... STORAGE_BACKEND=r2 BILLING_ENABLED=true
  modal deploy deploy/modal/worker.py
"""

from __future__ import annotations

from pathlib import Path

import modal

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKER_APP = _REPO_ROOT / "services" / "worker" / "app"  # пакет `app` (импорт-имя)
_WORKER_FONTS = _REPO_ROOT / "services" / "worker" / "fonts"  # TTF для прожига субтитров
_COOKIES = _REPO_ROOT / "www.youtube.com_cookies.txt"  # gitignored; нужен для скачивания с DC-IP

# Современный статик-ffmpeg (John Van Sickle). Версия ≥7 (release) с libdav1d (декод AV1).
_FFMPEG_STATIC = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
_TORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"

image = (
    modal.Image.debian_slim(python_version="3.12")
    # Рантайм-библиотеки MediaPipe/opencv (GLES/EGL) + утилиты для установки статик-ffmpeg.
    .apt_install(
        "libgl1",
        "libglib2.0-0",
        "libegl1",
        "libgles2",
        "libglvnd0",
        "libsm6",
        "libxext6",
        "wget",
        "xz-utils",
        "unzip",  # распаковать deno-zip
        "ca-certificates",  # https-загрузки deno/ffmpeg/ejs
    )
    # Deno — JS-рантайм для yt-dlp (решение YouTube nsig/«n»-челленджа). Без него скачивание
    # падает: «n challenge solving failed». yt-dlp находит deno на PATH (/usr/local/bin).
    .run_commands(
        "wget -q https://github.com/denoland/deno/releases/latest/download/deno-x86_64-unknown-linux-gnu.zip -O /tmp/deno.zip",
        "unzip -o /tmp/deno.zip -d /usr/local/bin",
        "chmod +x /usr/local/bin/deno",
        "rm /tmp/deno.zip",
        "/usr/local/bin/deno --version",  # доказать в логах сборки
    )
    # СТАТИК-ffmpeg ≥7 в /usr/local/bin (НЕ apt-ffmpeg — он крашит crop-рендер).
    .run_commands(
        f"wget -q {_FFMPEG_STATIC} -O /tmp/ffmpeg.tar.xz",
        "cd /tmp && tar xf ffmpeg.tar.xz",
        "cp /tmp/ffmpeg-*-static/ffmpeg /tmp/ffmpeg-*-static/ffprobe /usr/local/bin/",
        "chmod +x /usr/local/bin/ffmpeg /usr/local/bin/ffprobe",
        "rm -rf /tmp/ffmpeg*",
        "/usr/local/bin/ffmpeg -version | head -1",  # доказать версию в логах сборки
    )
    # torch CPU-колесо (ASD active-speaker). Отдельным шагом со своим индексом.
    .pip_install("torch>=2.2", index_url=_TORCH_CPU_INDEX)
    # Рантайм-депы (зеркало services/worker/pyproject.toml, без dev/линтеров и неиспользуемых).
    .pip_install(
        "fastapi>=0.136.3",
        "uvicorn[standard]>=0.49.0",
        "python-multipart>=0.0.32",
        "python-dotenv>=1.0.1",
        "pyjwt[crypto]>=2.10.1",
        "pydantic>=2.13.4",
        "pydantic-settings>=2.14.1",
        "httpx>=0.28.1",
        "mediapipe>=0.10.35",
        "scenedetect>=0.6.4",
        "numpy>=2.4.6",
        "scipy>=1.11",
        "python_speech_features>=0.6",
        "google-genai>=2.8.0",
        "yt-dlp>=2026.3.17",
        "boto3>=1.35",
    )
    # Наш код + ассеты в /root (PYTHONPATH=/root → import app.*). copy=True = слой образа.
    .add_local_dir(str(_WORKER_APP), "/root/app", copy=True, ignore=["__pycache__", "*.pyc"])
    .add_local_dir(str(_WORKER_FONTS), "/root/fonts", copy=True)
    .env(
        {
            "PYTHONPATH": "/root",
            "MODAL_SPAWN": "1",  # app.dispatch → spawn (не BackgroundTask)
            # cookies для yt-dlp (обход YouTube bot-защиты с DC-IP). Файл добавляется ниже.
            "YTDLP_COOKIES_FILE": "/root/cookies.txt",
            "YTDLP_COOKIES_BROWSER": "",
            # R2 кастомный домен (production, кэш CDN, без rate-limit) → клипы получают вечный
            # публичный URL вместо presigned (D6 re-presign больше не нужен для новых джоб).
            # Это ПУБЛИЧНЫЙ CDN-домен, не секрет. NB: бакет публичен по ключу — исходники тоже.
            "R2_PUBLIC_URL": "https://cdn.quip.ink",
        }
    )
)

# cookies.txt — gitignored, кладём в образ если есть локально (иначе скачивание упрётся в бот-гейт).
if _COOKIES.exists():
    image = image.add_local_file(str(_COOKIES), "/root/cookies.txt", copy=True)

app = modal.App("quip-worker", image=image, include_source=False)

# Секрет с ключами (Deepgram/Gemini/Supabase/R2/billing). Создаётся ОДИН раз (см. docstring).
_SECRET = modal.Secret.from_name("quip-worker")


# ⚠️ Функции САМОДОСТАТОЧНЫ: тело bootstrap'а /root инлайнено в каждую, БЕЗ модульного
# хелпера. Причина: при serialized=True cloudpickle пиклит ссылку на модульную функцию по
# имени модуля (worker._bootstrap_path) → на удалёнке include_source=False срезал `worker`
# → ModuleNotFoundError при десериализации. PYTHONPATH=/root и так в образе — это страховка.


@app.function(secrets=[_SECRET], timeout=900, min_containers=0, serialized=True)
@modal.asgi_app()
def web() -> object:
    """Лёгкий FastAPI (app.main): POST /jobs (spawn run_job), GET статусы, редактор. Scale-to-zero."""
    import sys

    if "/root" not in sys.path:
        sys.path.insert(0, "/root")
    from app.main import app as fastapi_app

    return fastapi_app


@app.function(secrets=[_SECRET], timeout=3600, min_containers=0, serialized=True)
def run_job(
    job_id: str,
    source_type: str,
    source_ref: str,
    max_clips: int | None = None,
    user_id: str | None = None,
) -> None:
    """Весь пайплайн для одного источника: download→transcribe→select→reframe→render→R2+Postgres.

    Долгоживущая CPU-функция (до 60 мин). Стейт/артефакты/клипы — в Supabase+R2 (app.tasks роутит).
    """
    import sys

    if "/root" not in sys.path:
        sys.path.insert(0, "/root")
    from app.tasks import run_pipeline_job

    run_pipeline_job(job_id, source_type, source_ref, max_clips, user_id)


@app.function(secrets=[_SECRET], timeout=1200, min_containers=0, serialized=True)
def render_job(job_id: str, clip_id: str) -> None:
    """Пере-рендер клипа из текущего edit-state (редактор). source.mp4 скачивается из R2."""
    import sys

    if "/root" not in sys.path:
        sys.path.insert(0, "/root")
    from app.tasks import render_clip_edit_job

    render_clip_edit_job(job_id, clip_id)
