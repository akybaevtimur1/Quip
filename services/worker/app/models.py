"""ЕДИНЫЙ ИСТОЧНИК ТИПОВ ClipFlow (Pydantic).

Здесь — все контракты данных. Из этого файла codegen-цепочка генерит JSON Schema
(`export_schema.py` → `packages/shared/contract.json`) и затем TypeScript
(`packages/shared/src/types.ts`). НИКОГДА не пишем TS руками и не дублируем типы.

Инварианты (см. план §4.1):
- все времена — секунды (float), абсолютные от начала source;
- `Transcript.words` отсортированы по `start` (обеспечивает провайдер транскрипции);
- Deepgram отдаёт секунды; AssemblyAI — мс → нормализуем в секунды на входе провайдера.

Две группы моделей:
- ВНУТРЕННИЕ (пайплайн): Word, Transcript, Segment, CropWindow, Clip.
- WIRE (API web↔worker, §4.3): Job, ClipOut, Metrics + enums JobStatus/SourceKind/ClipType.
"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

# ─────────────────────────── enums (общие web/worker) ───────────────────────────


class ClipType(StrEnum):
    """Тип момента, выбранного LLM (объяснимость + цвет чипа в UI)."""

    hook = "hook"
    emotional_peak = "emotional_peak"
    complete_thought = "complete_thought"
    strong_quote = "strong_quote"


class JobStatus(StrEnum):
    """Состояние задачи. Им же размечаем `stage` (Phase 0: stage зеркалит status)."""

    queued = "queued"
    downloading = "downloading"
    transcribing = "transcribing"
    selecting = "selecting"
    rendering = "rendering"
    done = "done"
    failed = "failed"


class SourceKind(StrEnum):
    """Откуда исходник: ссылка YouTube или загруженный файл."""

    youtube = "youtube"
    upload = "upload"


# ─────────────────────────── внутренние модели пайплайна ───────────────────────────


class Word(BaseModel):
    """Слово с word-level таймингами (фундамент всего: субтитры, trim, маппинг)."""

    text: str  # уже пунктуированное/капитализированное (для субтитров)
    start: float  # секунды, абсолютные от начала source
    end: float  # секунды
    confidence: float | None = None


class Transcript(BaseModel):
    """Нормализованный транскрипт. `words` отсортированы по `start`."""

    language: str
    duration: float  # длительность source, секунды
    words: list[Word]


class Segment(BaseModel):
    """Выбранный момент (границы снэпнуты к словам). `reason` — ПОЧЕМУ, 1-2 предложения."""

    start: float  # секунды, снэп к границе слова
    end: float  # секунды, снэп к границе слова
    reason: str
    score: float = Field(ge=0, le=1)
    type: ClipType


class CropWindow(BaseModel):
    """Окно кропа 9:16 в пиксельных координатах source. Phase 0: одно static-окно на клип."""

    t: float  # таймштамп (с), на котором применяется окно
    x: int  # левый-верхний угол в пикселях source
    y: int
    w: int  # размер кропа в пикселях source (9:16)
    h: int


class Clip(BaseModel):
    """Внутреннее представление готового клипа (пути к артефактам + экономика)."""

    id: str
    segment: Segment
    crop: list[CropWindow]  # Phase 0: одно окно
    captions_ass_path: str
    output_path: str  # финальный 9:16 mp4
    cost_usd: float
    latency_s: float


# ─────────────────────────── WIRE-модели (API web↔worker, §4.3) ───────────────────────────


class ClipOut(BaseModel):
    """Клип в ответе API. `start/end` — в координатах source (фундамент clip↔source).

    `words[]` присутствует уже в Phase 0 (фундамент trim-редактора), UI его игнорирует.
    """

    id: str
    start: float  # секунды в координатах source
    end: float
    duration: float  # секунды
    reason: str  # пояснение «почему этот момент» (explainability)
    type: ClipType
    score: float = Field(ge=0, le=1)
    video_url: str
    thumbnail_url: str | None = None
    transcript: str  # сниппет текста клипа
    words: list[Word]


class Metrics(BaseModel):
    """Экономика/латентность прогона (на виду в UI)."""

    cost_usd: float
    duration_sec: float  # длительность source
    elapsed_sec: float  # время до готовности


class Job(BaseModel):
    """Состояние задачи целиком — ответ `GET /jobs/{id}` (§4.3)."""

    id: str
    status: JobStatus
    stage: JobStatus  # Phase 0: зеркалит status
    progress: int = Field(ge=0, le=100)
    source_kind: SourceKind
    error: str | None = None
    clips: list[ClipOut] = Field(default_factory=list)
    metrics: Metrics | None = None


# ─────────────────────────── EDITOR-модели (слой композиции, спека §3) ───────────────────────────


class SourceInterval(BaseModel):
    """Один оставленный кусок исходника. Интервалы упорядочены по CLIP-порядку."""

    source_start: float  # сек в координатах source
    source_end: float  # сек; source_end > source_start


class CropOverride(BaseModel):
    """Ручной кроп на диапазон source — поверх авто-reframe (MVP: применяется per-интервал)."""

    source_start: float
    source_end: float
    mode: str  # "fill" | "fit" | "split"
    center: float | None = None  # центр кропа [0..1] для fill / верхней половины split
    center_b: float | None = None  # второй центр [0..1] для mode="split" (нижняя половина)


class CaptionStyle(BaseModel):
    """Стиль субтитров. Компилируется в ASS (рендер) и в CSS (превью) из одной модели."""

    font: str = "Montserrat"
    size: int = 90
    color: str = "#FFFFFF"  # основной цвет текста (#RRGGBB)
    outline_color: str = "#000000"
    outline_w: int = 6
    shadow: int = 2
    box_color: str | None = None  # фон-плашка; None = без плашки
    box_opacity: float = Field(default=0.0, ge=0.0, le=1.0)
    box_radius: int = 0
    margin_v: int = 260  # позиция от низа (ASS MarginV)
    alignment: int = 2  # ASS alignment (2 = низ-центр)
    uppercase: bool = True
    emphasis_color: str | None = (
        None  # цвет «ударных» слов (None = не красим); см. CaptionReply.emphasis_refs
    )


class HighlightStyle(BaseModel):
    """Караоке-подсветка активного слова. None в треке = караоке выключено."""

    color: str = "#FFE000"
    scale: float = 1.0  # 1.0 = без увеличения активного слова
    box: bool = False  # True = активное слово в залитой плашке; False = перекраска текста
    animation: Literal["none", "karaoke_fill", "pop", "bounce", "punch", "fade"] = "karaoke_fill"


class CaptionReply(BaseModel):
    """Одна реплика субтитра (чанк 3–5 слов)."""

    word_refs: list[int]  # индексы в transcript.words (тайминги для караоке/trim)
    text_override: str | None = None  # если юзер правил текст реплики
    hidden: bool = False  # скрыть субтитр, видео не трогая
    emphasis_refs: list[int] = Field(default_factory=list)  # подмн-во word_refs: «ударные» слова


class CaptionTrack(BaseModel):
    """Трек субтитров клипа: стиль + караоке + реплики."""

    style: CaptionStyle
    highlight: HighlightStyle | None = None
    replies: list[CaptionReply] = Field(default_factory=list)


class ClipEdit(BaseModel):
    """РЕЦЕПТ клипа — не-деструктивный edit-state. Версионируется (optimistic-lock)."""

    id: str  # = clip_id (clip_01…)
    version: int = 1
    source_intervals: list[SourceInterval]
    captions: CaptionTrack
    reframe_overrides: list[CropOverride] = Field(default_factory=list)
    aspect: str = "9:16"


class CaptionPreset(BaseModel):
    """Именованный пресет стиля субтитров (мини brand kit, спека §9)."""

    id: str
    name: str
    style: CaptionStyle
    highlight: HighlightStyle | None = None


# ─────────────────────────── TIMELINE-модели (редактор v2) ───────────────────────────


class TimelineSegment(BaseModel):
    """Кандидат-момент ИИ на таймлайне (маркер). `clip_id`=None, если момент не стал клипом."""

    clip_id: str | None = None
    start: float  # сек в координатах source
    end: float
    type: ClipType
    score: float = Field(ge=0, le=1)
    reason: str


class TimelineData(BaseModel):
    """Данные таймлайн-редактора: длительность + ВСЕ кандидаты ИИ + пословный транскрипт.

    Собирается из готовых segments.json + transcript.json (без новых ИИ-вызовов).
    `words` — для hover-подсказок «что тут происходит».
    """

    duration: float  # длительность source, секунды
    segments: list[TimelineSegment]
    words: list[Word]


# ─────────────────────────── AI-карта видео (редактор v3) ───────────────────────────


class Chapter(BaseModel):
    """Глава AI-карты видео (источник-время, секунды). Главы покрывают видео непрерывно."""

    start: float
    end: float
    title: str  # короткое название момента (язык транскрипта)
    summary: str  # 1-2 предложения, что происходит


class ChaptersData(BaseModel):
    """Статус+результат генерации AI-карты (кэш data/<job>/chapters.json)."""

    status: Literal["pending", "done", "failed"]
    chapters: list[Chapter] = Field(default_factory=list)
    error: str | None = None  # причина при status="failed" (правило №8 — не глотаем)
