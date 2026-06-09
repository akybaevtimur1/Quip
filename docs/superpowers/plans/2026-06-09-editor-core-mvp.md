# Editor Core (MVP) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Превратить batch-конвейер ClipFlow в не-деструктивный редактор: каждый клип становится редактируемым «рецептом» (`ClipEdit`) над исходником, который можно тримить/расширять/перенацеливать кроп/перестилизовать субтитры и пере-рендерить — без повторных вызовов Deepgram/Gemini.

**Architecture:** Три слоя — АНАЛИЗ (транскрипт + reframe по диапазону source, кэш, $0), ВЫБОР ИИ (один раз), КОМПОЗИЦИЯ (`ClipEdit` = таймлайн `SourceInterval` + `CaptionTrack` + `CropOverride`). Правки = PURE-трансформы над `ClipEdit`; рендер собирает mp4 из edit-state одним проходом ffmpeg (мульти-интервальный concat, бесшовное аудио). Спека: `docs/superpowers/specs/2026-06-09-editor-core-design.md`.

**Tech Stack:** Python 3.12 / FastAPI / pydantic v2 / SQLite / ffmpeg (libx264, ASS/libass, filter_complex) / MediaPipe / pytest. Codegen TS-типов из `app/models.py` через `just types`.

---

## Соглашения для исполнителя (прочитать ПЕРВЫМ)

- **Среда — Windows + PowerShell.** В КАЖДОМ PowerShell-вызове обновляй PATH:
  ```powershell
  $env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
  ```
- Воркер запускается из `C:\Users\user\Desktop\ClipClow\services\worker`. Команды `uv run …`, `pytest`, `just` — оттуда (кроме `just`, который из корня; см. HANDOFF §3).
- **Тест-первым на любой pure-логике** (правило CLAUDE.md). Шаг не готов, пока DoD не зелёный с показанным выводом.
- **Гейт перед каждым коммитом:** из корня репо `just check` (lint + mypy + tsc + test-unit + anti-drift) ДОЛЖЕН быть зелёным. Держать `uv sync --extra asd` (иначе mypy падает на `app/asd/scorer.py`).
- **После изменения `app/models.py`** — `just types` (codegen контракта). НЕ править `packages/shared/*` руками.
- Коммиты — conventional commits, из PowerShell (кириллица в сообщении → писать в файл UTF-8 и `git commit -F`, см. HANDOFF §9). Завершать сообщение строкой:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
- **Никаких `except: pass` и тихих фолбэков.** Ошибка стадии → `JobError` (`app/errors.py`).
- Тесты кладём в `services/worker/tests/unit/` (pytest, как существующие 180 тестов).

---

## File Structure (что создаём / меняем)

**Новый пакет `services/worker/app/editor/`** (слой композиции — pure-логика + персистентность):
- `editor/__init__.py` — пустой маркер пакета.
- `editor/timemap.py` — `ClipTimeMap` (clip↔source mapping, PURE). [E0]
- `editor/replies.py` — `rebuild_replies`, `default_caption_track` (группировка слов в реплики, PURE). [E0]
- `editor/defaults.py` — `default_clip_edit(segment, words)` (PURE). [E0]
- `editor/reframe_cache.py` — `RawReframe`, `analyze_source_range` (I/O+кэш), `resolve_regions` (PURE). [E1]
- `editor/captions_v2.py` — `compile_ass(track, words, cmap)` (CaptionTrack→ASS с `\k`, PURE). [E3]
- `editor/ops.py` — `apply_trim`/`add_section`/`apply_extend`/`set_crop_override` (PURE). [E4]
- `editor/store.py` — персистентность `ClipEdit` (SQLite + edit.json зеркало). [E4]
- `editor/presets.py` — `apply_preset` (PURE) + чтение/запись пресетов. [E5]

**Изменяем существующие файлы:**
- `app/models.py` — +контракты редактора (`SourceInterval`, `CropOverride`, `CaptionStyle`, `HighlightStyle`, `CaptionReply`, `CaptionTrack`, `ClipEdit`). [E0]
- `app/pipeline/stage5_render.py` — +`build_timeline_filter` (PURE) + `render_timeline` (I/O), single-interval fast-path. [E2]
- `app/db.py` — +таблица `clip_edits` + CRUD. [E4]
- `app/main.py` — +editor-эндпоинты (GET/PATCH edit, op-эндпоинты, render, analysis). [E4]
- `app/tasks.py` — +`render_clip_edit_job` (фон-рендер одного клипа из edit-state). [E4]
- `app/run.py` — после select писать дефолт-`ClipEdit` на каждый сегмент. [E4]

**Тесты:** `tests/unit/test_editor_models.py`, `test_timemap.py`, `test_replies.py`, `test_defaults.py`, `test_reframe_resolve.py`, `test_timeline_filter.py`, `test_captions_v2.py`, `test_editor_ops.py`, `test_presets.py`, `test_editor_store.py`.

---

## Phase E0 — Контракты + тайм-маппинг + дефолты

**Результат фазы:** модель `ClipEdit` существует, генерится в TS; есть PURE clip↔source mapping и сборка дефолтного `ClipEdit` из сегмента. Всё под unit-тестами.

### Task E0.1: Контракты редактора в models.py

**Files:**
- Modify: `services/worker/app/models.py` (добавить в конец файла, после `Job`)
- Test: `services/worker/tests/unit/test_editor_models.py`

- [ ] **Step 1: Написать падающий тест**

```python
# tests/unit/test_editor_models.py
from app.models import (
    CaptionReply, CaptionStyle, CaptionTrack, ClipEdit, CropOverride,
    HighlightStyle, SourceInterval,
)


def test_clip_edit_defaults():
    edit = ClipEdit(
        id="clip_01",
        source_intervals=[SourceInterval(source_start=10.0, source_end=25.0)],
        captions=CaptionTrack(style=CaptionStyle(), highlight=HighlightStyle(), replies=[]),
    )
    assert edit.version == 1
    assert edit.aspect == "9:16"
    assert edit.reframe_overrides == []
    assert edit.source_intervals[0].source_end == 25.0
    assert edit.captions.style.font == "Montserrat"
    assert edit.captions.style.uppercase is True
    assert edit.captions.highlight.color == "#FFE000"


def test_caption_reply_and_override():
    r = CaptionReply(word_refs=[3, 4, 5])
    assert r.text_override is None and r.hidden is False
    ov = CropOverride(source_start=1.0, source_end=2.0, mode="fill", center=0.7)
    assert ov.mode == "fill" and ov.center == 0.7
```

- [ ] **Step 2: Прогнать тест — убедиться, что падает**

Run (из `services/worker`): `uv run pytest tests/unit/test_editor_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'ClipEdit'`.

- [ ] **Step 3: Добавить контракты в models.py**

```python
# В конец app/models.py (после класса Job)

# ─────────────────────────── EDITOR-модели (слой композиции, спека §3) ───────────────────────────


class SourceInterval(BaseModel):
    """Один оставленный кусок исходника. Интервалы упорядочены по CLIP-порядку."""

    source_start: float  # сек в координатах source
    source_end: float  # сек; source_end > source_start


class CropOverride(BaseModel):
    """Ручной кроп на диапазон source — поверх авто-reframe (MVP: применяется per-интервал)."""

    source_start: float
    source_end: float
    mode: str  # "fill" | "fit"
    center: float | None = None  # центр кропа [0..1] для fill; None = центр кадра


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


class HighlightStyle(BaseModel):
    """Караоке-подсветка активного слова. None в треке = караоке выключено."""

    color: str = "#FFE000"
    scale: float = 1.0  # 1.0 = без увеличения активного слова


class CaptionReply(BaseModel):
    """Одна реплика субтитра (чанк 3–5 слов)."""

    word_refs: list[int]  # индексы в transcript.words (тайминги для караоке/trim)
    text_override: str | None = None  # если юзер правил текст реплики
    hidden: bool = False  # скрыть субтитр, видео не трогая


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
```

- [ ] **Step 4: Прогнать тест — убедиться, что проходит**

Run: `uv run pytest tests/unit/test_editor_models.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Регенерировать TS-типы и проверить идемпотентность**

Run (из корня репо, PowerShell с PATH-refresh): `just types`
Expected: `packages/shared/src/types.ts` и `contract.json` обновлены (появились `ClipEdit`, `CaptionTrack` и т.д.). Повторный `just types` → нет diff (`git diff --exit-code packages/shared` чисто).

- [ ] **Step 6: Коммит**

```
git add services/worker/app/models.py services/worker/tests/unit/test_editor_models.py packages/shared
git commit -F <msg-файл>
# feat(editor): add ClipEdit/CaptionTrack/SourceInterval contracts + codegen
```

---

### Task E0.2: ClipTimeMap (clip↔source mapping)

**Files:**
- Create: `services/worker/app/editor/__init__.py` (пустой)
- Create: `services/worker/app/editor/timemap.py`
- Test: `services/worker/tests/unit/test_timemap.py`

- [ ] **Step 1: Написать падающий тест**

```python
# tests/unit/test_timemap.py
import pytest

from app.editor.timemap import ClipTimeMap
from app.errors import JobError
from app.models import SourceInterval


def _iv(a, b):
    return SourceInterval(source_start=a, source_end=b)


def test_single_interval():
    m = ClipTimeMap([_iv(10.0, 20.0)])
    assert m.clip_duration == 10.0
    assert m.source_to_clip(10.0) == 0.0
    assert m.source_to_clip(15.0) == 5.0
    assert m.source_to_clip(20.0) is None  # полуинтервал [start, end)
    assert m.clip_to_source(0.0) == (0, 10.0)
    assert m.clip_to_source(5.0) == (0, 15.0)
    assert m.interval_clip_band(0) == (0.0, 10.0)


def test_two_intervals_with_gap():
    m = ClipTimeMap([_iv(10.0, 20.0), _iv(30.0, 35.0)])  # дырка 20..30
    assert m.clip_duration == 15.0
    assert m.source_to_clip(19.0) == 9.0
    assert m.source_to_clip(25.0) is None  # в дырке
    assert m.source_to_clip(30.0) == 10.0
    assert m.source_to_clip(34.0) == 14.0
    assert m.clip_to_source(12.0) == (1, 32.0)
    assert m.interval_clip_band(1) == (10.0, 15.0)


def test_add_section_out_of_source_order():
    # интервал из ПОЗЖЕ по source стоит РАНЬШЕ в клипе (add-section)
    m = ClipTimeMap([_iv(30.0, 35.0), _iv(10.0, 20.0)])
    assert m.clip_duration == 15.0
    assert m.source_to_clip(32.0) == 2.0
    assert m.source_to_clip(15.0) == 10.0


def test_empty_raises():
    with pytest.raises(JobError):
        ClipTimeMap([])
```

- [ ] **Step 2: Прогнать — убедиться, что падает**

Run: `uv run pytest tests/unit/test_timemap.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.editor'`.

- [ ] **Step 3: Реализовать ClipTimeMap**

```python
# app/editor/timemap.py
"""Clip-time ↔ source-time mapping (спека §4). ЕДИНАЯ точка таймингов клипа.

Все ошибки «±длина клипа / съехавшие субтитры» живут только здесь. PURE, под тестами.
"""

from __future__ import annotations

from app.errors import JobError
from app.models import SourceInterval

_STAGE = "editor"


class ClipTimeMap:
    """Кусочно-линейное отображение по интервалам (упорядочены по CLIP-порядку).

    clip-полоса k: [C_k, C_k + L_k), где C_k = сумма длин предыдущих, L_k = длина интервала.
    """

    def __init__(self, intervals: list[SourceInterval]) -> None:
        if not intervals:
            raise JobError(_STAGE, "ClipTimeMap: пустой список интервалов")
        self.intervals = list(intervals)
        self.lengths = [max(0.0, iv.source_end - iv.source_start) for iv in intervals]
        self.band_starts: list[float] = []
        acc = 0.0
        for length in self.lengths:
            self.band_starts.append(round(acc, 3))
            acc += length
        self.clip_duration = round(acc, 3)

    def source_to_clip(self, t_src: float) -> float | None:
        """source-время → clip-время; None если t_src в дырке (вне всех интервалов)."""
        for k, iv in enumerate(self.intervals):
            if iv.source_start <= t_src < iv.source_end:
                return round(self.band_starts[k] + (t_src - iv.source_start), 3)
        return None

    def clip_to_source(self, t_clip: float) -> tuple[int, float]:
        """clip-время → (индекс интервала, source-время). Клипуется в [0, clip_duration]."""
        for k, length in enumerate(self.lengths):
            c0 = self.band_starts[k]
            last = k == len(self.lengths) - 1
            if c0 <= t_clip < c0 + length or (last and t_clip <= c0 + length + 1e-6):
                off = min(max(0.0, t_clip - c0), length)
                return k, round(self.intervals[k].source_start + off, 3)
        return 0, round(self.intervals[0].source_start, 3)

    def interval_clip_band(self, k: int) -> tuple[float, float]:
        """(C_k, C_k + L_k) — clip-полоса интервала k (для рендера/субтитров)."""
        return self.band_starts[k], round(self.band_starts[k] + self.lengths[k], 3)
```

- [ ] **Step 4: Прогнать — убедиться, что проходит**

Run: `uv run pytest tests/unit/test_timemap.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Коммит**

```
git add services/worker/app/editor/__init__.py services/worker/app/editor/timemap.py services/worker/tests/unit/test_timemap.py
git commit -F <msg>   # feat(editor): ClipTimeMap clip<->source mapping (pure)
```

---

### Task E0.3: rebuild_replies + default_caption_track

**Files:**
- Create: `services/worker/app/editor/replies.py`
- Test: `services/worker/tests/unit/test_replies.py`

Переиспользуем существующий `group_words_into_chunks` из `app/pipeline/stage4_captions.py`
(он группирует список `Word` по правилам ≤5 слов / пауза>0.4 / длина>2.5 / конец предложения).
`rebuild_replies` отбирает слова, попадающие в интервалы (по source-времени, в clip-порядке),
группирует их и собирает `CaptionReply` с `word_refs` = индексами в `transcript.words`.

- [ ] **Step 1: Написать падающий тест**

```python
# tests/unit/test_replies.py
from app.editor.replies import default_caption_track, rebuild_replies
from app.models import CaptionReply, SourceInterval, Word


def _w(text, start, end):
    return Word(text=text, start=start, end=end)


WORDS = [
    _w("Привет", 0.0, 0.4),
    _w("мир.", 0.4, 0.8),       # конец предложения → разрыв после
    _w("Это", 1.0, 1.2),
    _w("тест", 1.2, 1.6),
    _w("редактора", 1.6, 2.2),
]


def test_rebuild_full_interval_groups_and_refs():
    intervals = [SourceInterval(source_start=0.0, source_end=3.0)]
    replies = rebuild_replies(WORDS, intervals)
    # "Привет мир." заканчивает предложение → отдельная реплика; затем "Это тест редактора"
    assert [r.word_refs for r in replies] == [[0, 1], [2, 3, 4]]


def test_rebuild_drops_words_in_gap():
    # интервал покрывает только слова 2..4 (1.0..2.2); 0,1 вне → выпадают
    intervals = [SourceInterval(source_start=1.0, source_end=3.0)]
    replies = rebuild_replies(WORDS, intervals)
    assert [r.word_refs for r in replies] == [[2, 3, 4]]


def test_rebuild_preserves_text_override_for_unchanged_refs():
    intervals = [SourceInterval(source_start=0.0, source_end=3.0)]
    keep = [CaptionReply(word_refs=[2, 3, 4], text_override="ИЗМЕНЕНО", hidden=True)]
    replies = rebuild_replies(WORDS, intervals, keep=keep)
    edited = next(r for r in replies if r.word_refs == [2, 3, 4])
    assert edited.text_override == "ИЗМЕНЕНО" and edited.hidden is True


def test_default_caption_track_defaults_on():
    track = default_caption_track(WORDS, [SourceInterval(source_start=0.0, source_end=3.0)])
    assert track.style.font == "Montserrat"
    assert track.highlight is not None  # караоке включён по умолчанию
    assert len(track.replies) == 2
```

- [ ] **Step 2: Прогнать — падает**

Run: `uv run pytest tests/unit/test_replies.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.editor.replies'`.

- [ ] **Step 3: Реализовать replies.py**

```python
# app/editor/replies.py
"""Сборка реплик субтитров из слов и интервалов (спека §4.1, §7). PURE.

rebuild_replies — единственное место синхронизации субтитров с интервалами:
структурная правка интервалов → перегруппировать слова в интервалах.
Переиспользует group_words_into_chunks (правила группировки не дублируем).
"""

from __future__ import annotations

from app.models import CaptionReply, CaptionStyle, CaptionTrack, HighlightStyle, SourceInterval, Word
from app.pipeline.stage4_captions import group_words_into_chunks


def rebuild_replies(
    all_words: list[Word],
    intervals: list[SourceInterval],
    *,
    max_words: int = 5,
    max_gap: float = 0.4,
    max_dur: float = 2.5,
    keep: list[CaptionReply] | None = None,
) -> list[CaptionReply]:
    """Перегруппировать слова, попадающие в интервалы (clip-порядок), в реплики.

    word_refs = индексы в all_words. Слова вне интервалов выпадают. keep сохраняет
    text_override/hidden для реплик с НЕизменившимся набором word_refs.
    """
    selected: list[tuple[int, Word]] = []
    for iv in intervals:  # clip-порядок интервалов
        for i, w in enumerate(all_words):  # внутри — по возрастанию (= source-порядок)
            if iv.source_start <= w.start < iv.source_end:
                selected.append((i, w))
    if not selected:
        return []
    chunks = group_words_into_chunks(
        [w for _i, w in selected], max_words=max_words, max_gap=max_gap, max_dur=max_dur
    )
    keyed = {tuple(r.word_refs): r for r in (keep or [])}
    replies: list[CaptionReply] = []
    pos = 0
    for ch in chunks:
        refs = [selected[pos + k][0] for k in range(len(ch.words))]
        pos += len(ch.words)
        prev = keyed.get(tuple(refs))
        replies.append(
            CaptionReply(
                word_refs=refs,
                text_override=prev.text_override if prev else None,
                hidden=prev.hidden if prev else False,
            )
        )
    return replies


def default_caption_track(all_words: list[Word], intervals: list[SourceInterval]) -> CaptionTrack:
    """Дефолтный трек: brand-neutral стиль + караоке ВКЛ + авто-группировка реплик."""
    return CaptionTrack(
        style=CaptionStyle(),
        highlight=HighlightStyle(),
        replies=rebuild_replies(all_words, intervals),
    )
```

- [ ] **Step 4: Прогнать — проходит**

Run: `uv run pytest tests/unit/test_replies.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Коммит**

```
git add services/worker/app/editor/replies.py services/worker/tests/unit/test_replies.py
git commit -F <msg>   # feat(editor): rebuild_replies + default_caption_track (pure, reuses grouping)
```

---

### Task E0.4: default_clip_edit

**Files:**
- Create: `services/worker/app/editor/defaults.py`
- Test: `services/worker/tests/unit/test_defaults.py`

- [ ] **Step 1: Написать падающий тест**

```python
# tests/unit/test_defaults.py
from app.editor.defaults import default_clip_edit
from app.models import Segment, Word


def _w(text, start, end):
    return Word(text=text, start=start, end=end)


def test_default_clip_edit_from_segment():
    words = [_w("Раз", 5.0, 5.3), _w("два", 5.3, 5.6), _w("три.", 5.6, 6.0), _w("Вне", 99.0, 99.4)]
    seg = Segment(start=5.0, end=7.0, reason="хук", score=0.8, type="hook")
    edit = default_clip_edit("clip_01", seg, words)
    assert edit.id == "clip_01"
    assert edit.version == 1
    assert len(edit.source_intervals) == 1
    assert edit.source_intervals[0].source_start == 5.0
    assert edit.source_intervals[0].source_end == 7.0
    assert edit.reframe_overrides == []
    # слово "Вне" (t=99) вне сегмента → не попало в реплики
    all_refs = [i for r in edit.captions.replies for i in r.word_refs]
    assert 3 not in all_refs and all_refs == [0, 1, 2]
```

- [ ] **Step 2: Прогнать — падает**

Run: `uv run pytest tests/unit/test_defaults.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.editor.defaults'`.

- [ ] **Step 3: Реализовать defaults.py**

```python
# app/editor/defaults.py
"""Сборка дефолтного ClipEdit из выбранного сегмента (спека §10). PURE."""

from __future__ import annotations

from app.editor.replies import default_caption_track
from app.models import ClipEdit, Segment, SourceInterval, Word


def default_clip_edit(clip_id: str, segment: Segment, all_words: list[Word]) -> ClipEdit:
    """Сегмент ИИ → дефолтный рецепт: один интервал [start,end], авто-субтитры, без overrides."""
    intervals = [SourceInterval(source_start=segment.start, source_end=segment.end)]
    return ClipEdit(
        id=clip_id,
        version=1,
        source_intervals=intervals,
        captions=default_caption_track(all_words, intervals),
        reframe_overrides=[],
        aspect="9:16",
    )
```

- [ ] **Step 4: Прогнать — проходит**

Run: `uv run pytest tests/unit/test_defaults.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Гейт + коммит**

Run (из корня): `just check`
Expected: всё зелёное (lint + mypy + tsc + tests + anti-drift).

```
git add services/worker/app/editor/defaults.py services/worker/tests/unit/test_defaults.py
git commit -F <msg>   # feat(editor): default_clip_edit from segment (pure)
```

**DoD фазы E0:** `ClipEdit` генерится в TS (`just types` идемпотентен); `ClipTimeMap` покрыт (1/2/дырка/add-section/пусто); `rebuild_replies` (группировка + дырка + keep) и `default_clip_edit` зелёные; `just check` зелёный.

---

## Phase E1 — Reframe-decoupling + кэш анализа

**Результат фазы:** reframe-анализ (лица+склейки) считается для ДИАПАЗОНА исходника и
кэшируется; PURE `resolve_regions` строит регионы на каждый интервал (с учётом ручных
overrides и forced-склеек на границах интервалов). Никаких новых платных вызовов.

Переиспользуем из `app/pipeline/stage3_reframe.py`: `sample_faces_continuous` (I/O),
`detect_cuts` (I/O), `build_shots` (PURE), `build_regions_from_shots` (PURE), `TrackPoint`,
`TrackRegion`. Все они уже возвращают КЛИП-относительные (0-based от `-ss start`) времена →
для диапазона `[s, e]` анализ автоматически interval-relative.

### Task E1.1: RawReframe + resolve_regions (PURE)

**Files:**
- Create: `services/worker/app/editor/reframe_cache.py`
- Test: `services/worker/tests/unit/test_reframe_resolve.py`

- [ ] **Step 1: Написать падающий тест**

```python
# tests/unit/test_reframe_resolve.py
from app.editor.reframe_cache import RawReframe, resolve_regions
from app.models import CropOverride, SourceInterval

SRC_W, SRC_H = 1920, 1080  # crop_w = 607.5→608; crop_w_frac ≈ 0.316


def _faces_centered(n, fps=5.0):
    # n сэмплов: одно центрированное лицо (cx=0.5, ширина 0.2)
    return [(i / fps, [(0.5, 0.2)]) for i in range(n)]


def test_single_fill_interval():
    intervals = [SourceInterval(source_start=10.0, source_end=12.0)]
    raw = [RawReframe(faces=_faces_centered(10), cuts=[])]
    out = resolve_regions(
        intervals, raw, [], src_w=SRC_W, src_h=SRC_H, smoothing=0.15, min_hold_sec=1.5
    )
    assert len(out) == 1
    assert out[0][0].mode == "fill"
    assert out[0][0].points  # есть траектория


def test_no_faces_is_fit():
    intervals = [SourceInterval(source_start=0.0, source_end=2.0)]
    raw = [RawReframe(faces=[(i / 5.0, []) for i in range(10)], cuts=[])]
    out = resolve_regions(
        intervals, raw, [], src_w=SRC_W, src_h=SRC_H, smoothing=0.15, min_hold_sec=1.5
    )
    assert out[0][0].mode == "fit"


def test_override_fit_replaces_interval():
    intervals = [SourceInterval(source_start=10.0, source_end=12.0)]
    raw = [RawReframe(faces=_faces_centered(10), cuts=[])]  # авто было бы fill
    ov = [CropOverride(source_start=10.0, source_end=12.0, mode="fit")]
    out = resolve_regions(
        intervals, raw, ov, src_w=SRC_W, src_h=SRC_H, smoothing=0.15, min_hold_sec=1.5
    )
    assert len(out[0]) == 1 and out[0][0].mode == "fit"


def test_override_fill_center():
    intervals = [SourceInterval(source_start=10.0, source_end=12.0)]
    raw = [RawReframe(faces=[(i / 5.0, []) for i in range(10)], cuts=[])]  # авто было бы fit
    ov = [CropOverride(source_start=10.0, source_end=12.0, mode="fill", center=0.7)]
    out = resolve_regions(
        intervals, raw, ov, src_w=SRC_W, src_h=SRC_H, smoothing=0.15, min_hold_sec=1.5
    )
    assert out[0][0].mode == "fill"
    assert out[0][0].points[0].cx == 0.7


def test_two_intervals_independent_region_lists():
    intervals = [
        SourceInterval(source_start=10.0, source_end=12.0),
        SourceInterval(source_start=30.0, source_end=32.0),
    ]
    raw = [
        RawReframe(faces=_faces_centered(10), cuts=[]),
        RawReframe(faces=_faces_centered(10), cuts=[]),
    ]
    out = resolve_regions(
        intervals, raw, [], src_w=SRC_W, src_h=SRC_H, smoothing=0.15, min_hold_sec=1.5
    )
    assert len(out) == 2  # отдельный список регионов на каждый интервал (граница = forced-cut)
```

- [ ] **Step 2: Прогнать — падает**

Run: `uv run pytest tests/unit/test_reframe_resolve.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.editor.reframe_cache'`.

- [ ] **Step 3: Реализовать RawReframe + resolve_regions (без analyze пока)**

```python
# app/editor/reframe_cache.py
"""Reframe-анализ по диапазону source (кэш) + сборка регионов на интервалы (спека §5).

analyze_source_range — I/O (ffmpeg+MediaPipe), кэшируется по диапазону. resolve_regions — PURE.
Граница интервала = forced-склейка (каждый интервал анализируется независимо).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.models import CropOverride, SourceInterval
from app.pipeline.stage3_reframe import (
    TrackPoint,
    TrackRegion,
    build_regions_from_shots,
    build_shots,
    detect_cuts,
    sample_faces_continuous,
)

_ASPECT_W, _ASPECT_H = 9, 16

FaceSamples = list[tuple[float, list[tuple[float, float]]]]


@dataclass(frozen=True)
class RawReframe:
    """Сырой reframe-анализ диапазона (interval-relative, 0-based): лица + склейки."""

    faces: FaceSamples  # [(t, [(cx, w_frac), …]), …]
    cuts: list[float]  # тайминги склеек


def _override_for(overrides: list[CropOverride], iv: SourceInterval) -> CropOverride | None:
    """Последний override, пересекающий интервал (MVP: override применяется per-интервал)."""
    found: CropOverride | None = None
    for ov in overrides:
        if ov.source_start < iv.source_end and ov.source_end > iv.source_start:
            found = ov
    return found


def _manual_region(ov: CropOverride, dur: float) -> list[TrackRegion]:
    """Ручной override → один регион на весь интервал."""
    if ov.mode == "fit":
        return [TrackRegion(t0=0.0, t1=dur, mode="fit", points=())]
    cx = ov.center if ov.center is not None else 0.5
    return [TrackRegion(t0=0.0, t1=dur, mode="fill", points=(TrackPoint(t=0.0, mode="fill", cx=cx),))]


def resolve_regions(
    intervals: list[SourceInterval],
    raw_by_interval: list[RawReframe],
    overrides: list[CropOverride],
    *,
    src_w: int,
    src_h: int,
    smoothing: float,
    min_hold_sec: float,
    mode_setting: str = "auto",
    wide_ratio: float = 0.5,
) -> list[list[TrackRegion]]:
    """Регионы на каждый интервал (interval-relative). PURE.

    Override, пересекающий интервал, заменяет авто-регионы (per-интервал). Иначе —
    cut-aligned build_shots + build_regions_from_shots по сырому анализу интервала.
    """
    crop_w_frac = round(src_h * _ASPECT_W / _ASPECT_H) / src_w
    out: list[list[TrackRegion]] = []
    for iv, raw in zip(intervals, raw_by_interval, strict=True):
        dur = round(iv.source_end - iv.source_start, 3)
        ov = _override_for(overrides, iv)
        if ov is not None:
            out.append(_manual_region(ov, dur))
            continue
        shots = build_shots(raw.cuts, dur)
        regions = build_regions_from_shots(
            shots, raw.faces, crop_w_frac, smoothing, min_hold_sec,
            mode_setting=mode_setting, wide_ratio=wide_ratio,
        )  # fmt: skip
        if not regions:
            regions = [TrackRegion(t0=0.0, t1=dur, mode="fit", points=())]
        out.append(regions)
    return out
```

- [ ] **Step 4: Прогнать — проходит**

Run: `uv run pytest tests/unit/test_reframe_resolve.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Коммит**

```
git add services/worker/app/editor/reframe_cache.py services/worker/tests/unit/test_reframe_resolve.py
git commit -F <msg>   # feat(editor): RawReframe + resolve_regions (pure, per-interval overrides)
```

---

### Task E1.2: analyze_source_range (I/O + кэш по диапазону)

**Files:**
- Modify: `services/worker/app/editor/reframe_cache.py` (добавить функцию)
- Test: `services/worker/tests/unit/test_reframe_resolve.py` (добавить тест кэш-хита)

- [ ] **Step 1: Добавить падающий тест кэш-хита**

```python
# дополнить tests/unit/test_reframe_resolve.py
import json

from app.editor.reframe_cache import analyze_source_range


def test_analyze_reads_cache_without_ffmpeg(tmp_path):
    # пред-записываем кэш → analyze должен прочитать его, НЕ зовя ffmpeg
    cache = tmp_path / "analysis"
    cache.mkdir()
    (cache / "reframe_10.00_12.00.json").write_text(
        json.dumps({"faces": [{"t": 0.0, "faces": [[0.5, 0.2]]}], "cuts": [1.0]}),
        encoding="utf-8",
    )
    raw = analyze_source_range(
        tmp_path / "nonexistent.mp4", 10.0, 12.0, cache_dir=cache, fps=5.0, cut_threshold=0.4
    )
    assert raw.cuts == [1.0]
    assert raw.faces == [(0.0, [(0.5, 0.2)])]
```

- [ ] **Step 2: Прогнать — падает**

Run: `uv run pytest tests/unit/test_reframe_resolve.py::test_analyze_reads_cache_without_ffmpeg -v`
Expected: FAIL — `ImportError: cannot import name 'analyze_source_range'`.

- [ ] **Step 3: Реализовать analyze_source_range (добавить в reframe_cache.py)**

```python
# добавить в app/editor/reframe_cache.py


def _cache_path(cache_dir: Path, src_start: float, src_end: float) -> Path:
    return cache_dir / f"reframe_{src_start:.2f}_{src_end:.2f}.json"


def analyze_source_range(
    video: Path,
    src_start: float,
    src_end: float,
    *,
    cache_dir: Path,
    fps: float = 5.0,
    cut_threshold: float = 0.4,
) -> RawReframe:
    """Сырой reframe-анализ диапазона [src_start, src_end]. Кэш по диапазону (compute-if-missing).

    Кэш-хит → читаем JSON (НЕ зовём ffmpeg). Иначе sample_faces_continuous + detect_cuts → пишем кэш.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _cache_path(cache_dir, src_start, src_end)
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        faces: FaceSamples = [
            (f["t"], [(c[0], c[1]) for c in f["faces"]]) for f in data["faces"]
        ]
        return RawReframe(faces=faces, cuts=list(data["cuts"]))
    faces = sample_faces_continuous(video, src_start, src_end, fps=fps)
    cuts = detect_cuts(video, src_start, src_end, threshold=cut_threshold)
    path.write_text(
        json.dumps(
            {"faces": [{"t": t, "faces": [[cx, w] for cx, w in fs]} for t, fs in faces], "cuts": cuts},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return RawReframe(faces=faces, cuts=cuts)
```

- [ ] **Step 4: Прогнать — проходит**

Run: `uv run pytest tests/unit/test_reframe_resolve.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Гейт + коммит**

Run (из корня): `just check` → зелёный.

```
git add services/worker/app/editor/reframe_cache.py services/worker/tests/unit/test_reframe_resolve.py
git commit -F <msg>   # feat(editor): analyze_source_range with range-keyed cache
```

**DoD фазы E1:** `resolve_regions` покрыт (fill / fit / override-fit / override-fill-center /
2 интервала); `analyze_source_range` кэш-хит читается без ffmpeg; `just check` зелёный.

---

## Phase E2 — Рендер из edit-state (мульти-интервальный таймлайн)

**Результат фазы:** `render_timeline` собирает mp4 из списка интервалов + регионов одним
проходом ffmpeg (видео: split→trim(source-кадры)→reframe→concat→subtitles; аудио:
asplit→atrim→concat — бесшовно). 1 интервал → делегирует в существующий `render_clip`.

### Task E2.1: flatten_timeline + build_timeline_filter (PURE)

**Files:**
- Modify: `services/worker/app/pipeline/stage5_render.py` (добавить билдеры)
- Test: `services/worker/tests/unit/test_timeline_filter.py`

- [ ] **Step 1: Написать падающий тест**

```python
# tests/unit/test_timeline_filter.py
from app.models import SourceInterval
from app.pipeline.stage3_reframe import TrackPoint, TrackRegion
from app.pipeline.stage5_render import build_timeline_filter, flatten_timeline

SRC_W, SRC_H, FPS = 1920, 1080, 25.0


def _fill(t0, t1, cx):
    return TrackRegion(t0=t0, t1=t1, mode="fill", points=(TrackPoint(t=t0, mode="fill", cx=cx),))


def _fit(t0, t1):
    return TrackRegion(t0=t0, t1=t1, mode="fit", points=())


def test_flatten_maps_to_source_frames():
    intervals = [SourceInterval(source_start=10.0, source_end=12.0)]
    regions = [[_fill(0.0, 2.0, 0.5)]]
    segs = flatten_timeline(intervals, regions, FPS)
    assert len(segs) == 1
    assert segs[0].src_f0 == round(10.0 * FPS)  # 250
    assert segs[0].src_f1 == round(12.0 * FPS)  # 300
    assert segs[0].mode == "fill"


def test_filter_two_segments_fill_then_fit():
    intervals = [
        SourceInterval(source_start=10.0, source_end=12.0),
        SourceInterval(source_start=30.0, source_end=31.0),
    ]
    regions = [[_fill(0.0, 2.0, 0.5)], [_fit(0.0, 1.0)]]
    segs = flatten_timeline(intervals, regions, FPS)
    fc = build_timeline_filter(segs, SRC_W, SRC_H, FPS, "captions_clip_01.ass")
    assert "split=2" in fc and "asplit=2" in fc
    assert "trim=start_frame=250:end_frame=300" in fc
    assert "trim=start_frame=750:end_frame=775" in fc
    assert "atrim=start=10.000:end=12.000" in fc
    assert "concat=n=2:v=1:a=0[cv]" in fc
    assert "[cv]subtitles=captions_clip_01.ass[outv]" in fc
    assert "concat=n=2:v=0:a=1[outa]" in fc
    assert "[bg1]" in fc and "[fg1]" in fc  # fit-лейблы уникальны по индексу сегмента
```

- [ ] **Step 2: Прогнать — падает**

Run: `uv run pytest tests/unit/test_timeline_filter.py -v`
Expected: FAIL — `ImportError: cannot import name 'flatten_timeline'`.

- [ ] **Step 3: Реализовать билдеры (добавить в stage5_render.py)**

```python
# добавить в app/pipeline/stage5_render.py (после build_smooth_filter)

from dataclasses import dataclass  # (вверх к импортам, если ещё нет)


@dataclass(frozen=True)
class TimelineSegment:
    """Плоский сегмент рендера: source-кадры/времена + reframe-режим (спека §6)."""

    src_f0: int
    src_f1: int
    src_t0: float
    src_t1: float
    mode: str
    points: tuple[TrackPoint, ...]
    region_t0: float  # interval-relative старт региона (offset для crop-expr)


def flatten_timeline(
    intervals: list[SourceInterval],
    regions_per_interval: list[list[TrackRegion]],
    fps: float,
) -> list[TimelineSegment]:
    """Интервалы + регионы (interval-relative) → плоский список сегментов в SOURCE-кадрах. PURE."""
    segs: list[TimelineSegment] = []
    for iv, regions in zip(intervals, regions_per_interval, strict=True):
        for r in regions:
            st0 = round(iv.source_start + r.t0, 3)
            st1 = round(iv.source_start + r.t1, 3)
            segs.append(
                TimelineSegment(
                    src_f0=round(st0 * fps), src_f1=round(st1 * fps),
                    src_t0=st0, src_t1=st1, mode=r.mode, points=r.points, region_t0=r.t0,
                )
            )  # fmt: skip
    return segs


def build_timeline_filter(
    segments: list[TimelineSegment],
    src_w: int,
    src_h: int,
    fps: float,
    ass_name: str,
    *,
    out_w: int = 1080,
    out_h: int = 1920,
    blur: int = 20,
) -> str:
    """filter_complex для мульти-интервального рендера (спека §6). PURE.

    Видео: split→per-seg trim(source-кадры)+reframe→concat→subtitles.
    Аудио: asplit→per-seg atrim(source-времена)→concat (бесшовно, до энкода).
    """
    if not segments:
        raise JobError(_STAGE, "build_timeline_filter: пустой таймлайн")
    n = len(segments)
    crop_w = round(src_h * 9 / 16)
    vheads = "".join(f"[v{i}]" for i in range(n))
    aheads = "".join(f"[a{i}]" for i in range(n))
    parts = [f"[0:v]split={n}{vheads};[0:a]asplit={n}{aheads};"]
    for i, s in enumerate(segments):
        if s.mode == "fit":
            seg = (
                f"split=2[bg{i}][fg{i}];"
                f"[bg{i}]scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
                f"crop={out_w}:{out_h},gblur=sigma={blur}[bgb{i}];"
                f"[fg{i}]scale={out_w}:{out_h}:force_original_aspect_ratio=decrease[fgb{i}];"
                f"[bgb{i}][fgb{i}]overlay=(W-w)/2:(H-h)/2"
            )
        else:
            if not s.points:
                raise JobError(_STAGE, f"fill-сегмент #{i} без траектории")
            x_expr = build_fill_crop_expr(s.points, s.region_t0, src_w, src_h)
            seg = f"crop={crop_w}:{src_h}:{x_expr}:0,scale={out_w}:{out_h}:flags=lanczos"
        parts.append(
            f"[v{i}]trim=start_frame={s.src_f0}:end_frame={s.src_f1},"
            f"setpts=PTS-STARTPTS,{seg},setsar=1[sv{i}];"
        )
        parts.append(
            f"[a{i}]atrim=start={s.src_t0:.3f}:end={s.src_t1:.3f},asetpts=PTS-STARTPTS[sa{i}];"
        )
    sv = "".join(f"[sv{i}]" for i in range(n))
    sa = "".join(f"[sa{i}]" for i in range(n))
    parts.append(f"{sv}concat=n={n}:v=1:a=0[cv];[cv]subtitles={ass_name}[outv];")
    parts.append(f"{sa}concat=n={n}:v=0:a=1[outa]")
    return "".join(parts)
```

Примечание: добавь `from app.models import SourceInterval` к импортам `stage5_render.py`.

- [ ] **Step 4: Прогнать — проходит**

Run: `uv run pytest tests/unit/test_timeline_filter.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Коммит**

```
git add services/worker/app/pipeline/stage5_render.py services/worker/tests/unit/test_timeline_filter.py
git commit -F <msg>   # feat(render): flatten_timeline + build_timeline_filter (pure, multi-interval)
```

---

### Task E2.2: render_timeline (I/O) + single-interval fast-path

**Files:**
- Modify: `services/worker/app/pipeline/stage5_render.py` (добавить `build_timeline_cmd` + `render_timeline`)
- Test: интеграционно в E6 (реальный ffmpeg). Здесь — PURE-тест команды.
- Test: `services/worker/tests/unit/test_timeline_filter.py` (добавить тест команды)

- [ ] **Step 1: Добавить падающий тест команды**

```python
# дополнить tests/unit/test_timeline_filter.py
from app.pipeline.stage5_render import build_timeline_cmd


def test_timeline_cmd_full_input_no_ss():
    cmd = build_timeline_cmd("source.mp4", "FILTER", "clips/clip_01.mp4")
    assert "-ss" not in cmd  # полный вход (не пред-слайс)
    assert cmd[:3] == ["ffmpeg", "-y", "-i"]
    assert "-map" in cmd and "[outv]" in cmd and "[outa]" in cmd
    assert cmd[-1] == "clips/clip_01.mp4"
```

- [ ] **Step 2: Прогнать — падает**

Run: `uv run pytest tests/unit/test_timeline_filter.py::test_timeline_cmd_full_input_no_ss -v`
Expected: FAIL — `ImportError: cannot import name 'build_timeline_cmd'`.

- [ ] **Step 3: Реализовать build_timeline_cmd + render_timeline**

```python
# добавить в app/pipeline/stage5_render.py


def build_timeline_cmd(source: str, filter_complex: str, out_name: str) -> list[str]:
    """ffmpeg для таймлайна: ПОЛНЫЙ вход (-i), маппим [outv]/[outa] из фильтра."""
    return [
        "ffmpeg", "-y", "-i", source,
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
        out_name,
    ]  # fmt: skip


def render_timeline(
    data_dir: Path,
    source_name: str,
    intervals: list[SourceInterval],
    regions_per_interval: list[list[TrackRegion]],
    ass_name: str,
    out_name: str,
    *,
    src_w: int,
    src_h: int,
    fps: float,
    engine: str = "A",
) -> float:
    """Рендер mp4 из edit-state (спека §6). Возвращает латентность (с). JobError при сбое.

    1 интервал → делегирует в render_clip (проверенный путь, непрерывное аудио).
    >1 интервал → мульти-интервальный concat (Engine A; бесшовное аудио внутри filtergraph).
    """
    if not intervals:
        raise JobError(_STAGE, "render_timeline: нет интервалов")
    (data_dir / out_name).parent.mkdir(parents=True, exist_ok=True)

    if len(intervals) == 1:
        return render_clip(
            data_dir, source_name, intervals[0].source_start, ass_name, out_name,
            regions=regions_per_interval[0], src_w=src_w, src_h=src_h, fps=fps, engine=engine,
        )  # fmt: skip

    segments = flatten_timeline(intervals, regions_per_interval, fps)
    fc = build_timeline_filter(segments, src_w, src_h, fps, ass_name)
    t0 = time.perf_counter()
    _run_ffmpeg(build_timeline_cmd(source_name, fc, out_name), data_dir)
    if not (data_dir / out_name).exists():
        raise JobError(_STAGE, f"render_timeline не создал {out_name}")
    return round(time.perf_counter() - t0, 2)
```

- [ ] **Step 4: Прогнать — проходит**

Run: `uv run pytest tests/unit/test_timeline_filter.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Гейт + коммит**

Run (из корня): `just check` → зелёный.

```
git add services/worker/app/pipeline/stage5_render.py services/worker/tests/unit/test_timeline_filter.py
git commit -F <msg>   # feat(render): render_timeline (multi-interval, single-interval fast-path)
```

**DoD фазы E2:** билдеры таймлайна покрыты (flatten в source-кадры, фильтр 2 сегментов
fill+fit с уникальными лейблами, команда без `-ss`); `render_timeline` делегирует при 1 интервале;
`just check` зелёный. Реальный mp4 из 2 интервалов проверяется в E6.

---

## Phase E3 — Субтитры v2 (стиль + текст + караоке)

**Результат фазы:** `CaptionTrack` компилируется в ASS из одной модели: стиль (шрифт/цвета/
контур/тень/плашка/позиция/регистр) + караоке-подсветка слова через нативный libass `{\k}`
+ правка текста реплики (`text_override`) + скрытие реплики (`hidden`). Всё PURE.

Караоке-модель MVP: **прогрессивная заливка** — слово красится из `style.color` (Secondary)
в `highlight.color` (Primary) по мере проговаривания (классический ASS `\k`). Вариант «только
текущее слово» — тюнинг позже.

### Task E3.1: _ass_color + compile_ass + write_caption_ass

**Files:**
- Create: `services/worker/app/editor/captions_v2.py`
- Test: `services/worker/tests/unit/test_captions_v2.py`

Переиспользуем `format_ass_time` из `app/pipeline/stage4_captions.py`.

- [ ] **Step 1: Написать падающий тест**

```python
# tests/unit/test_captions_v2.py
from app.editor.captions_v2 import _ass_color, compile_ass
from app.editor.timemap import ClipTimeMap
from app.models import CaptionReply, CaptionStyle, CaptionTrack, HighlightStyle, SourceInterval, Word


def _w(text, start, end):
    return Word(text=text, start=start, end=end)


def _cmap():
    return ClipTimeMap([SourceInterval(source_start=0.0, source_end=2.0)])


def test_ass_color_conversion():
    assert _ass_color("#FFFFFF") == "&H00FFFFFF"
    assert _ass_color("#FFE000") == "&H0000E0FF"  # BGR порядок: bb=00 gg=E0 rr=FF


def test_compile_ass_karaoke_tags_and_uppercase():
    words = [_w("Привет", 0.0, 0.4), _w("мир", 0.4, 0.8)]
    track = CaptionTrack(
        style=CaptionStyle(), highlight=HighlightStyle(), replies=[CaptionReply(word_refs=[0, 1])]
    )
    ass = compile_ass(track, words, _cmap())
    assert "[V4+ Styles]" in ass and "[Events]" in ass
    assert ass.count("\\k") == 2  # по \k-тегу на слово
    assert "ПРИВЕТ" in ass  # uppercase=True по умолчанию
    assert "Dialogue: 0," in ass


def test_compile_ass_no_highlight_is_plain():
    words = [_w("a", 0.0, 0.4), _w("b", 0.4, 0.8)]
    track = CaptionTrack(
        style=CaptionStyle(uppercase=False), highlight=None, replies=[CaptionReply(word_refs=[0, 1])]
    )
    ass = compile_ass(track, words, _cmap())
    assert "\\k" not in ass
    assert "a b" in ass


def test_compile_ass_text_override_plain_on_count_mismatch():
    words = [_w("a", 0.0, 0.4), _w("b", 0.4, 0.8)]
    track = CaptionTrack(
        style=CaptionStyle(),
        highlight=HighlightStyle(),
        replies=[CaptionReply(word_refs=[0, 1], text_override="ОДНО")],
    )
    ass = compile_ass(track, words, _cmap())
    assert "\\k" not in ass and "ОДНО" in ass  # 1 слово ≠ 2 word_refs → без караоке


def test_compile_ass_hidden_skipped():
    words = [_w("a", 0.0, 0.4)]
    track = CaptionTrack(
        style=CaptionStyle(), highlight=None, replies=[CaptionReply(word_refs=[0], hidden=True)]
    )
    ass = compile_ass(track, words, _cmap())
    assert "Dialogue:" not in ass


def test_compile_ass_box_sets_border_style_3():
    words = [_w("a", 0.0, 0.4)]
    track = CaptionTrack(
        style=CaptionStyle(box_color="#000000", box_opacity=0.5),
        highlight=None,
        replies=[CaptionReply(word_refs=[0])],
    )
    ass = compile_ass(track, words, _cmap())
    # BorderStyle = 16-е значение строки Style; split(",")[0]="Style: Default" → индекс 15
    style_line = next(ln for ln in ass.splitlines() if ln.startswith("Style: Default,"))
    fields = style_line.split(",")
    assert fields[15] == "3"
```

- [ ] **Step 2: Прогнать — падает**

Run: `uv run pytest tests/unit/test_captions_v2.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.editor.captions_v2'`.

- [ ] **Step 3: Реализовать captions_v2.py**

```python
# app/editor/captions_v2.py
"""Компиляция CaptionTrack → ASS (спека §7). PURE.

Один источник правды (CaptionTrack) → ASS для рендера (libass). Караоке = нативный {\\k}.
"""

from __future__ import annotations

from pathlib import Path

from app.editor.timemap import ClipTimeMap
from app.models import CaptionReply, CaptionTrack, HighlightStyle, Word
from app.pipeline.stage4_captions import format_ass_time


def _ass_color(hex_color: str, alpha_byte: int = 0) -> str:
    """#RRGGBB → ASS &HAABBGGRR (alpha_byte: 0=непрозрачный, 255=прозрачный)."""
    h = hex_color.lstrip("#")
    rr, gg, bb = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha_byte:02X}{bb}{gg}{rr}".upper()


def _reply_text(reply: CaptionReply, rwords: list[Word], uppercase: bool, hl: HighlightStyle | None) -> str:
    def up(s: str) -> str:
        return s.upper() if uppercase else s

    if reply.text_override is not None:
        ov = reply.text_override.split()
        if hl and len(ov) == len(rwords):
            return " ".join(
                f"{{\\k{round((w.end - w.start) * 100)}}}{up(o)}" for o, w in zip(ov, rwords, strict=True)
            )
        return up(reply.text_override)
    if hl:
        return " ".join(f"{{\\k{round((w.end - w.start) * 100)}}}{up(w.text)}" for w in rwords)
    return " ".join(up(w.text) for w in rwords)


def compile_ass(track: CaptionTrack, words: list[Word], cmap: ClipTimeMap) -> str:
    """CaptionTrack + слова + тайм-маппинг → полный ASS-текст (тайминги в КЛИП-времени)."""
    st = track.style
    hl = track.highlight
    primary = _ass_color(hl.color) if hl else _ass_color(st.color)  # активный/залитый
    secondary = _ass_color(st.color)  # ещё не проговорённый
    outline = _ass_color(st.outline_color)
    if st.box_color:
        back = _ass_color(st.box_color, round((1.0 - st.box_opacity) * 255))
        border_style = 3
    else:
        back = "&H64000000"
        border_style = 1

    script_info = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n"
        "WrapStyle: 0\nScaledBorderAndShadow: yes\n"
    )
    styles = (
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{st.font},{st.size},{primary},{secondary},{outline},{back},"
        f"-1,0,0,0,100,100,0,0,{border_style},{st.outline_w},{st.shadow},"
        f"{st.alignment},40,40,{st.margin_v},1\n"
    )
    events_hdr = "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, Effect, Text\n"
    lines = [script_info, styles, events_hdr]

    for reply in track.replies:
        if reply.hidden or not reply.word_refs:
            continue
        rwords = [words[i] for i in reply.word_refs]
        start_c = cmap.source_to_clip(rwords[0].start)
        if start_c is None:
            continue  # слово в дырке (не должно случаться при rebuild_replies) → пропуск
        last_c = cmap.source_to_clip(rwords[-1].start)
        end_c = (last_c if last_c is not None else start_c) + (rwords[-1].end - rwords[-1].start)
        text = _reply_text(reply, rwords, st.uppercase, hl)
        lines.append(
            f"Dialogue: 0,{format_ass_time(start_c)},{format_ass_time(end_c)},Default,,0,0,,{text}"
        )
    return "\n".join(lines) + "\n"


def write_caption_ass(track: CaptionTrack, words: list[Word], cmap: ClipTimeMap, out_path: Path) -> str:
    """Скомпилировать и записать ASS-файл. Возвращает ASS-текст."""
    ass = compile_ass(track, words, cmap)
    out_path.write_text(ass, encoding="utf-8")
    return ass
```

- [ ] **Step 4: Прогнать — проходит**

Run: `uv run pytest tests/unit/test_captions_v2.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Гейт + коммит**

Run (из корня): `just check` → зелёный.

```
git add services/worker/app/editor/captions_v2.py services/worker/tests/unit/test_captions_v2.py
git commit -F <msg>   # feat(editor): CaptionTrack -> ASS with karaoke (\k), text override, box
```

**DoD фазы E3:** `compile_ass` покрыт (караоке-`\k` теги + uppercase, без highlight = plain,
text_override при несовпадении слов = plain, hidden пропускается, плашка → BorderStyle=3,
конвертация цвета); `just check` зелёный.

---

## Phase E4 — Операции редактирования + персистентность + Editor API

**Результат фазы:** PURE-операции (trim/extend/add-section/crop), персистентность `ClipEdit`
(SQLite + edit.json + optimistic-lock), фоновый рендер из edit-state, REST-эндпоинты редактора.

> **Отклонение от спеки §10 (осознанное):** дефолтный `ClipEdit` создаётся **лениво** на
> первом `GET …/edit` через `store.ensure_edit` (из `segments.json` + `transcript.json`),
> а НЕ пишется эагерно в `run.py`. Плюсы: нет связности `run.py↔БД`; работает на уже
> закэшированных джобах (comedy01/test01) без перепрогона пайплайна.

### Task E4.1: PURE-операции (ops.py)

**Files:**
- Create: `services/worker/app/editor/ops.py`
- Test: `services/worker/tests/unit/test_editor_ops.py`

- [ ] **Step 1: Написать падающий тест**

```python
# tests/unit/test_editor_ops.py
from app.editor.defaults import default_clip_edit
from app.editor.ops import add_section, apply_extend, apply_trim, set_crop_override
from app.models import CropOverride, Segment, Word


def _w(t, s, e):
    return Word(text=t, start=s, end=e)


WORDS = [_w("a", 0.0, 0.4), _w("b", 0.4, 0.8), _w("c", 1.0, 1.4), _w("d", 1.4, 1.8), _w("e", 2.0, 2.4)]


def _base(end=3.0):
    seg = Segment(start=0.0, end=end, reason="r", score=0.5, type="hook")
    return default_clip_edit("clip_01", seg, WORDS)


def test_apply_trim_makes_hole():
    out = apply_trim(_base(), [2, 3], WORDS)  # вырезать c,d → диапазон [1.0,1.8]
    bounds = [(i.source_start, i.source_end) for i in out.source_intervals]
    assert bounds == [(0.0, 1.0), (1.8, 3.0)]
    refs = [i for r in out.captions.replies for i in r.word_refs]
    assert 2 not in refs and 3 not in refs


def test_add_section_inserts_interval_and_words():
    seg = Segment(start=0.0, end=1.0, reason="r", score=0.5, type="hook")
    edit = default_clip_edit("clip_01", seg, WORDS)  # интервал [0,1] → слова a,b
    out = add_section(edit, 2.0, 2.5, 1, WORDS)  # добавить [2.0,2.5] → слово e
    assert len(out.source_intervals) == 2
    assert 4 in [i for r in out.captions.replies for i in r.word_refs]


def test_apply_extend_end_grows_interval():
    seg = Segment(start=0.0, end=1.0, reason="r", score=0.5, type="hook")
    edit = default_clip_edit("clip_01", seg, WORDS)
    out = apply_extend(edit, edge="end", new_value=2.5, words=WORDS)
    assert out.source_intervals[-1].source_end == 2.5
    refs = [i for r in out.captions.replies for i in r.word_refs]
    assert 2 in refs and 3 in refs  # c,d попали в расширенный интервал


def test_set_crop_override_replaces_overlapping():
    edit = set_crop_override(_base(), CropOverride(source_start=0.0, source_end=1.0, mode="fill", center=0.6))
    assert len(edit.reframe_overrides) == 1
    edit2 = set_crop_override(edit, CropOverride(source_start=0.5, source_end=1.5, mode="fit"))
    assert len(edit2.reframe_overrides) == 1 and edit2.reframe_overrides[0].mode == "fit"
```

- [ ] **Step 2: Прогнать — падает**

Run: `uv run pytest tests/unit/test_editor_ops.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.editor.ops'`.

- [ ] **Step 3: Реализовать ops.py**

```python
# app/editor/ops.py
"""PURE-операции над ClipEdit (спека §4.1): интервальная математика в одном месте.

Каждая операция возвращает НОВЫЙ ClipEdit (version НЕ трогаем — его инкрементит store при
персисте). Структурные правки интервалов перестраивают реплики через rebuild_replies.
"""

from __future__ import annotations

from app.editor.replies import rebuild_replies
from app.models import ClipEdit, CropOverride, SourceInterval, Word


def _subtract_range(intervals: list[SourceInterval], rs: float, re: float) -> list[SourceInterval]:
    """Выколоть диапазон [rs, re] из интервалов (clip-порядок сохраняется)."""
    out: list[SourceInterval] = []
    for iv in intervals:
        if re <= iv.source_start or rs >= iv.source_end:  # нет пересечения
            out.append(iv)
            continue
        if iv.source_start < rs:
            out.append(SourceInterval(source_start=iv.source_start, source_end=round(rs, 3)))
        if re < iv.source_end:
            out.append(SourceInterval(source_start=round(re, 3), source_end=iv.source_end))
    return out


def _with_intervals(edit: ClipEdit, intervals: list[SourceInterval], words: list[Word]) -> ClipEdit:
    replies = rebuild_replies(words, intervals, keep=edit.captions.replies)
    captions = edit.captions.model_copy(update={"replies": replies})
    return edit.model_copy(update={"source_intervals": intervals, "captions": captions})


def apply_trim(edit: ClipEdit, word_indices: list[int], words: list[Word]) -> ClipEdit:
    """Удалить слова → выколоть их source-диапазон из интервалов + перестроить реплики."""
    if not word_indices:
        return edit
    rs = min(words[i].start for i in word_indices)
    re = max(words[i].end for i in word_indices)
    return _with_intervals(edit, _subtract_range(edit.source_intervals, rs, re), words)


def add_section(edit: ClipEdit, source_start: float, source_end: float, at_index: int, words: list[Word]) -> ClipEdit:
    """Вставить интервал [source_start, source_end] на позицию at_index + перестроить реплики."""
    new = list(edit.source_intervals)
    new.insert(at_index, SourceInterval(source_start=source_start, source_end=source_end))
    return _with_intervals(edit, new, words)


def apply_extend(edit: ClipEdit, *, edge: str, new_value: float, words: list[Word]) -> ClipEdit:
    """Подвинуть начало первого ('start') или конец последнего ('end') интервала."""
    new = list(edit.source_intervals)
    if not new:
        return edit
    if edge == "start":
        new[0] = SourceInterval(source_start=new_value, source_end=new[0].source_end)
    elif edge == "end":
        new[-1] = SourceInterval(source_start=new[-1].source_start, source_end=new_value)
    return _with_intervals(edit, new, words)


def set_crop_override(edit: ClipEdit, override: CropOverride) -> ClipEdit:
    """Добавить ручной кроп, заменив пересекающиеся по диапазону overrides."""
    kept = [
        o
        for o in edit.reframe_overrides
        if not (o.source_start < override.source_end and o.source_end > override.source_start)
    ]
    return edit.model_copy(update={"reframe_overrides": [*kept, override]})
```

- [ ] **Step 4: Прогнать — проходит**

Run: `uv run pytest tests/unit/test_editor_ops.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Коммит**

```
git add services/worker/app/editor/ops.py services/worker/tests/unit/test_editor_ops.py
git commit -F <msg>   # feat(editor): pure edit ops trim/add-section/extend/crop
```

---

### Task E4.2: Персистентность — clip_edits таблица + store

**Files:**
- Modify: `services/worker/app/db.py` (init_db + новые функции)
- Create: `services/worker/app/editor/store.py`
- Test: `services/worker/tests/unit/test_editor_store.py`

- [ ] **Step 1: Написать падающий тест**

```python
# tests/unit/test_editor_store.py
import json

import pytest

from app import db
from app.editor import store
from app.editor.store import EditConflict
from app.models import Segment, Transcript, Word


def _setup(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "jobs.db")
    monkeypatch.setattr(store, "DATA_ROOT", tmp_path / "data")
    db.init_db()
    job = "jobZ"
    d = tmp_path / "data" / job
    d.mkdir(parents=True)
    seg = Segment(start=0.0, end=3.0, reason="r", score=0.5, type="hook")
    (d / "segments.json").write_text(json.dumps([seg.model_dump()]), encoding="utf-8")
    words = [Word(text="a", start=0.0, end=0.4), Word(text="b", start=0.4, end=0.8)]
    (d / "transcript.json").write_text(
        Transcript(language="ru", duration=3.0, words=words).model_dump_json(), encoding="utf-8"
    )
    return job


def test_ensure_creates_default_then_loads(monkeypatch, tmp_path):
    job = _setup(monkeypatch, tmp_path)
    edit = store.ensure_edit(job, "clip_01")
    assert edit.version == 1 and len(edit.source_intervals) == 1
    again = store.load_edit(job, "clip_01")
    assert again is not None and again.version == 1


def test_save_bumps_version_and_optimistic_lock(monkeypatch, tmp_path):
    job = _setup(monkeypatch, tmp_path)
    edit = store.ensure_edit(job, "clip_01")  # version 1
    saved = store.save_edit(job, "clip_01", edit, expected_version=1)
    assert saved.version == 2
    with pytest.raises(EditConflict):
        store.save_edit(job, "clip_01", edit, expected_version=1)  # устаревшая версия


def test_load_transcript_words(monkeypatch, tmp_path):
    job = _setup(monkeypatch, tmp_path)
    words = store.load_transcript_words(job)
    assert [w.text for w in words] == ["a", "b"]
```

- [ ] **Step 2: Прогнать — падает**

Run: `uv run pytest tests/unit/test_editor_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.editor.store'`.

- [ ] **Step 3a: Расширить db.py (init_db + функции clip_edits)**

```python
# app/db.py — в init_db(), ПОСЛЕ создания таблицы jobs, добавить второй execute:
        c.execute(
            """CREATE TABLE IF NOT EXISTS clip_edits (
                job_id TEXT, clip_id TEXT, version INTEGER, edit_json TEXT,
                render_status TEXT, render_url TEXT, render_error TEXT, updated_at REAL,
                PRIMARY KEY (job_id, clip_id)
            )"""
        )

# app/db.py — добавить функции в конец файла:


def get_clip_edit_row(job_id: str, clip_id: str) -> dict[str, Any] | None:
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM clip_edits WHERE job_id=? AND clip_id=?", (job_id, clip_id)
        ).fetchone()
    return dict(row) if row is not None else None


def put_clip_edit(job_id: str, clip_id: str, edit_json: str, version: int) -> None:
    now = time.time()
    with _conn() as c:
        exists = c.execute(
            "SELECT 1 FROM clip_edits WHERE job_id=? AND clip_id=?", (job_id, clip_id)
        ).fetchone()
        if exists:
            c.execute(
                "UPDATE clip_edits SET edit_json=?, version=?, updated_at=? WHERE job_id=? AND clip_id=?",
                (edit_json, version, now, job_id, clip_id),
            )
        else:
            c.execute(
                "INSERT INTO clip_edits (job_id,clip_id,version,edit_json,updated_at) VALUES (?,?,?,?,?)",
                (job_id, clip_id, version, edit_json, now),
            )


def set_render_status(
    job_id: str, clip_id: str, status: str, url: str | None, error: str | None
) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE clip_edits SET render_status=?, render_url=?, render_error=?, updated_at=?"
            " WHERE job_id=? AND clip_id=?",
            (status, url, error, time.time(), job_id, clip_id),
        )
```

- [ ] **Step 3b: Создать store.py**

```python
# app/editor/store.py
"""Персистентность ClipEdit (спека §10): SQLite (источник правды) + edit.json зеркало.

ensure_edit лениво создаёт дефолт из segments.json+transcript.json. save_edit — optimistic-lock.
"""

from __future__ import annotations

import json
from pathlib import Path

from app import db
from app.editor.defaults import default_clip_edit
from app.models import ClipEdit, Segment, Transcript, Word
from app.run import DATA_ROOT


class EditConflict(Exception):
    """Версия edit-state в запросе устарела (optimistic-lock)."""


def _mirror_path(job_id: str, clip_id: str) -> Path:
    return DATA_ROOT / job_id / "clips" / clip_id / "edit.json"


def load_transcript_words(job_id: str) -> list[Word]:
    tr = Transcript.model_validate_json((DATA_ROOT / job_id / "transcript.json").read_text("utf-8"))
    return tr.words


def load_edit(job_id: str, clip_id: str) -> ClipEdit | None:
    row = db.get_clip_edit_row(job_id, clip_id)
    if row is None or not row.get("edit_json"):
        return None
    return ClipEdit.model_validate_json(row["edit_json"])


def save_edit(job_id: str, clip_id: str, edit: ClipEdit, *, expected_version: int | None) -> ClipEdit:
    """Сохранить edit (инкремент version). EditConflict при несовпадении версии."""
    row = db.get_clip_edit_row(job_id, clip_id)
    current = row["version"] if row else None
    if expected_version is not None and current is not None and current != expected_version:
        raise EditConflict(f"version {expected_version} != current {current}")
    saved = edit.model_copy(update={"version": (current or 0) + 1})
    payload = saved.model_dump_json()
    db.put_clip_edit(job_id, clip_id, payload, saved.version)
    mirror = _mirror_path(job_id, clip_id)
    mirror.parent.mkdir(parents=True, exist_ok=True)
    mirror.write_text(payload, encoding="utf-8")
    return saved


def ensure_edit(job_id: str, clip_id: str) -> ClipEdit:
    """Загрузить edit, либо создать дефолт из сегмента (segments.json + transcript.json)."""
    existing = load_edit(job_id, clip_id)
    if existing is not None:
        return existing
    out = DATA_ROOT / job_id
    segs = json.loads((out / "segments.json").read_text(encoding="utf-8"))
    idx = int(clip_id.split("_")[1]) - 1  # clip_01 → 0
    if idx < 0 or idx >= len(segs):
        raise KeyError(clip_id)
    seg = Segment.model_validate(segs[idx])
    edit = default_clip_edit(clip_id, seg, load_transcript_words(job_id))
    return save_edit(job_id, clip_id, edit, expected_version=None)
```

- [ ] **Step 4: Прогнать — проходит**

Run: `uv run pytest tests/unit/test_editor_store.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Коммит**

```
git add services/worker/app/db.py services/worker/app/editor/store.py services/worker/tests/unit/test_editor_store.py
git commit -F <msg>   # feat(editor): clip_edits persistence + store (ensure/save, optimistic-lock)
```

---

### Task E4.3: Фоновый рендер из edit-state (tasks.py)

**Files:**
- Modify: `services/worker/app/tasks.py` (добавить `render_clip_edit_job`)

- [ ] **Step 1: Реализовать render_clip_edit_job**

```python
# app/tasks.py — добавить функцию (импорты — внутри, чтобы не тянуть torch/ffmpeg-зависимости в /healthz)


def render_clip_edit_job(job_id: str, clip_id: str) -> None:
    """Собрать mp4 из текущего ClipEdit (фон). Статус рендера → clip_edits (правило №8)."""
    from app.config import get_settings
    from app.editor import store
    from app.editor.captions_v2 import write_caption_ass
    from app.editor.reframe_cache import analyze_source_range, resolve_regions
    from app.editor.timemap import ClipTimeMap
    from app.models import Transcript
    from app.pipeline.stage0_import import SourceMeta
    from app.pipeline.stage5_render import render_timeline
    from app.run import DATA_ROOT

    try:
        s = get_settings()
        out = DATA_ROOT / job_id
        edit = store.load_edit(job_id, clip_id)
        if edit is None:
            raise JobError("render", f"нет edit для {clip_id}")
        meta = SourceMeta.model_validate_json((out / "meta.json").read_text(encoding="utf-8"))
        transcript = Transcript.model_validate_json((out / "transcript.json").read_text("utf-8"))
        analysis_dir = out / "analysis"
        raw = [
            analyze_source_range(
                out / "source.mp4", iv.source_start, iv.source_end,
                cache_dir=analysis_dir, fps=s.reframe_face_fps, cut_threshold=s.reframe_cut_threshold,
            )
            for iv in edit.source_intervals
        ]  # fmt: skip
        regions = resolve_regions(
            edit.source_intervals, raw, edit.reframe_overrides,
            src_w=meta.width, src_h=meta.height, smoothing=s.reframe_smoothing,
            min_hold_sec=s.reframe_min_hold_sec, mode_setting=s.reframe_mode,
            wide_ratio=s.reframe_wide_ratio,
        )  # fmt: skip
        cmap = ClipTimeMap(edit.source_intervals)
        write_caption_ass(edit.captions, transcript.words, cmap, out / f"captions_{clip_id}.ass")
        render_timeline(
            out, "source.mp4", edit.source_intervals, regions,
            f"captions_{clip_id}.ass", f"clips/{clip_id}.mp4",
            src_w=meta.width, src_h=meta.height, fps=meta.fps, engine=s.reframe_engine,
        )  # fmt: skip
        db.set_render_status(job_id, clip_id, "done", f"clips/{clip_id}.mp4", None)
    except JobError as e:
        db.set_render_status(job_id, clip_id, "failed", None, str(e))
    except Exception as e:  # noqa: BLE001 — фон-таск: любое падение → статус failed
        db.set_render_status(job_id, clip_id, "failed", None, f"unexpected: {e}")
```

- [ ] **Step 2: Проверить, что модуль импортируется (без падения линтера)**

Run: `uv run python -c "import app.tasks"`
Expected: без ошибок.

- [ ] **Step 3: Коммит**

```
git add services/worker/app/tasks.py
git commit -F <msg>   # feat(editor): background render_clip_edit_job from edit-state
```

---

### Task E4.4: Editor REST-эндпоинты (main.py) + smoke

**Files:**
- Modify: `services/worker/app/main.py` (добавить эндпоинты)
- Test: `services/worker/tests/unit/test_editor_api.py`

- [ ] **Step 1: Написать падающий smoke-тест (TestClient, без ffmpeg)**

```python
# tests/unit/test_editor_api.py
import json

from fastapi.testclient import TestClient

from app import db
from app.editor import store
from app.models import Segment, Transcript, Word


def _client(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "jobs.db")
    monkeypatch.setattr(store, "DATA_ROOT", tmp_path / "data")
    db.init_db()
    job = "jobA"
    d = tmp_path / "data" / job
    d.mkdir(parents=True)
    (d / "segments.json").write_text(
        json.dumps([Segment(start=0.0, end=3.0, reason="r", score=0.5, type="hook").model_dump()]),
        encoding="utf-8",
    )
    words = [Word(text="a", start=0.0, end=0.4), Word(text="b", start=0.4, end=0.8), Word(text="c", start=1.0, end=1.4)]
    (d / "transcript.json").write_text(
        Transcript(language="ru", duration=3.0, words=words).model_dump_json(), encoding="utf-8"
    )
    from app.main import app

    return TestClient(app), job


def test_get_edit_creates_default(monkeypatch, tmp_path):
    client, job = _client(monkeypatch, tmp_path)
    r = client.get(f"/jobs/{job}/clips/clip_01/edit")
    assert r.status_code == 200
    edit = r.json()
    assert edit["version"] == 1 and len(edit["source_intervals"]) == 1


def test_trim_makes_hole_and_optimistic_lock(monkeypatch, tmp_path):
    client, job = _client(monkeypatch, tmp_path)
    v = client.get(f"/jobs/{job}/clips/clip_01/edit").json()["version"]
    r = client.post(f"/jobs/{job}/clips/clip_01/edit/trim", json={"version": v, "word_indices": [1]})
    assert r.status_code == 200
    assert len(r.json()["source_intervals"]) == 2  # дырка
    stale = client.post(f"/jobs/{job}/clips/clip_01/edit/trim", json={"version": v, "word_indices": [0]})
    assert stale.status_code == 409  # версия устарела


def test_get_edit_404_for_missing_clip(monkeypatch, tmp_path):
    client, job = _client(monkeypatch, tmp_path)
    r = client.get(f"/jobs/{job}/clips/clip_09/edit")
    assert r.status_code == 404
```

- [ ] **Step 2: Прогнать — падает**

Run: `uv run pytest tests/unit/test_editor_api.py -v`
Expected: FAIL — 404/405 (эндпоинтов ещё нет).

- [ ] **Step 3: Добавить эндпоинты в main.py**

```python
# app/main.py — добавить импорты вверх:
from app.editor import store
from app.editor.ops import add_section, apply_extend, apply_trim, set_crop_override
from app.editor.store import EditConflict
from app.models import CaptionTrack, CropOverride
from app.tasks import render_clip_edit_job


# app/main.py — тела запросов + эндпоинты (после get_job):


class PatchEditBody(BaseModel):
    version: int
    captions: CaptionTrack


class TrimBody(BaseModel):
    version: int
    word_indices: list[int]


class AddSectionBody(BaseModel):
    version: int
    source_start: float
    source_end: float
    at_index: int


class ExtendBody(BaseModel):
    version: int
    edge: str  # "start" | "end"
    new_value: float


class CropBody(BaseModel):
    version: int
    source_start: float
    source_end: float
    mode: str  # "fill" | "fit"
    center: float | None = None


def _save_or_409(job_id: str, clip_id: str, new_edit: Any, version: int) -> dict[str, Any]:
    try:
        return store.save_edit(job_id, clip_id, new_edit, expected_version=version).model_dump()
    except EditConflict as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


def _load_or_404(job_id: str, clip_id: str) -> Any:
    edit = store.load_edit(job_id, clip_id)
    if edit is None:
        raise HTTPException(status_code=404, detail="edit not found")
    return edit


@app.get("/jobs/{job_id}/clips/{clip_id}/edit")
def get_clip_edit(job_id: str, clip_id: str) -> dict[str, Any]:
    """ClipEdit клипа (создаёт дефолт из сегмента при первом обращении)."""
    try:
        return store.ensure_edit(job_id, clip_id).model_dump()
    except (FileNotFoundError, KeyError) as e:
        raise HTTPException(status_code=404, detail="clip/segment not found") from e


@app.patch("/jobs/{job_id}/clips/{clip_id}/edit")
def patch_clip_edit(job_id: str, clip_id: str, body: PatchEditBody) -> dict[str, Any]:
    """Прямая правка субтитров (стиль/текст/highlight). Интервалы НЕ трогает."""
    edit = _load_or_404(job_id, clip_id)
    return _save_or_409(job_id, clip_id, edit.model_copy(update={"captions": body.captions}), body.version)


@app.post("/jobs/{job_id}/clips/{clip_id}/edit/trim")
def op_trim(job_id: str, clip_id: str, body: TrimBody) -> dict[str, Any]:
    edit = _load_or_404(job_id, clip_id)
    words = store.load_transcript_words(job_id)
    return _save_or_409(job_id, clip_id, apply_trim(edit, body.word_indices, words), body.version)


@app.post("/jobs/{job_id}/clips/{clip_id}/edit/add-section")
def op_add_section(job_id: str, clip_id: str, body: AddSectionBody) -> dict[str, Any]:
    edit = _load_or_404(job_id, clip_id)
    words = store.load_transcript_words(job_id)
    new = add_section(edit, body.source_start, body.source_end, body.at_index, words)
    return _save_or_409(job_id, clip_id, new, body.version)


@app.post("/jobs/{job_id}/clips/{clip_id}/edit/extend")
def op_extend(job_id: str, clip_id: str, body: ExtendBody) -> dict[str, Any]:
    edit = _load_or_404(job_id, clip_id)
    words = store.load_transcript_words(job_id)
    new = apply_extend(edit, edge=body.edge, new_value=body.new_value, words=words)
    return _save_or_409(job_id, clip_id, new, body.version)


@app.post("/jobs/{job_id}/clips/{clip_id}/edit/crop")
def op_crop(job_id: str, clip_id: str, body: CropBody) -> dict[str, Any]:
    edit = _load_or_404(job_id, clip_id)
    ov = CropOverride(
        source_start=body.source_start, source_end=body.source_end, mode=body.mode, center=body.center
    )
    return _save_or_409(job_id, clip_id, set_crop_override(edit, ov), body.version)


@app.post("/jobs/{job_id}/clips/{clip_id}/render", status_code=202)
def post_render(job_id: str, clip_id: str, bg: BackgroundTasks) -> dict[str, Any]:
    """Async-рендер mp4 из edit-state. Статус — GET …/render."""
    _load_or_404(job_id, clip_id)
    db.set_render_status(job_id, clip_id, "rendering", None, None)
    bg.add_task(render_clip_edit_job, job_id, clip_id)
    return {"status": "rendering"}


@app.get("/jobs/{job_id}/clips/{clip_id}/render")
def get_render(job_id: str, clip_id: str) -> dict[str, Any]:
    row = db.get_clip_edit_row(job_id, clip_id)
    if row is None:
        raise HTTPException(status_code=404, detail="clip not found")
    url = row.get("render_url")
    return {
        "status": row.get("render_status"),
        "video_url": f"media/{job_id}/{url}" if url else None,
        "error": row.get("render_error"),
    }


@app.get("/jobs/{job_id}/clips/{clip_id}/analysis")
def get_analysis(job_id: str, clip_id: str) -> dict[str, Any]:
    """Интервалы + слова клипа (для клиент-превью субтитров/таймлайна)."""
    edit = _load_or_404(job_id, clip_id)
    words = store.load_transcript_words(job_id)
    in_clip = [
        w.model_dump()
        for w in words
        if any(iv.source_start <= w.start < iv.source_end for iv in edit.source_intervals)
    ]
    return {"intervals": [iv.model_dump() for iv in edit.source_intervals], "words": in_clip}
```

- [ ] **Step 4: Прогнать — проходит**

Run: `uv run pytest tests/unit/test_editor_api.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Гейт + коммит**

Run (из корня): `just check` → зелёный.

```
git add services/worker/app/main.py services/worker/tests/unit/test_editor_api.py
git commit -F <msg>   # feat(editor): REST endpoints (get/patch/trim/add-section/extend/crop/render/analysis)
```

**DoD фазы E4:** ops покрыты (trim/add-section/extend/crop); store (ensure/save/optimistic-lock)
покрыт; API-smoke зелёный (GET создаёт дефолт, trim → дырка, stale version → 409, 404 на нет-клипа);
`just check` зелёный. Реальный рендер из edit-state — в E6.

---

## Phase E5 — Style-пресеты (мини brand kit)

**Результат фазы:** именованные пресеты стиля субтитров (глобально, без auth — MVP);
применение к клипу или ко всем клипам job.

### Task E5.1: CaptionPreset + apply_preset (PURE)

**Files:**
- Modify: `services/worker/app/models.py` (добавить `CaptionPreset`)
- Create: `services/worker/app/editor/presets.py`
- Test: `services/worker/tests/unit/test_presets.py`

- [ ] **Step 1: Написать падающий тест**

```python
# tests/unit/test_presets.py
from app.editor.defaults import default_clip_edit
from app.editor.presets import apply_preset
from app.models import CaptionPreset, CaptionStyle, HighlightStyle, Segment, Word


def test_apply_preset_sets_style_and_highlight():
    words = [Word(text="a", start=0.0, end=0.4)]
    edit = default_clip_edit("clip_01", Segment(start=0.0, end=1.0, reason="r", score=0.5, type="hook"), words)
    preset = CaptionPreset(
        id="p1", name="Hormozi",
        style=CaptionStyle(color="#00FF00", size=120), highlight=HighlightStyle(color="#FF00FF"),
    )
    out = apply_preset(edit, preset)
    assert out.captions.style.color == "#00FF00" and out.captions.style.size == 120
    assert out.captions.highlight.color == "#FF00FF"
    # реплики НЕ трогаются
    assert out.captions.replies == edit.captions.replies
```

- [ ] **Step 2: Прогнать — падает**

Run: `uv run pytest tests/unit/test_presets.py -v`
Expected: FAIL — `ImportError: cannot import name 'CaptionPreset'`.

- [ ] **Step 3a: Добавить CaptionPreset в models.py (после ClipEdit)**

```python
# app/models.py — после ClipEdit


class CaptionPreset(BaseModel):
    """Именованный пресет стиля субтитров (мини brand kit, спека §9)."""

    id: str
    name: str
    style: CaptionStyle
    highlight: HighlightStyle | None = None
```

- [ ] **Step 3b: Создать presets.py (пока только apply_preset)**

```python
# app/editor/presets.py
"""Style-пресеты (спека §9): apply_preset (PURE) + чтение/запись глобального presets.json."""

from __future__ import annotations

import json

from app.models import CaptionPreset, ClipEdit
from app.run import DATA_ROOT


def apply_preset(edit: ClipEdit, preset: CaptionPreset) -> ClipEdit:
    """Записать style+highlight пресета в captions клипа. Реплики не трогает. PURE."""
    captions = edit.captions.model_copy(update={"style": preset.style, "highlight": preset.highlight})
    return edit.model_copy(update={"captions": captions})


def _presets_path():
    return DATA_ROOT / "presets.json"


def list_presets() -> list[CaptionPreset]:
    path = _presets_path()
    if not path.exists():
        return []
    return [CaptionPreset.model_validate(x) for x in json.loads(path.read_text(encoding="utf-8"))]


def save_preset(preset: CaptionPreset) -> CaptionPreset:
    """Добавить/заменить пресет по id, записать файл."""
    items = [p for p in list_presets() if p.id != preset.id]
    items.append(preset)
    _presets_path().parent.mkdir(parents=True, exist_ok=True)
    _presets_path().write_text(
        json.dumps([p.model_dump() for p in items], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return preset


def get_preset(preset_id: str) -> CaptionPreset | None:
    return next((p for p in list_presets() if p.id == preset_id), None)
```

- [ ] **Step 4: Прогнать — проходит + регенерировать типы**

Run: `uv run pytest tests/unit/test_presets.py -v` → PASS (1 passed).
Run (из корня): `just types` → `CaptionPreset` появился в TS; повторный `just types` без diff.

- [ ] **Step 5: Коммит**

```
git add services/worker/app/models.py services/worker/app/editor/presets.py services/worker/tests/unit/test_presets.py packages/shared
git commit -F <msg>   # feat(editor): CaptionPreset + apply_preset + presets store
```

---

### Task E5.2: Preset-эндпоинты (main.py)

**Files:**
- Modify: `services/worker/app/main.py`
- Test: `services/worker/tests/unit/test_editor_api.py` (добавить тест)

- [ ] **Step 1: Добавить падающий тест**

```python
# дополнить tests/unit/test_editor_api.py
def test_preset_save_and_apply(monkeypatch, tmp_path):
    from app.editor import presets
    monkeypatch.setattr(presets, "DATA_ROOT", tmp_path / "data")
    client, job = _client(monkeypatch, tmp_path)
    saved = client.post("/presets", json={"name": "Bold", "style": {"color": "#00FF00"}, "highlight": None})
    assert saved.status_code == 200
    pid = saved.json()["id"]
    v = client.get(f"/jobs/{job}/clips/clip_01/edit").json()["version"]
    r = client.post(f"/jobs/{job}/clips/clip_01/apply-preset", json={"version": v, "preset_id": pid})
    assert r.status_code == 200
    assert r.json()["captions"]["style"]["color"] == "#00FF00"
```

- [ ] **Step 2: Прогнать — падает**

Run: `uv run pytest tests/unit/test_editor_api.py::test_preset_save_and_apply -v`
Expected: FAIL — 404/405.

- [ ] **Step 3: Добавить эндпоинты в main.py**

```python
# app/main.py — импорты (uuid уже импортирован в main.py — используем его):
from app.editor import presets as presets_mod
from app.models import CaptionPreset, CaptionStyle, HighlightStyle


# app/main.py — тела + эндпоинты:


class SavePresetBody(BaseModel):
    name: str
    style: CaptionStyle
    highlight: HighlightStyle | None = None


class ApplyPresetBody(BaseModel):
    version: int
    preset_id: str


@app.get("/presets")
def get_presets() -> list[dict[str, Any]]:
    return [p.model_dump() for p in presets_mod.list_presets()]


@app.post("/presets")
def create_preset(body: SavePresetBody) -> dict[str, Any]:
    preset = CaptionPreset(
        id=f"preset_{uuid.uuid4().hex[:8]}", name=body.name, style=body.style, highlight=body.highlight
    )
    return presets_mod.save_preset(preset).model_dump()


@app.post("/jobs/{job_id}/clips/{clip_id}/apply-preset")
def apply_preset_to_clip(job_id: str, clip_id: str, body: ApplyPresetBody) -> dict[str, Any]:
    preset = presets_mod.get_preset(body.preset_id)
    if preset is None:
        raise HTTPException(status_code=404, detail="preset not found")
    edit = _load_or_404(job_id, clip_id)
    return _save_or_409(job_id, clip_id, presets_mod.apply_preset(edit, preset), body.version)
```

- [ ] **Step 4: Прогнать — проходит**

Run: `uv run pytest tests/unit/test_editor_api.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Гейт + коммит**

Run (из корня): `just check` → зелёный.

```
git add services/worker/app/main.py services/worker/tests/unit/test_editor_api.py
git commit -F <msg>   # feat(editor): preset endpoints (save/list/apply)
```

**DoD фазы E5:** `apply_preset` (pure) + preset-store + эндпоинты покрыты; `just check` зелёный.

---

## Phase E6 — Реальная e2e-проверка + обновление доков

**Результат фазы:** на реальном `comedy01` ($0, кэш) подтверждаем, что мульти-интервальный
рендер из edit-state даёт валидный mp4 с синхронным аудио; обновляем HANDOFF/журнал.

### Task E6.1: Реальный мульти-интервальный рендер (comedy01)

**Files:**
- Create: `services/worker/tmp/e2e_editor_render.py` (gitignored tmp)

- [ ] **Step 1: Написать e2e-скрипт**

```python
# services/worker/tmp/e2e_editor_render.py
"""E2E: trim → дырка → render_timeline на comedy01 (кэш, $0). Проверяет длительности."""

import subprocess

from app import db
from app.config import get_settings
from app.editor import store
from app.editor.captions_v2 import write_caption_ass
from app.editor.ops import apply_trim
from app.editor.reframe_cache import analyze_source_range, resolve_regions
from app.editor.timemap import ClipTimeMap
from app.models import Transcript
from app.pipeline.stage0_import import SourceMeta
from app.pipeline.stage5_render import render_timeline
from app.run import DATA_ROOT

JOB, CLIP = "comedy01", "clip_01"
db.init_db()
edit = store.ensure_edit(JOB, CLIP)  # дефолт: один интервал
words = store.load_transcript_words(JOB)
mid_reply = edit.captions.replies[len(edit.captions.replies) // 2]
edit2 = apply_trim(edit, mid_reply.word_refs, words)  # вырезать середину → дырка
assert len(edit2.source_intervals) >= 2, "trim не создал дырку"
edit2 = store.save_edit(JOB, CLIP, edit2, expected_version=edit.version)

s = get_settings()
out = DATA_ROOT / JOB
meta = SourceMeta.model_validate_json((out / "meta.json").read_text("utf-8"))
tr = Transcript.model_validate_json((out / "transcript.json").read_text("utf-8"))
raw = [
    analyze_source_range(out / "source.mp4", iv.source_start, iv.source_end,
        cache_dir=out / "analysis", fps=s.reframe_face_fps, cut_threshold=s.reframe_cut_threshold)
    for iv in edit2.source_intervals
]  # fmt: skip
regions = resolve_regions(edit2.source_intervals, raw, edit2.reframe_overrides,
    src_w=meta.width, src_h=meta.height, smoothing=s.reframe_smoothing,
    min_hold_sec=s.reframe_min_hold_sec, mode_setting=s.reframe_mode, wide_ratio=s.reframe_wide_ratio)  # fmt: skip
cmap = ClipTimeMap(edit2.source_intervals)
write_caption_ass(edit2.captions, tr.words, cmap, out / f"captions_{CLIP}.ass")
lat = render_timeline(out, "source.mp4", edit2.source_intervals, regions,
    f"captions_{CLIP}.ass", f"clips/{CLIP}_edited.mp4",
    src_w=meta.width, src_h=meta.height, fps=meta.fps, engine=s.reframe_engine)  # fmt: skip

mp4 = out / f"clips/{CLIP}_edited.mp4"


def _dur(stream: str) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", stream, "-show_entries",
         "stream=duration", "-of", "default=nw=1:nk=1", str(mp4)],
        capture_output=True, text=True,
    )  # fmt: skip
    return float(r.stdout.strip())


expected = cmap.clip_duration
vd, ad = _dur("v:0"), _dur("a:0")
print(f"intervals={len(edit2.source_intervals)} expected={expected:.2f} video={vd:.2f} audio={ad:.2f} render={lat}s")
assert abs(vd - expected) < 0.3, f"видео {vd} != ожидаемо {expected}"
assert abs(ad - vd) < 0.2, f"аудио {ad} рассинхрон с видео {vd}"
print("E6 OK: мульти-интервальный рендер из edit-state, аудио синхронно, дырка вырезана")
```

- [ ] **Step 2: Прогнать (PowerShell, PATH-refresh, из services/worker)**

```powershell
$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
Set-Location "C:\Users\user\Desktop\ClipClow\services\worker"
uv run python tmp/e2e_editor_render.py
```
Expected: печатает `E6 OK: …`; `intervals=2` (или больше), `expected≈video≈audio` (расхождения < 0.3с).
Если ассерт падает на длительностях — стык интервалов/frame-align (E2): проверить `build_timeline_filter`.

- [ ] **Step 3: Глазами проверить mp4 (фаундер/ты)**

Открыть `services/worker/data/comedy01/clips/clip_01_edited.mp4`: на стыке вырезанного куска
нет чёрного кадра/щелчка аудио; субтитры с караоке-подсветкой; кадр следит за лицом.

- [ ] **Step 4: Коммит (скрипт gitignored — коммитим только если не под ignore)**

Если `tmp/` под `.gitignore` (так и есть) — коммитить нечего; зафиксируй результат в журнале (E6.2).

---

### Task E6.2: (опц.) Полный HTTP-флоу через запущенный воркер

- [ ] **Шаги (PowerShell):** поднять воркер (`uv run uvicorn app.main:app --port 8000`), затем:

```powershell
$base = "http://localhost:8000/jobs/comedy01/clips/clip_01"
$edit = Invoke-RestMethod "$base/edit"                                  # GET → дефолт
Invoke-RestMethod "$base/edit/trim" -Method Post -ContentType application/json `
  -Body (@{version=$edit.version; word_indices=@(10,11,12)} | ConvertTo-Json)
$edit = Invoke-RestMethod "$base/edit"
Invoke-RestMethod "$base/render" -Method Post                           # запустить рендер
Start-Sleep 8; Invoke-RestMethod "$base/render"                         # GET статус → done + video_url
```
Expected: trim возвращает 2+ интервала; render → `status=done`, `video_url=media/comedy01/clips/clip_01.mp4`.

---

### Task E6.3: Обновить HANDOFF + журнал CLAUDE.md

**Files:**
- Modify: `docs/HANDOFF.md`, `CLAUDE.md` (журнал)

- [ ] **Step 1:** В `docs/HANDOFF.md` добавить раздел «Editor Core (MVP) — СДЕЛАН»: новый пакет
  `app/editor/`, контракт `ClipEdit`, editor-эндпоинты, мульти-интервальный `render_timeline`,
  лениво создаваемые edit-доки. Указать: правки = $0 (нет Deepgram/Gemini).
- [ ] **Step 2:** В `CLAUDE.md` журнал — строка «что сделано + чем доказано» (e2e на comedy01).
- [ ] **Step 3: Финальный гейт + коммит**

Run (из корня): `just check` → зелёный.
```
git add docs/HANDOFF.md CLAUDE.md
git commit -F <msg>   # docs: editor core MVP done (HANDOFF + journal)
```

**DoD фазы E6:** `e2e_editor_render.py` печатает `E6 OK` (длительности сходятся, аудио синхронно);
mp4 проверен глазами; HANDOFF/журнал обновлены; `just check` зелёный.

---

## Итоговый DoD всего ядра (спека §14)

На comedy01 (кэш, $0) через API/скрипт:
1. ✅ `GET …/edit` отдаёт валидный дефолт-`ClipEdit` на каждый клип (лениво создан).
2. ✅ `trim` (удалить реплику) → дырка; `add-section` → 2 интервала.
3. ✅ `render` → mp4: длительность = Σ интервалов; аудио синхронно; стык без чёрного кадра/подлага.
4. ✅ Субтитры: стиль из `CaptionStyle`, караоке `\k`, отредактированный текст.
5. ✅ Ручной кроп-override меняет кадр на диапазоне.
6. ✅ Пресет применяется к клипу.
7. ✅ `just check` зелёный; новые pure-функции покрыты; правки = $0 (нет вызовов Deepgram/Gemini).

## Карта «спека → задачи» (self-review coverage)

| Спека § | Задача(и) |
|---|---|
| §3 Контракты | E0.1, E5.1 (CaptionPreset) |
| §4 ClipTimeMap | E0.2 |
| §4.1 PURE-операции + sync реплик | E0.3 (rebuild_replies), E4.1 (trim/extend/add/crop) |
| §5 Reframe-decoupling + кэш | E1.1 (resolve_regions), E1.2 (analyze_source_range) |
| §6 render_timeline | E2.1 (билдеры), E2.2 (рендер) |
| §7 Субтитры v2 (караоке) | E3.1 |
| §8 API | E4.4 (edit/ops/render/analysis), E5.2 (presets) |
| §9 Пресеты | E5.1, E5.2 |
| §10 Персистентность | E4.2 (db+store); §10-эагерный run.py → лениво (E4 отклонение) |
| §11 Фазы | E0–E6 |
| §12 Контракты фронта | E4.4 (analysis/edit/render) |
| §14 DoD | E6 |
