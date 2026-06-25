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
        "git",  # git clone bgutil PO-token провайдера (нет в debian-slim по умолчанию)
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
    # ── bgutil PO-token (Proof-of-Origin) provider v1.3.1 — SCRIPT mode, DENO runtime ──
    # YouTube bot-gates Modal DC-IPs; cookies (above) authenticate the session, the PO token
    # attests proof-of-origin of the player request. Both signals are checked → we layer POT on
    # top of cookies. We REUSE the Deno already in the image (no Node added): the bgutil plugin
    # registers a Deno script-provider (higher preference than Node) that runs server/src/
    # generate_once.ts directly — NO `npx tsc` build step. node-canvas (the only native dep)
    # resolves via its NAPI-7 glibc PREBUILT tarball at `deno install` time, so debian-slim needs
    # ZERO extra apt build deps (confirmed: bgutil's own Dockerfile installs none). Clone shallow,
    # pin tag 1.3.1, resolve+cache deps at BUILD time (runtime token-gen does no network fetch of
    # deps), then strip .git to keep the layer small. server_home = the `server/` dir (NOT build/).
    .run_commands(
        "git clone --depth 1 --single-branch --branch 1.3.1 "
        "https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git "
        "/opt/bgutil-ytdlp-pot-provider",
        # canvas is the only native module needing --allow-scripts; --frozen uses the committed
        # lockfile for a reproducible build (drop --frozen only if a 1.3.x lock drifts at build).
        "cd /opt/bgutil-ytdlp-pot-provider/server && "
        "deno install --allow-scripts=npm:canvas",
        # warm the module cache so per-token `deno run` does zero dependency network fetches
        "cd /opt/bgutil-ytdlp-pot-provider/server && deno cache src/generate_once.ts",
        # trim build cruft (keep server/src, deno.json, deno.lock, node_modules/canvas)
        "rm -rf /opt/bgutil-ytdlp-pot-provider/.git",
        "ls /opt/bgutil-ytdlp-pot-provider/server/src/generate_once.ts",  # доказать в логах сборки
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
        # yt-dlp[default] (НЕ bare yt-dlp): бандлит yt-dlp-ejs → решатель YouTube nsig/«n»-
        # челленджа ЛОКАЛЕН в образе (а не качается с GitHub в рантайме через
        # --remote-components ejs:github). ⚠️ Вступает в силу ТОЛЬКО при следующем
        # `modal deploy deploy/modal/worker.py` (оркестратор/фаундер деплоит позже — здесь НЕ
        # деплоим). yt-dlp обновлять ЧАСТО: бот-гейт YouTube дрейфует, старый клиент = провалы.
        "yt-dlp[default]>=2026.3.17",
        # bgutil PO-token yt-dlp PLUGIN (pip side). Auto-loaded by yt-dlp via the yt_dlp_plugins
        # namespace — no plugins dir needed. MUST be the SAME version (1.3.1) as the provider
        # built above (a plugin↔server version mismatch yields tokens YouTube rejects with 403).
        # Pairs with --extractor-args youtubepot-bgutilscript:server_home=... (stage0_import).
        "bgutil-ytdlp-pot-provider==1.3.1",
        "boto3>=1.35",
    )
    # Наш код + ассеты в /root (PYTHONPATH=/root → import app.*). copy=True = слой образа.
    .add_local_dir(str(_WORKER_APP), "/root/app", copy=True, ignore=["__pycache__", "*.pyc"])
    .add_local_dir(str(_WORKER_FONTS), "/root/fonts", copy=True)
    .env(
        {
            "PYTHONPATH": "/root",
            "MODAL_SPAWN": "1",  # app.dispatch → spawn (не BackgroundTask)
            # На Modal (DC-IP) браузерных cookies нет → НЕ ставим YTDLP_COOKIES_BROWSER
            # (дефолт config = "edge" — на Linux-контейнере его нет, yt-dlp упал бы).
            # YTDLP_COOKIES_FILE ставится НИЖЕ, ТОЛЬКО если файл реально кладётся в образ
            # (иначе yt-dlp с несуществующим --cookies путём падает / тянет пустой jar).
            "YTDLP_COOKIES_BROWSER": "",
            # bgutil PO-token provider (SCRIPT mode) — the `server/` dir of the bgutil repo we
            # built above. config.ytdlp_pot_server_home reads this; stage0.build_youtube_cmd then
            # appends --extractor-args youtubepot-bgutilscript:server_home=<this>. yt-dlp finds
            # `deno` on PATH (/usr/local/bin) and spawns it per-token (no Node, no HTTP server).
            "YTDLP_POT_SERVER_HOME": "/opt/bgutil-ytdlp-pot-provider/server",
            # R2 кастомный домен (production, кэш CDN, без rate-limit) → клипы получают вечный
            # публичный URL вместо presigned (D6 re-presign больше не нужен для новых джоб).
            # Это ПУБЛИЧНЫЙ CDN-домен, не секрет. NB: бакет публичен по ключу — исходники тоже.
            "R2_PUBLIC_URL": "https://cdn.quip.ink",
        }
    )
)

# cookies.txt — gitignored, кладём в образ если есть локально (иначе скачивание упрётся в бот-гейт).
# ⚠️ YTDLP_COOKIES_FILE ставим ТОЛЬКО когда файл реально добавлен: yt-dlp с указанным, но
# отсутствующим --cookies путём падает (cookie-jar save в несуществующий каталог) ИЛИ тянет
# пустой jar (нулевой обход бот-гейта). Нет файла → переменная не задаётся, yt-dlp идёт без cookies.
if _COOKIES.exists():
    image = image.add_local_file(str(_COOKIES), "/root/cookies.txt", copy=True).env(
        {"YTDLP_COOKIES_FILE": "/root/cookies.txt"}
    )

app = modal.App("quip-worker", image=image, include_source=False)

# Секрет с ключами (Deepgram/Gemini/Supabase/R2). Создаётся ОДИН раз (см. docstring).
_SECRET = modal.Secret.from_name("quip-worker")
# Биллинг ОТДЕЛЬНЫМ секретом (BILLING_ENABLED + POLAR_WEBHOOK_SECRET + POLAR_PRODUCT_*), чтобы
# включать/крутить оплату, НЕ перекраивая рабочий quip-worker. Modal сливает env обоих секретов.
_BILLING_SECRET = modal.Secret.from_name("quip-billing")


# ⚠️ Функции САМОДОСТАТОЧНЫ: тело bootstrap'а /root инлайнено в каждую, БЕЗ модульного
# хелпера. Причина: при serialized=True cloudpickle пиклит ссылку на модульную функцию по
# имени модуля (worker._bootstrap_path) → на удалёнке include_source=False срезал `worker`
# → ModuleNotFoundError при десериализации. PYTHONPATH=/root и так в образе — это страховка.


# timeout=3600 (НЕ 900): POST /jobs/upload СТРИМИТ весь файл ЧЕРЕЗ этот web-контейнер (приём
# байтов + стейджинг в R2 = в одном запросе). Большое видео по обычному каналу грузится >15 мин →
# на 900s Modal убивал input → «застряло на 100% + 500». 3600s (как run_job) даёт загрузке дойти.
# (Правильный долгосрочный фикс — прямая presigned-загрузка браузер→R2; уже сделан, см. api.ts.)
#
# ⚡ ЛАТЕНТНОСТЬ ФРОНТА (замер: cold ~5s vs warm ~0.4s). web обслуживает /jobs/upload-url (БЛОКИРУЕТ
# старт загрузки), /upload-complete и опрос статуса — это латентность-чувствительный путь. Два рычага:
#   • min_containers=1 — входная дверь ВСЕГДА тёплая → нет +5s холодного старта перед загрузкой
#     (отход от scale-to-zero ТОЛЬКО для лёгкого web; pipeline-функции остаются на 0 — там warm дорого).
#   • @modal.concurrent(max_inputs=100) — web I/O-bound (ходит в Supabase/R2, спавнит джобы, без тяжёлого
#     CPU): ОДИН контейнер тянет сотню параллельных запросов. Без него Modal плодит ~контейнер на запрос
#     → под нагрузкой (десятки юзеров) рой ХОЛОДНЫХ стартов и очередь → тормозит у всех.
@app.function(secrets=[_SECRET, _BILLING_SECRET], timeout=3600, min_containers=1, serialized=True)
@modal.concurrent(max_inputs=100)
@modal.asgi_app()
def web() -> object:
    """Лёгкий FastAPI (app.main): POST /jobs (spawn run_job), GET статусы, редактор. Warm + concurrent."""
    import sys

    if "/root" not in sys.path:
        sys.path.insert(0, "/root")
    from app.main import app as fastapi_app

    return fastapi_app


# timeout=10800 (3h, НЕ 1h): длинные источники (до 3h-потолка контента) гоняют ВЕСЬ пайплайн
# здесь — включая полный preview-транскод source→720p (~30-60 мин для 3h) + транскрипцию +
# реframe/рендер. На 1h тяжёлый джоб умирал бы на полпути. 3h ≈ потолок контента (MAX_VIDEO_MINUTES)
# → ограничивает и runaway-стоимость.
# cpu=4/memory=4096: пайплайн CPU-bound (ffmpeg -threads 0 + torch ASD). Дефолтный ~1/8 ядра
# душил кодирование — больше ядер ≈ линейно быстрее, cost (ядро·сек) почти не меняется (быстрее).
@app.function(
    secrets=[_SECRET, _BILLING_SECRET],
    timeout=10800,
    cpu=4,
    memory=4096,
    min_containers=0,
    serialized=True,
)
def run_job(
    job_id: str,
    source_type: str,
    source_ref: str,
    max_clips: int | None = None,
    user_id: str | None = None,
) -> None:
    """Весь пайплайн для одного источника: download→transcribe→select→reframe→render→R2+Postgres.

    Долгоживущая CPU-функция (до 3 ч). Стейт/артефакты/клипы — в Supabase+R2 (app.tasks роутит).
    """
    import sys

    if "/root" not in sys.path:
        sys.path.insert(0, "/root")
    from app.tasks import run_pipeline_job

    run_pipeline_job(job_id, source_type, source_ref, max_clips, user_id)


# timeout=10800 (3h): качает залитый источник (до ~5 ГБ) на свой контейнер + гоняет тот же
# полный пайплайн (incl. preview-транскод). Тяжёлой/длинной загрузке 1h мало — см. run_job.
# cpu=4/memory=4096: то же, что run_job (CPU-bound пайплайн + крупный source-download).
@app.function(
    secrets=[_SECRET, _BILLING_SECRET],
    timeout=10800,
    cpu=4,
    memory=4096,
    min_containers=0,
    serialized=True,
)
def upload_job(
    job_id: str,
    filename: str,
    max_clips: int | None = None,
    user_id: str | None = None,
) -> None:
    """Пайплайн для ЗАГРУЖЕННОГО файла (не URL). web-контейнер залил исходник в R2
    (storage.upload_source) и спавнил эту долгоживущую функцию — она качает исходник на СВОЙ
    контейнер и гоняет тот же run_upload_job (web scale-to-zero убил бы фон-таск на полпути).
    """
    import sys
    from pathlib import Path

    if "/root" not in sys.path:
        sys.path.insert(0, "/root")
    from app import artifacts, storage
    from app.tasks import run_upload_job

    out = artifacts.job_dir(job_id)
    out.mkdir(parents=True, exist_ok=True)
    suffix = Path(filename).suffix.lower() or ".mp4"
    upload_path = out / f"upload{suffix}"
    storage.download_source(job_id, upload_path)  # raw upload, залитый web-контейнером в R2
    run_upload_job(job_id, str(upload_path), filename, max_clips, user_id)


# cpu=4/memory=4096: пере-рендер клипа = ffmpeg (reframe+прожиг) → больше ядер = быстрее.
@app.function(
    secrets=[_SECRET, _BILLING_SECRET],
    timeout=1200,
    cpu=4,
    memory=4096,
    min_containers=0,
    serialized=True,
)
def render_job(job_id: str, clip_id: str) -> None:
    """Пере-рендер клипа из текущего edit-state (редактор). source.mp4 скачивается из R2."""
    import sys

    if "/root" not in sys.path:
        sys.path.insert(0, "/root")
    from app.tasks import render_clip_edit_job

    render_clip_edit_job(job_id, clip_id)


# Фан-аут per-clip (perf #1): ОДИН контейнер на клип → клипы рендерятся ПАРАЛЛЕЛЬНО, а не
# последовательным циклом на одном run_job-контейнере. source.mp4 скачивается из R2
# (artifacts.ensure_source — тот же путь, что у editor-render). timeout=1800 с запасом на длинный
# клип (reframe ASD ~реалтайм + рендер). cpu=4/memory=4096 как render_job (CPU-bound ffmpeg+torch).
# Возвращает picklable result-dict; run.py собирает из них ClipOut. НЕ трогает stage3/stage5 —
# только зовёт reframe_segment/render_clip (инвариант кадровой сетки цел).
@app.function(
    secrets=[_SECRET, _BILLING_SECRET],
    timeout=1800,
    cpu=4,
    memory=4096,
    min_containers=0,
    serialized=True,
)
def reframe_render_clip(
    job_id: str,
    clip_index: int,
    seg: dict,
    meta: dict,
    user_id: str | None = None,
) -> dict:
    """Stages 3–5 ОДНОГО клипа на своём контейнере (параллельный фан-аут run_job).

    ``user_id`` (владелец джоба) → план резолвится СЕРВЕРНО внутри render_one_clip
    (вотермарка для free + потолок разрешения). Дефолт None оставлен для обратной совместимости
    со старыми in-flight стартмапами; в проде run.clip_spawn_args ВСЕГДА передаёт user_id.
    """
    import sys

    if "/root" not in sys.path:
        sys.path.insert(0, "/root")
    from app import artifacts
    from app.errors import JobError
    from app.models import Segment
    from app.pipeline.stage0_import import SourceMeta
    from app.run import failed_clip_result, render_one_clip

    src = artifacts.ensure_source(job_id)  # качает source из R2 на свежий контейнер
    # КОНТЕЙНИРОВАНИЕ per-clip провала: ловим ЗДЕСЬ (в дочернем контейнере), а НЕ даём
    # исключению вылететь — иначе starmap ре-рейзит его в координаторе run_job и валит ВЕСЬ
    # джоб. Возвращаем failed_clip_result (пустой video_url = still/failed по streaming-
    # контракту) → координатор соберёт ClipOut с пустым url, остальные клипы дойдут, джоб
    # done. Провал ЯВНО логируем (правило №8). Тотальный провал (все клипы упали) ловит
    # run._render_all_clips → JobError → джоб честно failed. НЕ трогает stage3/stage5.
    try:
        return render_one_clip(
            src.parent,
            src.name,
            clip_index,
            Segment.model_validate(seg),
            SourceMeta.model_validate(meta),
            user_id,
        )
    except JobError as e:
        print(f"[reframe_render_clip] clip_{clip_index:02d} FAILED (contained): {e}")
        return failed_clip_result(clip_index, str(e))
    except Exception as e:
        print(f"[reframe_render_clip] clip_{clip_index:02d} FAILED (contained, unexpected): {e}")
        return failed_clip_result(clip_index, f"unexpected: {e}")


# Preview-прокси (perf #3) — отдельная функция: run_job спавнит её ПАРАЛЛЕЛЬНО с клипами, она НЕ
# держит set_done (раньше полный транскод source→720p сидел на критическом пути, до 30-60 мин для
# 3ч-видео). Качает source из R2, строит ≤720p H.264 faststart, льёт preview в R2. Редактор
# фолбэчит на source, пока прокси не готов (storage.preview_read_url). cpu=2 — лёгкий ре-энкод.
@app.function(
    secrets=[_SECRET, _BILLING_SECRET],
    timeout=1800,
    cpu=2,
    memory=2048,
    min_containers=0,
    serialized=True,
)
def preview_job(job_id: str) -> None:
    """Построить и залить preview.mp4 в R2 (вне критического пути джоба)."""
    import sys

    if "/root" not in sys.path:
        sys.path.insert(0, "/root")
    from app import artifacts, storage
    from app.config import get_settings
    from app.pipeline.stage0_import import build_preview_proxy

    s = get_settings()
    src = artifacts.ensure_source(job_id)
    meta = artifacts.load_meta(job_id)
    dst = src.parent / "preview.mp4"
    build_preview_proxy(src, dst, height=min(s.preview_height, meta.height), crf=s.preview_crf)
    storage.upload_preview(dst, job_id)


@app.function(
    secrets=[_SECRET, _BILLING_SECRET],
    timeout=600,
    cpu=2,
    memory=2048,
    min_containers=0,
    serialized=True,
)
def agent_edit_job(run_id: str) -> None:
    """W3: агент-чат редактора (Gemini function-calling + правки edit-state). Отдельная функция —
    отменяемый Stop'ом долгоживущий джоб (как run_job). Биллинг минут не трогает."""
    import sys

    if "/root" not in sys.path:
        sys.path.insert(0, "/root")
    from app.tasks import agent_edit_job as _job

    _job(run_id)


# VideoMap: нарративный анализ (главы+моменты+связный разбор) в ОТДЕЛЬНОМ контейнере. Имя функции
# ОБЯЗАНО совпадать со строкой dispatch.spawn("generate_video_map_job", ...). Результат durable в
# Postgres job_artifacts.video_map (save_video_map) → web-контейнер /video-map читает его.
@app.function(
    secrets=[_SECRET, _BILLING_SECRET],
    timeout=600,
    cpu=2,
    memory=2048,
    min_containers=0,
    serialized=True,
)
def generate_video_map_job(job_id: str) -> None:
    """Сгенерировать VideoMap (Gemini) и сохранить в Postgres + диск контейнера."""
    import sys

    if "/root" not in sys.path:
        sys.path.insert(0, "/root")
    from app import tasks

    tasks.generate_video_map_job(job_id)


# Ретеншн R2: source.mp4/preview.mp4 — 70-90% хранилища, нужны лишь редактору; клипы (продукт)
# вечны. Без чистки R2 растёт безлимитно (разовая оплата → вечное хранение). Раз в сутки удаляем
# editor-only артефакты старше DEFAULT_SOURCE_RETENTION_DAYS. _SECRET даёт R2-креды.
@app.function(secrets=[_SECRET], timeout=900, schedule=modal.Cron("0 4 * * *"), serialized=True)
def cleanup_stale_sources() -> None:
    """Ежедневная (04:00 UTC) чистка R2: удалить source/preview старше окна. Клипы не трогаем."""
    import sys

    if "/root" not in sys.path:
        sys.path.insert(0, "/root")
    from app.storage import delete_stale_editor_artifacts

    n = delete_stale_editor_artifacts()
    print(f"[retention] deleted {n} stale source/preview objects")


# ── Rotating YouTube cookies (free bot-gate bypass) ──────────────────────────────────────────
# yt-dlp rewrites the --cookies file with a fresh session after each run; we persist that jar in
# R2 (app.ytdlp_cookies) so the rotation survives Modal's read-only/ephemeral containers. The two
# functions below KEEP it alive and SEED it. Both reuse _SECRET (R2 creds) and the baked image's
# yt-dlp + Deno (n-challenge JS runtime). They do NOT touch reframe/render or per-clip containment.

# KEEP-WARM: even with zero user traffic the YouTube session would idle-expire. Every ~2 days we
# pull the jar from R2, run a LIGHTWEIGHT --skip-download rotation against a stable public CC clip
# (KEEP_WARM_VIDEO_URL), and push the rotated jar back → session stays fresh. _SECRET gives R2 creds.
@app.function(secrets=[_SECRET], timeout=600, schedule=modal.Cron("0 5 */2 * *"), serialized=True)
def refresh_ytdlp_cookies() -> None:
    """Keep the YouTube cookie session alive (R2 jar) via a lightweight --skip-download ping."""
    import subprocess
    import sys
    import tempfile
    from pathlib import Path

    if "/root" not in sys.path:
        sys.path.insert(0, "/root")
    from app import ytdlp_cookies

    tmp = Path(tempfile.gettempdir()) / "ytdlp_cookies_keepwarm.txt"
    if not ytdlp_cookies.pull_cookies(tmp):
        print("[ytdlp-cookies] keep-warm SKIP: no cookie jar in R2 yet (run seed_ytdlp_cookies once)")
        return
    # --skip-download: no media fetched, but yt-dlp still touches the session and REWRITES tmp with
    # refreshed cookies (the whole point). --remote-components ejs:github keeps the n-challenge
    # solver available (mirrors stage0_import.build_youtube_cmd). Best-effort: log result, then push.
    cmd = [
        "yt-dlp",
        "--skip-download",
        "--no-playlist",
        "--remote-components",
        "ejs:github",
        "--cookies",
        str(tmp),
        ytdlp_cookies.KEEP_WARM_VIDEO_URL,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip()[-500:]
        print(f"[ytdlp-cookies] keep-warm yt-dlp exit {proc.returncode}: {tail}")
    else:
        print(f"[ytdlp-cookies] keep-warm rotation ok against {ytdlp_cookies.KEEP_WARM_VIDEO_URL}")
    ytdlp_cookies.push_cookies(tmp)  # push rotated jar back (logged; keeps last-known-good on fail)


# ONE-TIME SEED (CLI: `modal run deploy/modal/worker.py::seed_ytdlp_cookies`). Reads the baked image
# file /root/cookies.txt (the www.youtube.com_cookies.txt the founder dropped at repo root) and
# uploads it to the R2 cookie key. After this, R2 is the rotating store; the baked file is only the
# seed source. Absent /root/cookies.txt → clear message (no crash). _SECRET gives R2 creds.
@app.function(secrets=[_SECRET], timeout=300, serialized=True)
def seed_ytdlp_cookies() -> None:
    """One-time: upload the baked /root/cookies.txt to the R2 cookie key (seeds the rotating jar)."""
    import sys
    from pathlib import Path

    if "/root" not in sys.path:
        sys.path.insert(0, "/root")
    from app import ytdlp_cookies

    baked = Path("/root/cookies.txt")
    if not baked.exists():
        print(
            "[ytdlp-cookies] seed SKIP: /root/cookies.txt absent. Drop "
            "www.youtube.com_cookies.txt at repo root, redeploy, then run this seed again."
        )
        return
    ytdlp_cookies.push_cookies(baked)
    print(f"[ytdlp-cookies] seeded R2 cookie jar (r2://{ytdlp_cookies.cookies_r2_key()}) from {baked}")


# DIAGNOSTIC (CLI: `modal run deploy/modal/worker.py::probe_youtube_pot --url <youtube-url>`).
# Runs yt-dlp -v --skip-download on the PROD image with the SAME cookies + bgutil PO-token path the
# real download uses, prints the PO-token markers + any bot-gate, so we can verify POT works and how
# stable it is from Modal's DC-IP WITHOUT running the whole pipeline. _SECRET gives R2 creds.
@app.function(secrets=[_SECRET], timeout=300, serialized=True)
def probe_youtube_pot(url: str = "https://www.youtube.com/watch?v=Ks-_Mh1QhMc") -> None:
    """Probe: does yt-dlp extract the video info (cookies + POT) from a Modal DC-IP, or bot-gate?"""
    import subprocess
    import sys
    import tempfile
    from pathlib import Path

    if "/root" not in sys.path:
        sys.path.insert(0, "/root")
    from app import ytdlp_cookies
    from app.config import get_settings

    s = get_settings()
    tmp = Path(tempfile.gettempdir()) / "probe_cookies.txt"
    has_cookies = ytdlp_cookies.pull_cookies(tmp)
    cmd = ["yt-dlp", "-v", "--skip-download", "--no-playlist", "--remote-components", "ejs:github"]
    if has_cookies:
        cmd += ["--cookies", str(tmp)]
    if s.ytdlp_pot_server_home:
        cmd += ["--extractor-args", f"youtubepot-bgutilscript:server_home={s.ytdlp_pot_server_home}"]
    cmd.append(url)
    print(f"[probe] cookies={has_cookies} pot={bool(s.ytdlp_pot_server_home)} url={url}")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    markers = (
        "PO Token", "[pot", "Retrieved", "Sign in to confirm", "not a bot", "ERROR:",
        "Forbidden", "HTTP Error 4", "429", "n challenge", "Some formats may be missing",
    )
    for line in (proc.stdout + "\n" + proc.stderr).splitlines():
        if any(m in line for m in markers):
            print("  | " + line.strip())
    verdict = "OK (info extracted -> download would work)" if proc.returncode == 0 else "FAILED"
    print(f"[probe] exit={proc.returncode} -> {verdict}")
