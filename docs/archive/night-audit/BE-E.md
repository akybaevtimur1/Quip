# BE-E — Editor backend — отчёт агента

## Сводка
- Файлов проверено: 8 (store, ops, timemap, timeline, replies, defaults, presets, preset_seeds)
- Багов найдено: 5 (crit 0 / high 1 / med 3 / low 1)
- Багов починено: 4 (все в `editor/ops.py` — pure-логика, мой ownership)
- Тесты добавлены: 6 (в `tests/unit/test_editor_ops.py`)
- Прогон (мой полный набор):
  `uv run python -m pytest tests/unit/test_editor_store.py test_editor_ops test_timemap test_replies test_defaults test_presets test_set_interval test_timeline_api test_editor_api test_editor_models -q`
  → **65 passed, 1 warning in 1.64s** (было 59 до добавления тестов).
  ruff/mypy на `app/editor/ops.py` — чисто.

## Баги

### [HIGH] apply_trim падает голым ValueError/IndexError — ops.py:42 (исходно)
**Симптом:** `op_trim` (main.py:536) зовёт `apply_trim` ДО `_save_or_409`, без try/except.
`TrimBody.word_indices` (main.py:384) не имеет min-length/диапазон-валидации. Клиент,
приславший `word_indices=[]`, получает `min() arg is empty` → **HTTP 500** (а не чистый 4xx).
Индекс вне диапазона транскрипта → `IndexError` → 500.
**Корень:** `min(words[i].start for i in word_indices)` по пустому/невалидному списку.
**Фикс:** в начале `apply_trim` — `if not word_indices: raise JobError(...)` и проверка
диапазона `i<0 or i>=len(words)` → `JobError`. Доменная ошибка вместо неконтролируемого краха
(правило №8).
**Тест:** `test_apply_trim_empty_indices_raises_joberror`, `test_apply_trim_out_of_range_index_raises_joberror`.

### [MED] apply_extend — тихий фолбэк на неизвестный edge — ops.py:71 (исходно)
**Симптом:** `ExtendBody.edge: str` (main.py:398) — свободная строка. Любое значение, кроме
ровно `"start"` (например `"END"`, опечатка, пустая строка), ТИХО проваливалось в ветку `else`
и меняло **КОНЕЦ** клипа. Доказано: `apply_extend(edge="START", new_value=99)` → интервал стал
`(0.0, 99.0)` — пользователь тянул «начало», получил растянутый конец.
**Корень:** `if edge == "start": ... else: <меняем конец>` — нет валидации (правило №8 нарушено).
**Фикс:** `if edge not in ("start","end"): raise JobError(...)` + guard на пустые интервалы.
**Тест:** `test_apply_extend_invalid_edge_raises_joberror`.

### [MED] apply_extend/add_section создают инвертированный интервал — ops.py:62/72 (исходно)
**Симптом:** `apply_extend(edge="start", new_value=10)` на интервале `[0,5]` → `(10.0, 5.0)`
(start>end). `add_section(2.5, 2.0, ...)` → тот же дефект. Эти интервалы текут в `ClipTimeMap`
(длина клампится в 0 через `max(0.0,...)` → «исчезающий» кусок) и в рендер.
**Корень:** нет проверки `new_value` против противоположной границы / `source_end>source_start`.
**Фикс:** в `apply_extend` — старт должен быть < конца, конец > старта (иначе JobError);
в `add_section` — `source_end <= source_start` → JobError.
**Тест:** `test_apply_extend_start_past_end_raises_joberror`, `test_add_section_inverted_range_raises_joberror`.

### [MED] add_section допускает пересекающиеся интервалы → дублирование слов — ops.py:55 (исходно)
**Симптом:** `add_section` вставляет интервал без проверки пересечения. Два пересекающихся
интервала (`[0,3)` + `[1,4)`) в `rebuild_replies` (replies.py:35) дают **дублированные
word_refs**: доказано `[0,1,2,1,2,3]` — слова 1,2 дважды → двойные субтитры + двойной учёт
тайминга караоке. Тайм-мап (`source_to_clip`) тоже ломается: одно source-время мапится в 2
clip-полосы (возвращает первую).
**Корень:** `new_intervals.insert(at_index, new_iv)` без anti-overlap инварианта; и replies, и
timemap предполагают НЕпересекающиеся клип-интервалы.
**Фикс:** в `add_section` — `if any(source_start < iv.source_end and iv.source_start < source_end ...)`
→ JobError (пересечение = невалидный edit-state). Минимальный фикс in-style (как inverted-guard).
**Тест:** `test_add_section_overlapping_range_raises_joberror`.

### [LOW] save_edit — тихая потеря обновления при гонке ленивой вставки — store.py:54 (НЕ чинил)
**Симптом:** в `save_edit`, когда `row is None`, зовётся `insert_clip_edit` = `INSERT OR IGNORE`
(local) / `resolution=ignore-duplicates` (cloud) — обе НЕ возвращают rowcount. При гонке двух
запросов на ленивое создание оба вставляют version=1; один выигрывает, у другого insert ТИХО
игнорируется, **но `save_edit` возвращает свой `saved` как будто записан** — расхождение
возвращённого стейта и БД.
**Корень:** `insert_clip_edit` (db.py:263, чужой файл) ничего не возвращает → `save_edit` не
может детектить проигранную гонку.
**Фикс:** НЕ чинил — корень в контракте `db.py` (ownership BE-F). На практике benign: путь
ленивой вставки (`ensure_edit`) всегда пишет ИДЕНТИЧНЫЙ дефолтный edit, поэтому расхождение
содержательно нулевое. Реальная правка идёт через `update_clip_edit_if_version` (атомарно,
корректно). См. «Передать оркестратору».

## Что проверено и ОК (ложных багов нет)
- **Optimistic-lock основной путь (store.py:58-69):** при существующей строке — корректная
  проверка `expected_version != current` → EditConflict, плюс атомарный
  `update_clip_edit_if_version` (UPDATE ... WHERE version=expected, rowcount==1). Гонка ловится.
- **apply_preset (presets.py:13) сохраняет hook/burn/emphasis_auto:** `model_copy(update={style,
  highlight})` трогает ТОЛЬКО style+highlight → `hook`, `burn`, `replies` сохраняются. Стиль
  пресета сам несёт `emphasis_color/emphasis_auto` (преднамеренная замена). Проверено
  `test_apply_preset_sets_style_and_highlight` + контракт модели.
- **ClipTimeMap (timemap.py):** offset-математика `t_clip = band_start + (t_src - iv.start)`
  верна для нескольких интервалов и для add-section вне source-порядка. Полуинтервал [start,end),
  дырки → None, пустой список → JobError. Хвостовая граница clip_to_source с эпсилоном корректна.
- **rebuild_replies (replies.py):** keep сохраняет text_override/hidden только для НЕизменившихся
  word_refs (ключ = tuple refs) — корректно. Слова вне интервалов выпадают.
- **clamp_interval/set_interval (ops.py:80-126):** все 8 тестов кламп-краёв сходятся; источник
  короче min → окно = весь источник; инверсия схлопывается+расширяется.
- **set_crop_override/clear_crop_overrides:** корректная замена пересекающихся overrides.

## Передать оркестратору (чужие/общие файлы — НЕ правил)
1. **main.py (READ-ONLY) — op-хендлеры не ловят JobError.** После моего фикса `apply_trim`/
   `apply_extend`/`add_section` бросают `JobError` на невалидный ввод, но `op_trim`/`op_extend`/
   `op_add_section` (main.py:536-547) НЕ оборачивают вызов в try/except → JobError всё ещё даст
   HTTP 500. Нужно: в этих хендлерах ловить `JobError` → `HTTPException(400, str(e))`
   (как уже сделано для GET-хендлеров: `except JobError → 404`). Тогда невалидный ввод = чистый 400.
2. **models.py (READ-ONLY) — слабая валидация body.** `ExtendBody.edge: str` стоило бы сделать
   `Literal["start","end"]`; `TrimBody.word_indices` — `Field(min_length=1)`. Это сместит отказ
   на уровень pydantic (422) до бизнес-логики. (Я добавил защиту в pure-слое как страховку.)
3. **db.py (BE-F) — insert_clip_edit не возвращает результат вставки** (см. баг LOW выше). Если
   хотим строгий optimistic-create без тихой потери — `insert_clip_edit` должен возвращать bool
   (вставлено/проигнорировано), а `save_edit` при False — перечитать строку и вернуть актуальную
   версию (или EditConflict). Сейчас benign из-за идентичных дефолтов.

## Не успел / открыто
- Ничего критичного не оставлено. Все 4 чинибельных бага в моём ownership закрыты тестами.
- Рекомендация оркестратору: применить пункт 1 (try/except JobError в 3 op-хендлерах main.py),
  иначе мой fix конвертирует «тихий неверный результат» в «чистый 500» вместо «чистого 400».
