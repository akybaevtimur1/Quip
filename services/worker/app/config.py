"""Конфиг воркера (pydantic-settings). Fail-fast: нет ключа выбранного провайдера → падаем.

Читает ``.env`` из корня репо (абсолютный путь, не зависит от cwd) + OS-переменные
(они приоритетнее). ``get_settings()`` ленив и закэширован — валидация срабатывает при
первом обращении (вход в стадию), а не при импорте, чтобы unit-тесты и /healthz жили
без ключей.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Cost guard: a moving "…-latest" alias OR any gemini-3* can silently jump to Gemini 3.x Flash
# (~×10 the LLM cost). We refuse those and pin to this stable, cheap model. See pin_llm_model.
_PINNED_LLM_MODEL = "gemini-2.5-flash"


def pin_llm_model(v: str) -> str:
    """Refuse a Gemini-3 / moving -latest model id → pin to gemini-2.5-flash. Prod
    LLM_MODEL=``gemini-flash-latest`` now resolves to gemini-3.5-flash (~×10 cost) — coerce it.
    NOT a silent fallback (rule #8): the coercion is logged to stderr."""
    low = v.strip().lower()
    if low.endswith("-latest") or low.startswith("gemini-3") or "gemini-3" in low:
        import sys

        print(
            f"[config] cost guard: LLM_MODEL={v!r} → {_PINNED_LLM_MODEL!r} (no Gemini-3 / -latest)",
            file=sys.stderr,
        )
        return _PINNED_LLM_MODEL
    return v


# config.py → parents: [0]=app [1]=worker [2]=services [3]=<repo root>. На Modal пакет в
# /root/app (мельче) → parents[3] нет; .env там не нужен (секреты из env). Берём parents[3]
# если есть, иначе любой предок → .env не найдётся, bootstrap скипнет.
_parents = Path(__file__).resolve().parents
_ENV_FILE = (_parents[3] if len(_parents) > 3 else _parents[-1]) / ".env"


class Settings(BaseSettings):
    """Все настройки воркера. Лишние переменные из .env игнорируются (extra=ignore)."""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # transcription
    transcription_provider: Literal["deepgram", "assemblyai"] = "deepgram"
    deepgram_api_key: str | None = None
    deepgram_model: str = "nova-3"
    assemblyai_api_key: str | None = None

    # llm (этап D, выбор моментов). Провайдер swappable; сейчас Gemini (нет Anthropic-ключа).
    llm_provider: str = "gemini"
    gemini_api_key: str | None = None
    anthropic_api_key: str | None = None
    # ПИН конкретной версии (НЕ -latest): -latest может уехать на Gemini 3.x Flash с выходом
    # ~$9/1M = ×10 к стоимости LLM молча. 2.5-flash стабильна на платном ключе, дёшева.
    llm_model: str = "gemini-2.5-flash"
    llm_max_output_tokens: int = 16000

    @field_validator("llm_model", mode="after")
    @classmethod
    def _pin_llm_model(cls, v: str) -> str:
        return pin_llm_model(v)

    # download: куки для обхода YouTube bot-защиты.
    # browser: "chrome" | "firefox" | "edge" | "" (пусто = не использовать).
    # Chrome 127+ ломает DPAPI → используй firefox/edge или экспортируй cookies.txt.
    # file: абсолютный путь к cookies.txt (Netscape-формат). Приоритет над browser.
    ytdlp_cookies_browser: str = "edge"
    ytdlp_cookies_file: str = ""
    # R2 key для САМО-РОТИРУЮЩЕГОСЯ cookie-jar (boevoy/Modal). yt-dlp переписывает --cookies
    # файл свежей сессией ПОСЛЕ каждого скачивания; на read-only/эфемерном Modal ротация
    # терялась бы → храним jar в R2 и пушим обратно (app.ytdlp_cookies). Активен ТОЛЬКО при
    # STORAGE_BACKEND=r2 (см. cookies_enabled); локально остаётся ytdlp_cookies_file/browser.
    ytdlp_cookies_r2_key: str = "internal/ytdlp_cookies.txt"
    # Будущий рычаг надёжности YouTube-скачивания: прокси (обход DC-IP бот-гейта). Пусто =
    # без прокси = $0 (дефолт, OFF). Формат yt-dlp --proxy: "http://host:port" / "socks5://...".
    # Когда заполнен — stage0.download_youtube добавляет "--proxy <url>". Ставим ВЫКЛ.
    ytdlp_proxy: str = ""
    # Free proxy pool for YouTube download reliability (IP rotation). Pool is fetched from
    # proxyscrape.com, tested against YouTube, and persisted in R2. Only active in cloud mode
    # (STORAGE_BACKEND=r2). Empty pool → single-proxy or no-proxy fallback (same as before).
    ytdlp_proxy_pool_r2_key: str = "internal/ytdlp_proxy_pool.json"
    ytdlp_proxy_pool_min_size: int = 3  # refresh pool when fewer than this remain in R2
    # YouTube player client(s) for yt-dlp (comma-separated, tried in order). "tv,android_vr" pass
    # the DC-IP bot-gate WITHOUT a GVS PO token (and still honor cookies) → removes the flaky cold
    # bgutil-POT dependency for most videos. Empty = yt-dlp default (env YTDLP_PLAYER_CLIENT).
    ytdlp_player_client: str = "tv,android_vr"
    # bgutil PO-token (Proof-of-Origin) provider, SCRIPT mode. Layered ON TOP of cookies: cookies
    # authenticate the session, the PO token attests proof-of-origin of the player request —
    # YouTube's DC-IP bot-gate checks both. When set, stage0.build_youtube_cmd appends
    # --extractor-args "youtubepot-bgutilscript:server_home=<path>". The path is the bgutil
    # `server/` dir built into the Modal image (deploy/modal/worker.py sets YTDLP_POT_SERVER_HOME
    # to /opt/bgutil-ytdlp-pot-provider/server). Empty (default) = OFF → no POT arg → unchanged
    # behavior for local dev (the provider is not built locally).
    ytdlp_pot_server_home: str = ""

    # pipeline tuning
    # NB: потолок длины исходника НЕ здесь — он в billing.MAX_VIDEO_MINUTES (stage0._check_limits).
    # Раньше тут был мёртвый max_source_minutes=90, который никто не читал и который вводил
    # в заблуждение (реальный лимит = 180). Удалён, чтобы не было двух «источников правды».
    clip_min_sec: int = 20
    clip_max_sec: int = 60
    # W1: хвостовой паддинг конца клипа (сек) — тишина для чистого лупа вертикального шортса.
    clip_tail_pad_sec: float = 0.3
    caption_max_words_per_group: int = 5
    max_clips: int = 12  # D1: дефолт кандидатов (был 8 — скупо для длинных видео); UI Auto шлёт 30

    # transcript cache (content-addressed, data/_cache/transcripts/)
    transcript_cache_enabled: bool = True
    transcript_cache_max_entries: int = 200  # LRU cap by mtime
    transcript_cache_max_age_days: float = 60.0  # TTL for cache entries
    # reframe: auto = лицо→fill(кроп), нет лица→fit(блюр-рамки, ничего не режет);
    #          fill = всегда кроп; fit = всегда весь кадр в рамках.
    reframe_mode: Literal["auto", "fill", "fit"] = "auto"
    reframe_speaker_crop_scale: float = 0.55
    # движок рендера: A = ffmpeg piecewise expr (быстрый); B = cv2 per-frame (точный).
    reframe_engine: str = "A"
    # ASD требует 25fps (модель обучена на 25fps; выше = точнее/медленнее).
    reframe_face_fps: float = 25.0
    reframe_smoothing: float = 0.15  # exponential smoothing коэф (0=без; 1=нет сглаж.)
    # анти-флеш/СТРОБ: регион < min_hold НЕ переключает режим, поглощается предыдущим (гасит
    # рапид-монтаж). 1.5 (ВЕРНУЛ с 0.8): на реальном 25fps-видео 0.8 пускал короткие шоты →
    # режим скакал fill↔fit = СТРОБ («флеши» на 25fps, где grid-флеш в принципе невозможен).
    # Восстановление коротких реакционных резов под tight теперь делает ручной «Split here» в
    # редакторе, поэтому min_hold снова высокий (анти-строб важнее авто-toggleable короткого шота).
    reframe_min_hold_sec: float = 1.5
    reframe_wide_ratio: float = 0.5  # editor: wide_spread_min для resolve_regions
    # PySceneDetect ContentDetector (~27) + ASD порог говорения.
    reframe_scene_threshold: float = 27.0
    # min_scene_len ContentDetector в СЕКУНДАХ → нативные кадры (round(fps*sec), пол 2). Без этого
    # библиотека берёт дефолт 15 кадров (0.5с@30fps) + FlashFilter.MERGE. 0.4 (было 0.25): ловит
    # реальный ~1с реакционный рез, но душит саб-0.4с микро-резы, которые плодили лишние шоты →
    # churn режима/строб. Это фильтр ДЕТЕКЦИИ — границы остаются на реальных нативных склейках.
    reframe_min_scene_sec: float = 0.4
    reframe_speak_threshold: float = 0.0  # ниже порога → фолбэк на largest-face
    # ГИБРИД (фаундер): на широком плане, если кто-то говорит с speak ≥ этого → кропим спикера
    # (fill), а не fit. Шкала ASD speak ≈ [-2..+1]; 0.3 = «явно говорит». Ниже → split/fit.
    reframe_wide_speak_min: float = 0.3
    # split-screen УДАЛЁН из MVP (2026-06-24): авто НИКОГДА не выбирает split — любой «не одно
    # лицо» шот → fit (wide). Флаг оставлен = False (выкл) для совместимости сигнатур планировщиков;
    # UI-опции split нет; легаси split (persist/override) коэрсится в fit (editor/reframe_cache).
    reframe_split_enabled: bool = False
    # perf (#2): при ОДНОЙ дорожке лиц пропускать дорогой ASD (crop+torch) — говорящий
    # однозначен, скор не влияет на регионы (см. stage3_speaker.should_score_asd). Kill-switch:
    # REFRAME_SKIP_ASD_SINGLE_TRACK=false → всегда считать ASD (прежнее поведение, мгновенный
    # откат без передеплоя кода — Modal подхватит env при следующем контейнере).
    reframe_skip_asd_single_track: bool = True

    # billing / payments (P1). Все опциональны — гейт квоты и вебхук Lemon активны
    # ТОЛЬКО при заполнении (нужны Supabase + Lemon у фаундера). По умолчанию инертны →
    # пайплайн не трогается. См. docs/SUPABASE_SETUP.md.
    billing_enabled: bool = False  # включить гейт квоты в create_job (402)
    polar_webhook_secret: str = ""  # Standard Webhooks секрет Polar.sh (whsec_...)
    polar_product_starter: str = ""  # Polar product_id → план "starter"
    polar_product_pro: str = ""  # Polar product_id → план "pro"
    supabase_url: str = ""
    supabase_service_role_key: str = ""  # 🔴 ТОЛЬКО сервер; пишет profiles.plan/usage_events

    # ── облачный стейт + хранилище (boevoy / Modal). Инертны без заполнения. ──
    # storage_backend=local → клип на диске, отдаётся воркером на /media (dev, Phase 0).
    # storage_backend=r2    → клип льётся в Cloudflare R2, video_url = публичный CDN / presigned.
    storage_backend: Literal["local", "r2"] = "local"
    r2_account_id: str = ""  # Cloudflare account id (часть endpoint)
    r2_endpoint: str = ""  # https://<account_id>.r2.cloudflarestorage.com
    r2_access_key_id: str = ""  # 🔴
    r2_secret_access_key: str = ""  # 🔴
    r2_bucket: str = "quip"
    # публичный базовый URL клипов (r2.dev managed domain или кастомный). Пусто →
    # storage.py отдаёт presigned GET URL (работает на голых R2-ключах, без публичного бакета).
    r2_public_url: str = ""
    signed_url_ttl: int = 604800  # presigned GET TTL, сек (R2 максимум = 7 дней)
    # ── preview-прокси (лёгкий source для редактора: быстрая загрузка, H.264, faststart) ──
    # Полный source.mp4 (1080p, 50-100МБ, иногда AV1 = софт-декод) грузился в редакторе долго.
    # preview.mp4 = ≤preview_height H.264 crf preview_crf → пара МБ, hw-декод. Рендер — из source
    # (качество не падает). preview_height клампится сверху высотой источника (без апскейла).
    preview_height: int = 720
    preview_crf: int = 30
    # job-стейт через psycopg-пулер (опц.). Воркер по умолчанию пишет стейт через PostgREST
    # (см. app/cloud_state.py) — этот URL НЕ обязателен. Оставлен для будущего psycopg-пути.
    supabase_db_url: str = ""

    @model_validator(mode="after")
    def _require_selected_provider_key(self) -> Self:
        if self.transcription_provider == "deepgram" and not self.deepgram_api_key:
            raise ValueError("DEEPGRAM_API_KEY is required when TRANSCRIPTION_PROVIDER=deepgram")
        if self.transcription_provider == "assemblyai" and not self.assemblyai_api_key:
            raise ValueError(
                "ASSEMBLYAI_API_KEY is required when TRANSCRIPTION_PROVIDER=assemblyai"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Закэшированный синглтон настроек. Бросает ValidationError при отсутствии ключа."""
    return Settings()


def bootstrap_env() -> None:
    """Загрузить ``.env`` в ``os.environ`` (override=False) при ЛОКАЛЬНОМ запуске воркера.

    Гейты auth/billing (``app.auth``/``app.supa``/``_billing_enabled``) читают ``os.environ``
    напрямую (чтобы unit-тесты держали dual-mode через monkeypatch). В проде env-переменные
    ставит платформа (Modal/Vercel); локально они живут в ``.env`` → этот мост активирует
    JWT-гейт и BILLING из ``.env`` как в проде. НЕ вызывать под pytest (main.py делает guard).
    """
    if _ENV_FILE.exists():
        from dotenv import load_dotenv

        load_dotenv(_ENV_FILE, override=False)
