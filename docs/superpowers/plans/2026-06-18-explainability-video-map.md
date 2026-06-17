# Explainability + Video Map + Smart Cutting — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended)
> or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax. Spec (source of truth):
> `docs/superpowers/specs/2026-06-17-explainability-video-map.md`.

**Goal:** Make Quip's differentiator real — it *understands the whole video* and *explains why each
moment works* — via a Video Map (results page), an enriched topic strip with click-to-cut (editor),
a smarter agent (whole-video context + reliable bounds), and a 20s minimum clip length.

**Architecture:** A new fan-out Gemini pass builds a `VideoMap` (narrative + chapters + colored
"interesting moments" + clip cross-refs) from the transcript+segments, stored as a job artifact and
served via an endpoint (extends the existing `chapters` infra). The frontend renders it as a map
above the clip grid and as an expandable topic strip in the editor; both can click-to-cut (reusing
`setClipInterval`/`trim`). The agent gets a compact map summary + a 20s/source-bound clamp. Min clip
length 15→20 everywhere.

**Tech Stack:** Python/FastAPI worker, Modal, Gemini (google-genai, structured output), Next.js 16
(apps/web), Tailwind, pytest, vitest/tsc/eslint via `just check`.

---

## ⛔ Working constraints (овернайт-сессия — НЕ нарушать)

- **Работай ТОЛЬКО в ветке `feat/explainability-video-map`.** НЕ пушить и НЕ мержить в `main`
  НИЧЕГО, пока фаундер явно не скажет. Коммиты в ветку — да; push — НЕТ.
- **Используй саб-агентов** (домены D0–D4 ниже независимы по файлам — режь и гоняй параллельно;
  оркестратор коммитит и гоняет `just check`).
- **ВИЗУАЛЬНАЯ ПРОВЕРКА обязательна для КАЖДОГО фронт-таска:** через браузер (skill `browse`/`qa`
  или chrome-devtools) на ДЕСКТОПЕ И МОБИЛЕ (узкий вьюпорт ~390px). Ничего сломанного, не наезжает,
  адаптивно, tap-таргеты ≥40px. Скриншоты в отчёт. Это часть DoD.
- **Боевые тесты перед «готово»:** реально прогнать видео на задеплоенном (по запросу фаундера)
  воркере и проверить карту/строку/агента на настоящих данных. НЕ заявлять «работает» без этого.
- **Гейт:** `just check` зелёный перед КАЖДЫМ коммитом. `models.py` менялся → `just types`.
  Conventional commits, кириллица → файл + `git commit -F`.
- **НЕ трогать** reframe-инвариант (`stage3_reframe`/`stage5_render`/`reframe_cache` геометрию).
  Эта фича про СМЫСЛ/НАРЕЗКУ/UI, не про кадровую сетку.
- **Каждый коммит — `just check` зелёный**; падающий тест/ошибка не маскируется (правило №8).

---

## File Structure

**Backend (worker):**
- `services/worker/app/models.py` — +`VideoMap`, `VideoChapter`, `VideoMoment` (контракт → `just types`).
- `services/worker/app/editor/video_map.py` — NEW: pure-парсинг/валидация ответа Gemini → `VideoMap`;
  pure-хелперы (снап момента к словам, расширение до min-длины).
- `services/worker/app/prompts/video_map.v1.txt` — NEW: промпт Gemini для карты.
- `services/worker/app/editor/chapters.py` — переиспользовать Gemini-обвязку (клиент/ретраи) или
  вынести общее; не дублировать.
- `services/worker/app/tasks.py` — `generate_video_map_job(job_id)` (фон, статус, ретрай).
- `services/worker/app/run.py` — после select триггерить генерацию карты (фон, не блокирует клипы).
- `services/worker/app/main.py` — эндпоинт `GET /jobs/{id}/video-map` (+ retry), + агент-тул.
- `services/worker/app/config.py` — `clip_min_sec` 15→20.
- `services/worker/app/agent/tools.py` + `clip_agent.py` + `prompts/agent_clip_editor.v1.txt` —
  тул `get_video_map`, контекст видео в хук, надёжный кламп границ.
- `deploy/modal/worker.py` — `generate_video_map_job` как Modal-функция (фон).

**Frontend (apps/web):**
- `lib/api.ts` — `getVideoMap`, types.
- `components/VideoMap.tsx` — NEW: карта на странице результатов (адаптив, аккордеон на мобиле).
- `app/(app)/dashboard/page.tsx` — вставить `<VideoMap>` над `<ClipGrid>`.
- `components/editor/TopicStrip.tsx` — NEW: обогащённая строка тем в редакторе (раскрытие +
  цветные моменты + клик-обрезка).
- `components/editor/ClipEditorScreen.tsx` — вставить `<TopicStrip>` + обработчики клик-обрезки
  (переиспуют `setClipInterval`/`trimClip`).
- `components/editor/TimelineV2.tsx` — слайдер мин. длины = 20с.

---

## DOMAIN D0 — Минимальная длина клипа = 20с (изолированно, первым)

### Task D0.1 — config + select-промпт + слайдер
**Files:** `services/worker/app/config.py`, select-промпт в `services/worker/app/prompts/*` (найти
тот, что в stage2_select), `apps/web/components/editor/TimelineV2.tsx`, тест
`services/worker/tests/unit/test_ops.py` (или где тесты ops set_interval/trim).

- [ ] **Step 1 (test):** написать падающий тест, что `set_interval`/`trim` клампят длину к ≥20с.
  Найти существующие тесты ops (grep `set_interval` в tests). Пример:
```python
def test_set_interval_clamps_to_min_20s(...):
    edit = _edit_with_interval(100.0, 130.0)  # 30s
    new = set_interval(edit, 100.0, 110.0, words, duration=600, min_sec=20, max_sec=60)
    iv = new.source_intervals
    assert round(iv[-1].source_end - iv[0].source_start, 1) >= 20.0
```
- [ ] **Step 2:** прогнать — упадёт, если поведение/дефолт не 20.
- [ ] **Step 3:** `config.py`: `clip_min_sec: int = 20` (было 15). Проверить, что `set_interval`/`trim`
  получают `min_sec` из настроек везде (run.py/tasks.py/ops вызовы) — они уже передают `s.clip_min_sec`.
- [ ] **Step 4:** select-промпт (stage2): добавить требование «каждый клип ≥20с, не отдавай огрызки».
- [ ] **Step 5 (frontend):** `TimelineV2` слайдер/ручка интервала: минимальная длина ручки = 20с;
  попытка сделать короче → не даём + подсказка «Минимум 20с».
- [ ] **Step 6:** `uv run pytest tests/unit/test_ops.py -q` (PATH refresh) → PASS. `just check`.
- [ ] **Step 7 (визуальная проверка):** в браузере (десктоп+мобила) проверить, что слайдер не даёт
  <20с и подсказка видна. Скриншоты.
- [ ] **Step 8:** commit `feat(clip): минимальная длина клипа 20с (config + select + слайдер)`.

---

## DOMAIN D1 — Backend: VideoMap (основа для D3/D4)

### Task D1.1 — модель VideoMap (контракт)
**Files:** `services/worker/app/models.py`, затем `just types`.

- [ ] **Step 1:** добавить в `models.py`:
```python
class VideoMoment(BaseModel):
    start: float  # source seconds
    end: float
    label: str           # живой текст: «они начали спорить»
    why: str             # почему потенциально интересно
    kind: str            # tension|quote|emotional|insight|funny (→ цвет на фронте)

class VideoChapter(BaseModel):
    start: float
    end: float
    title: str
    summary: str         # что происходит в главе (кратко)
    clip_ids: list[str] = []   # какие наши клипы из этой главы
    moments: list[VideoMoment] = []

class VideoMap(BaseModel):
    status: str = "pending"   # pending|done|failed
    error: str | None = None
    narrative: str = ""       # связный разбор (может содержать [mm:ss] и [[clip:clip_03]])
    chapters: list[VideoChapter] = []
```
- [ ] **Step 2:** `just types` (PowerShell PATH refresh) → `packages/shared/src/types.ts` обновится.
  `git diff packages/shared` покажет новые типы.
- [ ] **Step 3:** `just check` зелёный (mypy/tsc).
- [ ] **Step 4:** commit `feat(models): VideoMap/VideoChapter/VideoMoment + codegen`.

### Task D1.2 — pure-парсинг ответа Gemini → VideoMap (TDD)
**Files:** `services/worker/app/editor/video_map.py` (NEW), `services/worker/tests/unit/test_video_map.py` (NEW).

- [ ] **Step 1 (test):** падающий тест `parse_video_map(raw: dict, segments, source_dur) -> VideoMap`:
  валидирует/клампит времена в [0, source_dur], отбрасывает кривые моменты, привязывает `clip_ids`
  по пересечению глав с интервалами клипов. Пример проверок: момент с end>source_dur клампится;
  глава, пересекающая интервал clip_02 → clip_ids содержит "clip_02"; пустой/битый raw → VideoMap
  со status failed (не падаем).
- [ ] **Step 2:** прогнать — упадёт (нет функции).
- [ ] **Step 3:** реализовать `parse_video_map` (PURE): нормализация, клампинг, привязка клипов
  (по пересечению `chapter[start,end]` с `segment[start,end]`), дефолты, без I/O.
- [ ] **Step 4:** `uv run pytest tests/unit/test_video_map.py -q` → PASS. `just check`.
- [ ] **Step 5:** commit `feat(video-map): pure-парсинг ответа Gemini в VideoMap (TDD)`.

### Task D1.3 — pure-хелперы клик-обрезки (TDD)
**Files:** `services/worker/app/editor/video_map.py`, `test_video_map.py`.

- [ ] **Step 1 (test):** `moment_to_interval(start, end, source_dur, words, min_sec=20) -> (s,e)`:
  если момент <20с — расширяет симметрично до 20с в пределах [0, source_dur]; снапит к границам слов
  (используй существующий снап из `editor/replies`/ops — изучить). Тесты: момент 14:30–14:40 (10с) →
  ≥20с; у конца видео расширяет влево; снап к словам.
- [ ] **Step 2:** прогнать — упадёт.
- [ ] **Step 3:** реализовать (PURE; переиспользовать снап-к-словам, не дублировать логику).
- [ ] **Step 4:** тесты PASS. `just check`. commit `feat(video-map): момент→интервал (≥20с, снап к словам)`.

### Task D1.4 — Gemini-генерация карты (I/O) + промпт
**Files:** `services/worker/app/prompts/video_map.v1.txt` (NEW), `services/worker/app/editor/video_map.py`
(функция `generate_video_map(transcript, segments, language) -> VideoMap`), переиспользовать
Gemini-клиент/ретраи из `chapters.py`/`stage2_select` (не дублировать).

- [ ] **Step 1:** написать промпт `video_map.v1.txt`: на ВХОДЕ индексированный транскрипт + список
  выбранных клипов (интервалы); на ВЫХОДЕ structured JSON под `VideoMap` (narrative + chapters +
  moments + clip_ids). Язык вывода = язык видео. Инструкции: тайм-коды как [mm:ss]; моменты —
  короткий живой `label` + `why` + `kind`; не выдумывать факты вне транскрипта.
- [ ] **Step 2:** реализовать `generate_video_map` (I/O-обёртка Gemini, structured output, ретраи как
  в select) → сырой dict → `parse_video_map` (D1.2). JobError при неретраябельном сбое.
- [ ] **Step 3:** ручной спот-чек (по запросу фаундера на боевом видео) — отложить до боевых тестов.
- [ ] **Step 4:** `just check`. commit `feat(video-map): генерация карты Gemini + промпт v1`.

### Task D1.5 — фон-джоб + эндпоинт + триггер
**Files:** `services/worker/app/tasks.py` (`generate_video_map_job`), `services/worker/app/main.py`
(`GET /jobs/{id}/video-map` + `?retry=true`), `services/worker/app/run.py` (триггер после select,
фон), `deploy/modal/worker.py` (Modal-функция), хранение артефакта (как chapters: файл/Postgres).

- [ ] **Step 1:** `generate_video_map_job(job_id)`: грузит transcript+segments+meta (artifacts),
  зовёт `generate_video_map`, сохраняет VideoMap-артефакт (по образцу `chapters` save/load);
  падение → status failed с причиной (правило №8). Зеркалит структуру `generate_chapters_job`.
- [ ] **Step 2:** `run.py`: после select (когда известны segments) — НЕ блокируя клипы — поставить
  генерацию карты (на Modal — spawn `generate_video_map_job`; локально — фон/inline). Сохранить
  artefact в R2/Postgres так же, как meta/segments.
- [ ] **Step 3:** `main.py`: `GET /jobs/{id}/video-map` → отдать VideoMap (pending/done/failed),
  `?retry=true` перезапускает (как `/chapters`).
- [ ] **Step 4:** `deploy/modal/worker.py`: добавить `generate_video_map_job` Modal-функцию (cpu=2,
  serialized, секреты) по образцу существующих.
- [ ] **Step 5:** `just check`. commit `feat(video-map): фон-джоб + эндпоинт /video-map + триггер`.

---

## DOMAIN D2 — Умный агент (контекст видео + надёжные границы)

### Task D2.1 — кламп границ у конца видео + мин. 20с (TDD)
**Files:** `services/worker/app/agent/tools.py` (если есть pure-часть) или `app/editor/ops.py`,
`services/worker/tests/unit/test_agent_tools.py`.

- [ ] **Step 1 (test):** воспроизвести «двинь на 10с вперёд у конца видео»: интервал близко к концу,
  сдвиг +10с → end НЕ превышает source_dur, длина сохраняется ≥20с; вернуть флаг «clamped», чтобы
  агент честно сообщил. Тест на pure `compute_nudge` + кламп-обёртку.
- [ ] **Step 2:** прогнать — упадёт, если клампинг недостаточен.
- [ ] **Step 3:** починить клампинг (pure) так, чтобы сдвиг у конца не ломал длину и не вылетал за
  source; тул возвращает в summary, что упёрлись (для `respond_to_user`).
- [ ] **Step 4:** тесты PASS. `just check`. commit `fix(agent): надёжный кламп границ у конца видео + 20с`.

### Task D2.2 — контекст всего видео для агента
**Files:** `services/worker/app/agent/tools.py` (тул `get_video_map`), `clip_agent.py` (`_FN_DECLS` +
промпт), `app/editor/hook_ops.py` (хук с контекстом видео — опц. сводка карты).

- [ ] **Step 1:** тул `get_video_map(job_id)` → компактная сводка VideoMap (главы+краткое+моменты,
  без раздувания контекста). Зарегистрировать в `_DISPATCH` + `_FN_DECLS`.
- [ ] **Step 2:** промпт агента: «для "переделай хук с учётом всего видео" вызови `get_video_map`».
- [ ] **Step 3:** `hook_ops.regenerate_hook_for_clip`: опц. принимать сводку видео для лучшего хука.
- [ ] **Step 4:** тесты pure-частей (если есть). `just check`. commit `feat(agent): контекст всего видео (get_video_map) + хук с учётом видео`.

> Боевой сценарий для проверки (на боевых тестах): «не нравится хук — глянь о чём видос и переделай
> в POV; обрезка резкая (начинает со слова "кстати") — поправь; сделай клип подлиннее» → агент:
> `get_video_map` → `get_surrounding_transcript` (найти "кстати") → `set_interval` (длиннее, ≥20с,
> старт после "кстати") → `regenerate_hook(pov, с контекстом)` → `request_render` → `respond_to_user`.

---

## DOMAIN D3 — Frontend: Карта видео (страница результатов)

### Task D3.1 — API + компонент VideoMap
**Files:** `apps/web/lib/api.ts` (`getVideoMap`), `apps/web/components/VideoMap.tsx` (NEW),
`apps/web/app/(app)/dashboard/page.tsx` (вставка над `<ClipGrid>`).

- [ ] **Step 1:** `getVideoMap(jobId)` в `lib/api.ts` (как `getChapters`: поллинг pending→done,
  `?retry`). Типы из codegen (`@clipflow/shared`).
- [ ] **Step 2:** `VideoMap.tsx`: рендер нарратива (тайм-коды [mm:ss] → кликабельны; `[[clip:..]]` →
  ссылка на клип/редактор) + аккордеон глав (title, summary, цветные моменты по `kind`). Кнопки на
  моменте: «Подвинуть текущий клип сюда» и «Сделать новый клип» (см. спек §8 решение 1).
  Состояния: pending (скелетон/«AI читает видео…»), failed (+retry), done.
- [ ] **Step 3:** адаптив: на мобиле карта СВЁРНУТА по умолчанию (аккордеон), tap-таргеты ≥40px,
  тайм-коды переносятся, ничего не наезжает на грид.
- [ ] **Step 4:** вставить `<VideoMap jobId=.../>` над `<ClipGrid>` в dashboard (phase done).
- [ ] **Step 5 (ВИЗУАЛЬНО, обязательно):** браузер десктоп (≥1280px) И мобила (~390px): карта
  читается, аккордеон работает, клики по тайм-кодам/клипам ведут куда надо, pending/failed выглядят
  ок. Скриншоты обоих в отчёт.
- [ ] **Step 6:** `just check`. commit `feat(web): карта видео на странице результатов (адаптив)`.

---

## DOMAIN D4 — Frontend: обогащённая строка тем (редактор)

### Task D4.1 — TopicStrip + клик-обрезка
**Files:** `apps/web/components/editor/TopicStrip.tsx` (NEW),
`apps/web/components/editor/ClipEditorScreen.tsx` (вставка + обработчики).

- [ ] **Step 1:** `TopicStrip.tsx`: главы из VideoMap, раскрытие → summary + цветные моменты
  (`kind`→цвет, живой `label`). Кнопки на моменте: «Подвинуть клип сюда»/«Новый клип». Различать
  визуально от `FitTimeline` (заголовок «Темы видео», иконка) — текущая претензия «непонятно/путаю».
- [ ] **Step 2:** обработчики в `ClipEditorScreen`: «подвинуть» → `setClipInterval(jobId,clipId,v,
  s,e)` (интервал из `moment_to_interval`, ≥20с) + reload (как `handleSetInterval`); «новый клип» —
  по спеку (создать клип/черновик — уточнить минимальный путь: можно открыть новый `/edit` с
  предустановленным интервалом через стартовый override, либо явный backend-эндпоинт «clone clip
  with interval» — выбрать минимально-инвазивный; если сложно — в этой итерации только «подвинуть», а
  «новый» пометить TODO в отчёте и согласовать). НЕ оставлять полусломанным.
- [ ] **Step 3:** адаптив: строка коллапсируется, не сливается со скраббером и `FitTimeline` на узком
  экране; три полосы читаемы.
- [ ] **Step 4 (ВИЗУАЛЬНО, обязательно):** браузер десктоп+мобила: раскрытие глав, цвета моментов,
  клик-обрезка реально меняет интервал и превью, не конфликтует с FitTimeline. Скриншоты.
- [ ] **Step 5:** `just check`. commit `feat(web): обогащённая строка тем + клик-обрезка в редакторе`.

---

## Финальная интеграция
- [ ] Прогнать `just check` на всей ветке (зелёный, codegen синхронизирован).
- [ ] **Боевые тесты:** по запросу фаундера задеплоить воркер, прогнать реальное видео; проверить:
  карта осмысленная (RU/EN спот-чек), строка/клик-обрезка работают, агент выполняет мульти-правку
  надёжно (сценарий из D2), мин. длина 20с соблюдается.
- [ ] **Визуальный сводный прогон** в браузере (десктоп+мобила) по всем экранам.
- [ ] Обновить `docs/README.md` (реальность) + `docs/JOURNAL.md` (одна запись).
- [ ] **НЕ пушить/НЕ мержить** — ждать явного «ок» фаундера после его проверки.

---

## Self-review (покрытие спека)
- Спек §2 (Карта) → D1 (бэкенд) + D3 (фронт). §3 (строка) → D1 + D4. §4 (агент) → D2. §5 (20с) → D0.
  §6 (архитектура/контракт) → D1.1 (`just types`). §7 (визуальная QA + мобила) → DoD в D0.7, D3.5,
  D4.4 + финал. §8 решения (оба действия клипа / мобила свёрнута / язык видео) → D3.2, D3.3, D4.2.
- Зависимости: D0 и D1.1 — первыми (контракт). D3/D4 — после контракта VideoMap (D1.1). D2 — после
  тула `get_video_map`/D1. Параллелить: D0 ⟂ D1 ⟂ (D2 после D1.1) ⟂ (D3/D4 после D1.1).
- Открытый под-вопрос (D4.2 «новый клип»): минимальный путь уточнить в реализации; не оставлять
  полусломанным — если дорого, согласовать «только подвинуть» в этой итерации.
</content>
