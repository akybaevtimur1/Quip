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
