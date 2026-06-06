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
