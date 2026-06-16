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

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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
    llm_model: str = "gemini-flash-latest"
    llm_max_output_tokens: int = 16000

    # download: куки для обхода YouTube bot-защиты.
    # browser: "chrome" | "firefox" | "edge" | "" (пусто = не использовать).
    # Chrome 127+ ломает DPAPI → используй firefox/edge или экспортируй cookies.txt.
    # file: абсолютный путь к cookies.txt (Netscape-формат). Приоритет над browser.
    ytdlp_cookies_browser: str = "edge"
    ytdlp_cookies_file: str = ""

    # pipeline tuning
    # NB: потолок длины исходника НЕ здесь — он в billing.MAX_VIDEO_MINUTES (stage0._check_limits).
    # Раньше тут был мёртвый max_source_minutes=90, который никто не читал и который вводил
    # в заблуждение (реальный лимит = 180). Удалён, чтобы не было двух «источников правды».
    clip_min_sec: int = 15
    clip_max_sec: int = 60
    # W1: хвостовой паддинг конца клипа (сек) — тишина для чистого лупа вертикального шортса.
    clip_tail_pad_sec: float = 0.3
    caption_max_words_per_group: int = 5
    max_clips: int = 8  # сколько кандидатов отдавать (юзер выберет из них в UI)

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
    # анти-флеш: регион < min_hold НЕ переключает режим, поглощается предыдущим.
    reframe_min_hold_sec: float = 1.5
    reframe_wide_ratio: float = 0.5  # editor: wide_spread_min для resolve_regions
    # PySceneDetect ContentDetector (~27) + ASD порог говорения.
    reframe_scene_threshold: float = 27.0
    reframe_speak_threshold: float = 0.0  # ниже порога → фолбэк на largest-face
    # split-screen (v3): ровно 2 устойчивых разнесённых лица → верх/низ (вместо fit);
    # 3+ лиц / нестабильные треки → fit как раньше. false = всегда fit (старое поведение).
    reframe_split_enabled: bool = True

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
            raise ValueError("DEEPGRAM_API_KEY обязателен при TRANSCRIPTION_PROVIDER=deepgram")
        if self.transcription_provider == "assemblyai" and not self.assemblyai_api_key:
            raise ValueError("ASSEMBLYAI_API_KEY обязателен при TRANSCRIPTION_PROVIDER=assemblyai")
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
