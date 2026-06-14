# BE-A — отчёт агента (Import / Transcribe / Config / Cache / Errors)

## Сводка
- Файлов проверено: 5 (`stage0_import.py`, `stage1_transcribe.py`, `transcript_cache.py`, `config.py`, `errors.py`) + 4 теста.
- Багов найдено: 5 (crit 0 / high 1 / med 3 / low 1)
- Багов починено: 4 (один — в чужом файле run.py — передан оркестратору)
- Тесты добавлены: 6, прогон:
  `uv run python -m pytest tests/unit/test_stage0_import.py tests/unit/test_stage1_transcribe.py tests/unit/test_stage1_contract.py tests/unit/test_transcript_cache.py -q` → **41 passed**
  mypy на 5 файлах → **Success: no issues found**.

## Баги

### [HIGH] parse_fps пропускает fps ≤ 0 → ZeroDivisionError при рендере — stage0_import.py:71
**Симптом:** `parse_fps("0/1")` возвращало `0.0`, `parse_fps("-30/1")` → `-30.0`, `parse_fps("0")` → `0.0`.
Значение шло в `meta.fps` → дальше в `round(seg_start * fps) / fps` (stage5_render.py:454) и
`round(start * fps) / fps` (stage3_reframe.py:704). **fps=0 = ZeroDivisionError на стадии рендера**,
отрицательный = битая кадровая математика. Тихий брак, всплывающий далеко от источника.
**Корень:** проверялся только нулевой ЗНАМЕНАТЕЛЬ (`30/0`), но не нулевой/отрицательный РЕЗУЛЬТАТ.
**Фикс:** после вычисления — `if fps <= 0: raise JobError(...)`.
**Тест:** `test_zero_numerator_raises`, `test_zero_bare_raises`, `test_negative_raises`.

### [MED] build_source_meta пропускает duration ≤ 0 и width/height ≤ 0 — stage0_import.py:90,116
**Симптом:** `duration="0"` или `width=0` в ffprobe проходили молча → нулевой/пустой клип,
деление на ноль в downstream-геометрии, битый meta.json.
**Корень:** `_duration` валидировал только «есть/нет» и парсимость, не положительность; размеры
не проверялись на > 0 вообще.
**Фикс:** `_duration` → `if dur <= 0: raise JobError`; в `build_source_meta` → `if width <= 0 or height <= 0: raise JobError`.
**Тест:** `test_zero_duration_raises`, `test_zero_width_raises`.

### [MED] deepgram_to_transcript тихо подставляет duration=0.0 — stage1_transcribe.py:65
**Симптом:** при отсутствии `metadata.duration` в ответе Deepgram писалось `duration=0.0` молча.
Дальше в run.py: `transcribe_cost = transcript.duration / 60 * RATE` = **$0** → учёт стоимости/маржи
(железное правило №12) ломается незаметно; любые проверки длины тоже.
**Корень:** `.get("duration", 0.0)` — классический тихий фолбэк (нарушает правило №8).
**Фикс:** явный `JobError`, если `duration` отсутствует или не парсится в float.
**Тест:** `test_missing_duration_raises_not_silent_zero`. Контракт-фикстура имеет валидный
`duration=1987.7` → `test_real_deepgram_response_parses` остаётся зелёным.

### [LOW] config.max_source_minutes=90 — мёртвое/вводящее в заблуждение поле — config.py:56
**Симптом:** поле `max_source_minutes: int = 90` нигде не читается (grep по всему репо — только
определение). Реальный потолок длины = `billing.MAX_VIDEO_MINUTES = 180` (stage0._check_limits).
Два «лимита» с разными числами (90 vs 180) — ловушка: настройщик меняет 90, эффекта нет.
**Корень:** legacy-остаток до перехода на кредит-модель (журнал CLAUDE.md это подтверждает —
«Раньше тут стоял плоский 90»).
**Фикс:** удалил поле, заменил комментарием с указанием единого источника правды (billing.MAX_VIDEO_MINUTES).

## Передать оркестратору (чужие/общие файлы)

### [MED] cache_key использует deepgram_model для ВСЕХ провайдеров — run.py:120-121,144-145 (домен BE-G)
В run.py ключ кэша транскрипции строится как
`cache_key(sha, s.transcription_provider, s.deepgram_model)` и так же пишется `db.put_cached_transcript`.
При `transcription_provider="assemblyai"` в ключ всё равно попадает **deepgram_model**, а не модель
AssemblyAI. Сейчас не стреляет (assemblyai-путь не реализован — `transcribe()` кидает JobError на
неподдержанный провайдер), но как только AssemblyAI включат, кэш-коллизия: разные модели → один ключ →
возврат чужого/устаревшего транскрипта (ровно то, от чего `cache_key` и защищает по докстрингу).
Рекомендация для BE-G: выбирать модель по провайдеру (`deepgram_model` если deepgram, иначе
assemblyai-модель), либо включать обе в ключ. Файл run.py вне моего ownership — не правил.

## Не успел / открыто (наблюдения, не правил — нет однозначного бага)

- `call_deepgram` грузит весь WAV в RAM через `wav.read_bytes()` (stage1:95). На длинных видео
  (WAV >100МБ) это пиковая аллокация всего файла в память. `write=None` решает таймаут, но не RAM.
  Потенциальная оптимизация — стриминг файла, но это перф, не корректность — оставил как есть.
- `_video_stream` берёт `streams[0]` (stage0:74). В I/O-пути это безопасно, т.к. `probe_video`
  фиксирует `-select_streams v:0`. Но pure-функция `build_source_meta` доверяет, что [0] — видео;
  если её когда-то вызовут с непрофильтрованным probe (аудио-стрим первым), размеры/fps уедут.
  Сейчас не баг (вызывается только из import_* после probe_video) — не трогал.
- `transcript_cache` — проверен, корректен: ключ включает provider+model (защита от stale при
  смене модели), `get_cached` ловит битый JSON через `except Exception` с явным комментарием
  «corrupt cache entry = miss» (это допустимый осознанный фолбэк на кэше, а не тихое глотание
  ошибки пайплайна — правило №8 не нарушено). Eviction-логика (TTL → cap) корректна.
