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

# config.py → parents: [0]=app [1]=worker [2]=services [3]=<repo root>
_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


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

    # pipeline tuning
    max_source_minutes: int = 90
    clip_min_sec: int = 15
    clip_max_sec: int = 60
    caption_max_words_per_group: int = 5
    max_clips: int = 8  # сколько кандидатов отдавать (юзер выберет из них в UI)
    # reframe: auto = лицо→fill(кроп), нет лица→fit(блюр-рамки, ничего не режет);
    #          fill = всегда кроп; fit = всегда весь кадр в рамках.
    reframe_mode: Literal["auto", "fill", "fit"] = "auto"
    # active-speaker наведение (на ГОВОРЯЩЕЕ лицо, не крупнейшее). Требует asd-экстру (torch).
    # off → cut-aware largest-face (D2). reframe_speaker_crop_scale — тюнинг кадра под MediaPipe.
    reframe_speaker: bool = False
    reframe_speaker_crop_scale: float = 0.55
    # умная статика (гасит «флеши»): порог детекта склеек (выше → меньше ложных) +
    # dead-zone (окно НЕ двигаем, пока центр не уехал > доли ширины → держим кадр через склейки).
    reframe_cut_threshold: float = 0.4
    reframe_dead_zone: float = 0.12

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
