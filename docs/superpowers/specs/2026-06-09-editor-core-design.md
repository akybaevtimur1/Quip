# ClipFlow — Editor Core (MVP) — дизайн-спека

> Статус: **DRAFT, на ревью фаундера** (2026-06-09).
> Это спека ЯДРА редактора (post-generation editing), не реализация. Из неё дальше
> рождается пошаговый implementation-план (writing-plans) для исполнения Sonnet-ом.
> Читать вместе с `docs/HANDOFF.md` (текущее состояние Phase 0).

## 0. TL;DR

Сейчас ClipFlow — **batch-конвейер в одну сторону**: ссылка → готовые 9:16-mp4 с
прожжёнными субтитрами. Править нечего.

Цель этого ядра — добавить **post-generation редактор** (главная ценность OpusClip):
после AI-нарезки юзер дорабатывает каждый клип до publish-ready. MVP-ядро = 6 слоёв:
edit-state модель + превью-фундамент, редактор субтитров (стиль+текст+караоке),
ручная reframe-коррекция, transcript-trim, style-пресеты, экспорт.

**Главное архитектурное решение:** правка **не-деструктивна**. Клип — это не вырезанный
файл, а **рецепт** (`ClipEdit`): «проиграй вот эти куски исходника, с такими субтитрами,
с таким кропом». Финальный mp4 собирается из рецепта **только на рендере/экспорте**.
Исходник и транскрипт всего видео хранятся всегда → можно нацелить рецепт на **любой**
момент видео, в любом порядке, с любыми дырками — машина просто читает кадры по рецепту.

---

## 1. Контекст и границы

### 1.1 Что есть сейчас (Phase 0, см. HANDOFF)
- `download → transcribe(весь source) → LLM select → reframe 9:16 → captions ASS → render`.
- `ClipOut.video_url` → готовый mp4. Субтитры/кроп прожжены за один проход ffmpeg.
- Субтитры — один захардкоженный стиль (`stage4_captions.py`).
- Worker — fire-and-forget: `POST /jobs` → фон → `GET /jobs` отдаёт ссылки. Нет правок/пере-рендера.
- `ClipOut` УЖЕ несёт `words: list[Word]` — заложено под trim-редактор (используем).

### 1.2 Зафиксированные продуктовые решения (фаундер, 2026-06-09)
| Решение | Выбор |
|---|---|
| Границы клипа за пределы AI-сегмента (extend / add-section) | **ДА**, клип = окно в исходник |
| Transcript-trim (удалить слова = вырезать кусок) | **ДА, в MVP** |
| Потолок субтитров | **Стиль + правка текста + караоке-хайлайт** |
| Соотношения сторон | **Только 9:16** (модель ratio-aware на будущее) |

### 1.3 В scope MVP-ядра
1. Edit-state модель (`ClipEdit`) + контракты.
2. Рендер из edit-state (мульти-интервальный таймлайн).
3. Reframe-decoupling: анализ по диапазону source + кэш; ручной кроп-override.
4. Transcript-trim + extend + add-section (всё через `source_intervals`).
5. Субтитры v2: стиль, правка текста реплик, караоке (`\k`).
6. Style-пресеты (мини brand kit).
7. Editor API + персистентность; пере-рендер/экспорт.

### 1.4 ВНЕ scope (YAGNI; отдельными спеками позже)
- B-roll (stock/AI), загрузка своих медиа, музыка/громкость/удаление пауз.
- Top/hook text-оверлеи, CTA/lower-thirds, intro/outro.
- Соотношения 1:1 / 16:9, SRT/XML-экспорт.
- Auth, пейволл, водяной знак, биллинг/кредиты.
- Перевыбор моментов ИИ из редактора (`reselect`) — оставляем **seam**, не реализуем.
- Клиент-side превью-движок (рендер оверлеев в браузере) — это **дизайн-слой**, делается
  отдельно поверх готового бэка; здесь только резервируем контракты, которые ему нужны.

---

## 2. Архитектура: три слоя

Ключ к «ничего не ломается» — разделить **анализ**, **выбор** и **композицию**.

### Слой 1 — АНАЛИЗ (на весь исходник, считается один раз, кэшируется)
- **Транскрипт** (`transcript.json`) — слова всего видео с word-level таймингами. Уже есть.
  Транскрипция **никогда** не гоняется повторно при правках.
- **Reframe-анализ** (трек лиц + детект склеек) — локальный CPU, **$0**. Сейчас считается
  на сегмент внутри `reframe_segment`. **Отвязываем** от границ клипа: считаем для
  *диапазона исходника* и кэшируем по диапазону (см. §5).

### Слой 2 — ВЫБОР ИИ (один раз)
- `segments.json` — Gemini предложил моменты. После этого клипами владеет **редактор**.
- Перевыбор — отдельное явное действие; правка границ его НЕ триггерит и НЕ платит.

### Слой 3 — КОМПОЗИЦИЯ (то, что юзер правит) — сердце редактора
- `ClipEdit` — рецепт клипа (см. §3). И trim, и extend, и add-section — операции над
  **одним** списком `source_intervals`.

### 2.1 Почему ничего не ломается (гарантия по сценариям)
Потому что мы **никогда не выбрасываем сырьё** (весь `source.mp4` + весь транскрипт), а
reframe — **пере-запускаемая** локальная функция от диапазона source (не одноразовый прожог).
Клип — указатель в всегда-присутствующее сырьё.

| Правка | Что пересчитывается | Платный API |
|---|---|---|
| Сдвинуть / растянуть границу | reframe-анализ нового куска source (CPU, кэш) | **НЕТ** |
| Добавить секцию из др. места | reframe-анализ этого диапазона | **НЕТ** |
| Удалить слова (trim → дырка) | ничего; рендер пропускает диапазон | **НЕТ** |
| Стиль / текст / караоке субтитров | пересборка ASS | **НЕТ** |
| Ручной кроп на сцене | override поверх анализа | **НЕТ** |
| Пере-рендер / экспорт | сборка mp4 из edit-state | **НЕТ** (CPU) |
| *(seam)* Перевыбор моментов ИИ | Gemini заново | ДА |
| Новый исходник (новый job) | Deepgram + Gemini | ДА |

Инвариант: **редактирование никогда не зовёт Deepgram/Gemini.** Платный API — только при
явном «перегенерировать» или новом источнике.

---

## 3. Контракты (модель данных)

Всё — в `app/models.py` (единый источник типов → codegen в `@clipflow/shared`). Времена —
секунды (float). `source_*` — координаты ИСХОДНИКА; clip-время — производное (см. §4).

```python
class SourceInterval(BaseModel):
    """Один оставленный кусок исходника. Упорядочены по clip-порядку (не обязательно по source)."""
    source_start: float        # сек в координатах source
    source_end: float          # сек; source_end > source_start

class CropOverride(BaseModel):
    """Ручной кроп на диапазон source — поверх авто-reframe-анализа."""
    source_start: float
    source_end: float
    mode: str                  # "fill" | "fit"
    center: float | None = None  # центр кропа [0..1] для fill; None = центр кадра

class CaptionStyle(BaseModel):
    font: str = "Montserrat"
    size: int = 90
    color: str = "#FFFFFF"           # основной цвет текста
    outline_color: str = "#000000"
    outline_w: int = 6
    shadow: int = 2
    box_color: str | None = None     # фон-плашка; None = без плашки
    box_opacity: float = 0.0
    box_radius: int = 0
    margin_v: int = 260              # позиция от низа (ASS MarginV)
    alignment: int = 2               # ASS alignment (2 = низ-центр)
    uppercase: bool = True

class HighlightStyle(BaseModel):
    """Караоке-подсветка активного слова. None в треке = караоке выключено."""
    color: str = "#FFE000"
    scale: float = 1.0               # 1.0 = без увеличения активного слова

class CaptionReply(BaseModel):
    """Одна реплика субтитра (чанк 3–5 слов)."""
    word_refs: list[int]             # индексы в transcript.words → тайминги (для караоке)
    text_override: str | None = None # если юзер правил текст реплики
    hidden: bool = False             # скрыть субтитр, видео не трогая

class CaptionTrack(BaseModel):
    style: CaptionStyle
    highlight: HighlightStyle | None = None
    replies: list[CaptionReply]

class ClipEdit(BaseModel):
    """РЕЦЕПТ клипа. Не-деструктивный edit-state. Версионируется (optimistic-lock)."""
    id: str                          # = clip_id (clip_01…)
    version: int = 1
    source_intervals: list[SourceInterval]
    captions: CaptionTrack
    reframe_overrides: list[CropOverride] = Field(default_factory=list)
    aspect: str = "9:16"
    # производное (не хранится): clip_duration = sum(i.source_end - i.source_start)
```

**Замечания по контракту:**
- `word_refs` ссылаются на индексы `transcript.words` (весь транскрипт), а не копируют слова.
  Это держит тайминги для караоке и для пере-маппинга при trim, без дублирования.
- `text_override` меняет отображаемый текст, не трогая `word_refs` (тайминги живут).
- Цвета — `#RRGGBB` в модели; в ASS конвертируются в `&HBBGGRR` (порядок BGR) в компиляторе.

---

## 4. Clip-time ↔ source-time mapping (ЕДИНАЯ точка таймингов)

Самая важная PURE-функция. Все ошибки «±длина клипа / съехавшие субтитры» живут только здесь.

Дано: упорядоченные интервалы `I_0..I_{n-1}`, `I_k = [s_k, e_k]`, длина `L_k = e_k - s_k`.
Clip-полосы: начало полосы `k` = `C_k = L_0 + … + L_{k-1}`; полоса `k` = `[C_k, C_k + L_k)`.
`clip_duration = Σ L_k`.

```python
class ClipTimeMap:
    """Кусочно-линейное отображение clip-время ↔ source-время по интервалам."""
    def source_to_clip(self, t_src: float) -> float | None:
        # найти интервал, содержащий t_src → C_k + (t_src - s_k); в дырке → None (слово выпадает)
    def clip_to_source(self, t_clip: float) -> tuple[int, float]:
        # найти полосу → (k, s_k + (t_clip - C_k))
    def interval_clip_band(self, k: int) -> tuple[float, float]:
        # (C_k, C_k + L_k) — для рендера и компиляции субтитров
```

- Это **обобщение** существующего `to_clip_time` (которое = частный случай 1 интервала).
- Слова в дырках (`source_to_clip → None`) не попадают в субтитры — корректно (их вырезали).
- Покрывается unit-тестами первым: 1 интервал, 2 интервала с дыркой, add-section
  (интервалы не по возрастанию source), границы полос, точка ровно на стыке.

### 4.1 Операции редактирования (PURE-трансформы над `ClipEdit`)

Вся «опасная» интервальная математика — в ОДНОМ месте (`app/editor/ops.py`), PURE, под
тестами. API дёргает их сервер-сайд → НЕ дублируем в TS-фронте (нет дрейфа на headline-фиче).
Каждая операция возвращает НОВЫЙ `ClipEdit` (инкремент `version` делает API при персисте).

```python
def apply_trim(edit, word_indices, words) -> ClipEdit:
    # слова W → их source-диапазон [min start, max end] → выколоть из source_intervals
    # (split/shrink интервалов) → rebuild_replies. Это и есть «удалить из транскрипта = вырезать видео».
def apply_extend(edit, *, edge: str, new_value: float) -> ClipEdit:
    # edge="start": подвинуть source_start ПЕРВОГО интервала; "end": source_end ПОСЛЕДНЕГО → rebuild_replies
def add_section(edit, source_start, source_end, at_index, words) -> ClipEdit:
    # вставить SourceInterval на позицию at_index в таймлайне → rebuild_replies
def set_crop_override(edit, override: CropOverride) -> ClipEdit:
    # добавить/заменить ручной кроп на диапазоне source
def rebuild_replies(words, intervals, *, max_words, max_gap, max_dur,
                    keep: list[CaptionReply] | None = None) -> list[CaptionReply]:
    # перегруппировать слова, ПОПАДАЮЩИЕ в интервалы (вне интервалов — выкинуть);
    # переиспользует group_words_into_chunks; сохраняет text_override у реплик с НЕизменившимся word_refs
```

**Caption-sync правило (убирает неоднозначность):** структурные правки интервалов
(trim/extend/add-section) ВСЕГДА перестраивают `captions.replies` через `rebuild_replies`.
Ручной `text_override` сохраняется для реплик, чьи `word_refs` не изменились; в изменившихся
регионах — сбрасывается. Детерминированно. Стиль/highlight/прямую правку текста реплики делает
`PATCH …/edit` (не трогает интервалы).

---

## 5. Reframe-decoupling + кэш анализа

### 5.1 Что кэшируем
Дорогая часть reframe — **сэмплинг лиц (ffmpeg+MediaPipe) и детект склеек (ffmpeg scene)**.
Дешёвая — построение `TrackRegion` (PURE). Кэшируем **дорогую (сырую) часть**, регионы
строим на лету (потому что они зависят от границ интервалов, которые юзер двигает).

```
data/<job>/analysis/reframe_<src0>_<src1>.json   # ключ = округлённый source-диапазон
  { "faces": [{t, [[cx,w],...]}, ...], "cuts": [t, ...] }   # t — source-relative
```

`analyze_source_range(source, src_start, src_end) -> RawReframe` — I/O, load-or-compute
(если файл есть — читаем, нет — считаем и пишем). Округление ключа (напр. до 0.1с)
делает повторные правки кэш-хитами.

### 5.2 Построение регионов (PURE)
```python
def resolve_regions(
    intervals: list[SourceInterval],
    raw_by_interval: list[RawReframe],     # сырой анализ на каждый интервал
    overrides: list[CropOverride],
    *, crop_w_frac, smoothing, min_hold_sec, wide_ratio, dead_zone,
) -> list[list[TrackRegion]]:              # регионы на каждый интервал, в interval-relative времени
```
- Внутри интервала — текущий cut-aligned пайплайн (`build_shots → decide_shot_mode →
  build_shot_trajectory → build_regions_from_shots`). Переиспользуем как есть.
- **Граница интервала = forced-склейка** (между интервалами наведение не пытается плавно
  проехать). Это и закрывает «дырки/add-section не дёргают кадр».
- `CropOverride`, пересекающий интервал, заменяет авто-регион на ручной (`fill+center` или `fit`).

---

## 6. Рендер из edit-state (мульти-интервальный таймлайн)

`render_timeline(...)` обобщает текущий `render_clip` (который остаётся быстрым путём для
1 непрерывного интервала).

```python
def render_timeline(
    source: Path,
    intervals: list[SourceInterval],
    regions_per_interval: list[list[TrackRegion]],
    captions_ass: Path,                  # субтитры в КЛИП-времени
    *, aspect: str, src_w: int, src_h: int, fps: float,
    out_path: Path,
) -> float:                              # latency_s
```

**Граф ffmpeg (один декод, один энкод):**
- Для каждого интервала `i`:
  `[0:v]trim=start=s_i:end=e_i,setpts=PTS-STARTPTS` → reframe (crop/fit per region) →
  `setsar=1` → `[v_i]`;
  `[0:a]atrim=start=s_i:end=e_i,asetpts=N/SR/TB` → `[a_i]`.
- `concat=n=N:v=1:a=1` склеивает `[v_i][a_i]…` → `subtitles={ass}` → `[outv][outa]`.

**Инварианты (критично, из R1c/R1d уроков):**
- **Бесшовное аудио:** стыки аудио уезжают ВНУТРЬ filtergraph (concat по *декодированным*
  сэмплам, до энкода) → нет AAC-priming-подлага. Энкод один.
- **Frame-align:** границы интервалов выравниваем на границу кадра
  (`round(t * fps) / fps`) → trim-кадры точно на реальных кадрах, без чёрного кадра-флеша.
- `setsar=1` на каждом сегменте (fill/fit дают разный SAR → без него concat падает).
- fit-лейблы уникальны per-сегмент (`[bg{i}]`, `[fg{i}]`) — иначе коллизия на 2+ fit.
- **Быстрый путь:** ровно 1 интервал → текущий `render_clip` (аудио непрерывным `-map 0:a`).

**Переиспользуем** существующие PURE-билдеры: `build_fill_crop_expr(points, t0_offset,…)`
(t0_offset = clip-начало интервала из `ClipTimeMap.interval_clip_band`), fit-overlay билдеры.
Новое — обёртка мульти-интервального concat.

Engine A (filter_complex, default) и Engine B (cv2-pipe) — оба расширяются; B полезен как
frame-exact эталон в тестах. Output: `clips/<clip_id>.mp4` (перезапись = последний экспорт).

---

## 7. Субтитры v2 (компиляция из `CaptionTrack`)

Один источник правды (`CaptionTrack`) → компилируется в ASS **сейчас**, в CSS — **потом**
(превью). `compile_ass` — PURE, под тестами.

```python
def compile_ass(track: CaptionTrack, words: list[Word], cmap: ClipTimeMap) -> str: ...
```

- **Стиль** → ASS `[V4+ Styles]` (font/size/colors/outline/shadow/box/margin/alignment).
  `uppercase` → `.upper()` текста. Цвета `#RRGGBB → &HBBGGRR`.
- **Реплики:** для каждой `CaptionReply` (если не `hidden`):
  - тайминги слов из `words[word_refs]` → `source_to_clip` → клип-время начала/конца реплики;
  - текст = `text_override or " ".join(words)`.
- **Караоке (нативно в libass):** активное слово красится тегом `{\k<cs>}` (centiseconds на
  слово, из его клип-длительности). Подсветка = `highlight.color` как Primary, базовый =
  приглушённый. Покадровые PNG НЕ нужны.
  - Если `text_override` задан и число слов ≠ числу `word_refs` → реплика без караоке
    (показываем текст целиком на интервал реплики). Простое детерминированное правило.
- **Стартовый трек** генерим текущим `group_words_into_chunks` (переиспользуем) →
  `default_caption_track(words_in_segment)`.

---

## 8. API-поверхность (worker)

Добавляем к существующим `POST /jobs`, `GET /jobs/{id}`, `GET /healthz`, `/media/*`.

Разделение: **простые правки** (стиль/текст/highlight) — через `PATCH …/edit`;
**интервальные вербы** (trim/extend/add-section/crop) — через op-эндпоинты, которые применяют
PURE-трансформ из §4.1 сервер-сайд и персистят (интервальная математика в одном месте).

| Метод / путь | Делает | Стоимость |
|---|---|---|
| `GET /jobs/{j}/clips/{c}/edit` | Вернуть `ClipEdit` (нет → дефолт из сегмента) | $0 |
| `PATCH /jobs/{j}/clips/{c}/edit` | Прямые правки стиля/текста реплик/highlight + version. НЕ трогает интервалы, НЕ рендерит. 409 при version-mismatch | $0 |
| `POST …/edit/trim` `{word_indices}` | `apply_trim` → persist (новый `ClipEdit`) | $0 |
| `POST …/edit/add-section` `{source_start, source_end, at_index}` | `add_section` → persist | $0 |
| `POST …/edit/extend` `{edge, new_value}` | `apply_extend` → persist | $0 |
| `POST …/edit/crop` `{source_start, source_end, mode, center}` | `set_crop_override` → persist | $0 |
| `POST /jobs/{j}/clips/{c}/render` | Async-рендер mp4 из текущего edit-state. Возвращает render-status. | CPU |
| `GET /jobs/{j}/clips/{c}/render` | Статус рендера (`rendering`/`done`/`failed`) + `video_url` | $0 |
| `GET /jobs/{j}/clips/{c}/analysis` | reframe-регионы + слова + интервалы (для клиент-превью) | $0 |
| `GET /media/{j}/source.mp4` | Исходник (для превью клиента) | $0 |
| `GET /jobs/{j}/presets`, `POST …/presets`, `POST …/clips/{c}/apply-preset` | Style-пресеты (§9) | $0 |
| *(seam, НЕ MVP)* `POST /jobs/{j}/reselect` | Перевыбор моментов ИИ | Gemini |

- **Все правки мгновенные** (пишут JSON, инкрементят version). Если границы вылезли в
  неанализированный source — reframe досчитается **лениво на `render`** (compute-if-missing).
- **`render`** — единственное «дорогое» (CPU) действие; **явное** (юзер жмёт «применить/экспорт»).
- Рендер-конкурентность: для MVP — BackgroundTask + простой per-job лимит (RQ/Redis = K1, отложено).

---

## 9. Style-пресеты (мини brand kit)

```
data/<job>/presets.json    # или глобально data/presets.json (MVP: глобально, без auth)
  [ { "id": "...", "name": "Hormozi", "style": CaptionStyle, "highlight": HighlightStyle|None }, ... ]
```
- `POST /presets` — сохранить текущий стиль клипа как именованный пресет.
- `POST /clips/{c}/apply-preset` (или `apply-to-all`) — записать `style`+`highlight` в
  `ClipEdit.captions` клипа (или всех клипов job). PURE `apply_preset(edit, preset) -> ClipEdit`.
- MVP: только caption-стиль (не layout/logo/overlay — это V1).

---

## 10. Персистентность + сосуществование с пайплайном

- **SQLite**: новая таблица
  `clip_edits(job_id TEXT, clip_id TEXT, version INT, edit_json TEXT, updated_at, PK(job_id,clip_id))`.
  Зеркало в `data/<job>/clips/<clip_id>/edit.json` (консистентно с файловой культурой проекта;
  SQLite = источник правды для API, файл = для пайплайна/дебага).
- **Кэш анализа**: `data/<job>/analysis/reframe_<src0>_<src1>.json` (§5).
- **`run.py` меняется минимально:** после select на каждый сегмент пишем **дефолтный
  `ClipEdit`** (`default_clip_edit(segment, words)`) и рендерим **v1** (юзеру сразу есть что
  смотреть — первый AI-кат). Редактор дальше правит доки и пере-рендерит. Старый flow жив.
- **Миграция БД:** `db.init_db()` создаёт `clip_edits` идемпотентно (CREATE TABLE IF NOT EXISTS).

---

## 11. Фазы сборки (TDD + DoD как в CLAUDE.md; тест-первым на pure-логике)

| Фаза | Содержание | DoD (зелёный + показанный вывод) |
|---|---|---|
| **E0** | Контракты в `models.py` (§3) → `just types`. PURE: `ClipTimeMap` (§4), `default_clip_edit`, `default_caption_track` | unit-тесты ClipTimeMap (1/2/дырка/add-section); `just types` идемпотентен; `just check` зелёный |
| **E1** | Reframe-decoupling: `analyze_source_range` + кэш; PURE `resolve_regions` с overrides | тест resolve_regions (fill/fit/override/forced-cut на границе); кэш-хит не пересчитывает |
| **E2** | `render_timeline` (§6): мульти-интервал, бесшовное аудио, single-fast-path | реальный mp4 из 2 интервалов на comedy01: длительность = Σ интервалов ±0.1с; аудио-длит = видео-длит (нет подлага); нет чёрного кадра на стыке |
| **E3** | Субтитры v2 (§7): `CaptionTrack→ASS` с `\k`; text_override; переиспользуем grouping | тесты compile_ass (стиль, караоке-`\k`-тайминги, text_override без караоке, hidden, дырка выкидывает слово) |
| **E4** | PURE-операции §4.1 (`apply_trim`/`add_section`/`apply_extend`/`set_crop_override`/`rebuild_replies`) + Editor API/персистентность (§8,§10): `clip_edits`, edit.json, GET/PATCH/op-эндпоинты/render/analysis; `run.py` пишет дефолт-доки | unit-тесты операций (trim→дырка, add-section→2 интервала, sync реплик); e2e: GET edit → POST trim → POST add-section → POST render → новый mp4; version-mismatch → 409 |
| **E5** | Style-пресеты (§9) | тест `apply_preset` (pure) + apply-to-all меняет все clip_edits |
| **E6** | Интеграция/e2e на comedy01 ($0, кэш): trim + add-section + рестайл субтитров + ручной кроп + пере-рендер | визуальная проверка mp4 (фаундер); `just check` зелёный; `runs.jsonl` пишет latency рендера |

Каждая фаза: коммит на зелёный гейт, conventional commits, `just check` перед коммитом.

---

## 12. Что нужно фронту (контракты для дизайн-слоя позже)

Бэк строим первым, но резервируем то, что превью-редактор будет потреблять (чтобы дизайн лёг
без переделок бэка):
- `GET …/edit` — текущий `ClipEdit` (рисуем таймлайн интервалов, реплики, стиль).
- `GET …/analysis` — reframe-регионы + слова → клиент рисует кроп-рамку и субтитры поверх
  `source.mp4` для **мгновенного** превью (без серверного рендера на каждую правку).
- `POST/GET …/render` — «применить/экспорт» (серверный финальный mp4).
- Превью-консистентность: `CaptionStyle`/`HighlightStyle` спроектированы компилироваться И в
  ASS (рендер), И в CSS (превью) из одной модели — браузерное превью совпадает с финалом.

---

## 13. Риски и открытые вопросы

| Риск / вопрос | План |
|---|---|
| `text_override` + караоке при изменении числа слов | детерминированно: реплика без караоке (правило в §7) |
| Семантика ручного кропа (center vs полное окно) | бэк принимает `mode+center` (+scale на будущее); UI-семантику решаем на дизайн-слое |
| Двойные субтитры (вшитые в исходник) | известно, ВНЕ scope (R2) |
| Стоимость reframe-анализа при большом extend | ограничена длиной клипа (десятки сек), $0; кэш по диапазону |
| Конкурентные рендеры нескольких клипов | MVP: BackgroundTask + per-job лимит; очередь = K1 (отложено) |
| Аудио-стык на границе add-section (щелчок) | concat-фильтр по декодир. сэмплам + frame-align; при артефактах — короткий afade на стыке (тюнинг E2) |
| Длинные реплики после text_override | WrapStyle:0 (авто-перенос) уже в ASS; проверить на длинном override |

---

## 14. Definition of Done (всё ядро)

На comedy01 (кэш, $0) через API:
1. `GET edit` отдаёт валидный дефолт-`ClipEdit` на каждый клип.
2. `PATCH`: trim (удалить реплику) → дырка; add-section (интервал из др. места) → 2 интервала.
3. `POST render` → mp4: длительность = Σ интервалов; аудио синхронно; стык без чёрного кадра/подлага.
4. Субтитры: новый стиль применён, караоке подсвечивает активное слово, отредактированный текст виден.
5. Ручной кроп-override меняет кадр на заданном диапазоне.
6. Пресет применяется к одному клипу и ко всем.
7. `just check` зелёный; новые pure-функции покрыты тестами; экономика правок = $0 (никаких
   вызовов Deepgram/Gemini в логах при редактировании).
