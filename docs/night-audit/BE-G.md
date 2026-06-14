# BE-G — отчёт агента (API surface + orchestration)

## Сводка
- Файлов проверено: 5 owned (`main.py`, `tasks.py`, `run.py`, `eval.py`) + транзит
  (`transcript_cache.py`, `config.py`, `dispatch.py`, `editor/ops.py`, `editor/chapters.py`, `db.py` — read-only).
- Багов найдено: 5 (crit 0 / high 2 / med 2 / low 1)
- Багов починено: 5 (включая все 3 handoff-айтема)
- Тесты добавлены: 7 (3 в `test_editor_api.py`, 1 в `test_editor_api.py` для spawn, 3+1 в новом `test_tasks.py`)
- Прогон:
  ```
  uv run python -m pytest tests/unit/test_upload_api.py tests/unit/test_models.py \
    tests/unit/test_models_contracts.py tests/unit/test_eval.py \
    tests/unit/test_editor_api.py tests/unit/test_tasks.py -q
  → 56 passed, 1 warning in 1.40s
  ```
  ruff + mypy на owned-файлах: `All checks passed!` / `Success: no issues found`.

## Баги

### [HIGH] Editor op-handlers не ловят JobError → 500 вместо 400 — main.py:536-555 (handoff #1)
**Симптом:** wave-1 сделал `ops.py` доменно-рейзящим `JobError` на невалидный ввод
(индекс слова вне диапазона, перевёрнутый интервал, неизвестный край). Хендлеры
`op_trim`/`op_add_section`/`op_extend`/`op_set_interval` звали ops БЕЗ перехвата →
JobError всплывал необработанным → HTTP **500** (баг сервера) вместо **400** (ошибка клиента).
**Корень:** GET-хендлеры транслируют JobError→404, но POST-op-хендлеры — нет.
**Фикс:** добавлен `_op_or_400(fn)` (main.py), оборачивающий ops-вызов и переводящий
`JobError → HTTPException(400, detail=str(e))`. Обёрнуты все 4 op-хендлера.
**Тест:** `test_trim_bad_index_returns_400`, `test_add_section_inverted_range_returns_400`,
`test_extend_unknown_edge_returns_400` (test_editor_api.py).

### [MED] generate_chapters_job: пустой результат Gemini → тихий done с []  — tasks.py:159 (handoff #2)
**Симптом:** `generate_chapters` может вернуть `[]` (модель отдала 0 глав / все главы
битые и отброшены / postprocess пуст). Таск писал `status="done", chapters=[]` → фронт
показывал ПУСТУЮ карту без объяснения (нарушение правила №8 — тихий «успех»).
**Корень:** отсутствовала проверка пустого результата перед записью done.
**Фикс:** `if not chapters:` → `save_chapters(..., status="failed", error="AI-карта пуста …")`
и `return`. Это включает существующий retry-путь (`GET /chapters?retry=true`) и юзер видит причину.
**Тест:** `test_chapters_job_empty_result_is_failed_not_silent_done` (+ success/JobError кейсы) в test_tasks.py.

### [MED] transcript cache_key всегда берёт deepgram_model независимо от провайдера — run.py:120 (handoff #3)
**Симптом:** `cache_key(sha, provider, s.deepgram_model)` — при
`transcription_provider="assemblyai"` в ключ кэша попадал deepgram-моделей слот (`nova-3`),
мусорный/недискриминирующий. Provider-поле спасало от кросс-провайдер коллизии (deepgram
≠ assemblyai), но смена assemblyai-модели НЕ инвалидировала бы кэш → latent stale-collision.
**Корень:** хардкод `s.deepgram_model` во всех трёх сайтах ключа (локальный + Postgres get/put).
**Фикс:** добавлена PURE `transcript_cache_model(settings)` (run.py): возвращает модель
ВЫБРАННОГО провайдера; для assemblyai читает `assemblyai_model` через getattr (поле опционально
в config — провайдер ещё не реализован, дефолт `"assemblyai-default"` безопасен). Все три
сайта ключа теперь используют `tr_model`.
**Тест:** `test_transcript_cache_model_is_provider_aware` (test_tasks.py).

### [HIGH] dispatch.spawn упал → джоб/рендер застрял в queued/rendering навсегда — main.py:206, 622
**Симптом (cloud-only, Modal-путь):** в `create_job` джоб вставляется как "queued", затем
`dispatch.spawn("run_job", …)`. В `post_render` статус ставится "rendering", затем
`dispatch.spawn("render_job", …)`. Если spawn рейзит (modal import/lookup/сетевой сбой) ДО
старта работы — строка БД остаётся "queued"/"rendering" НАВСЕГДА, фронт поллит вечно.
**Корень:** spawn не обёрнут; статус выставлен оптимистично до подтверждения постановки.
**Фикс:** обёрнуты оба spawn-вызова в try/except → `db.set_failed` / `set_render_status(failed)`
с причиной + `HTTPException(500)` (правило №8). Локальный `bg.add_task`-путь не трогал
(BackgroundTask не падает синхронно). upload-путь всегда bg.add_task (не spawn) → не затронут.
**Тест:** `test_post_render_spawn_failure_marks_render_failed` (test_editor_api.py).

### [LOW] (проверено, НЕ баг) CORS regex / StaticFiles
**Проверка:** `allow_origin_regex` корректно покрывает `app.quip.ink` + `*.vercel.app` +
`localhost:3000`. StaticFiles `/media` смонтирован на `DATA_ROOT` (mkdir перед mount).
Auth-гейт (`_resolve_user`) корректно 401-ит при включённом Supabase и dual-mode иначе.
Все error-mapping в GET-хендлерах (JobError/FileNotFoundError/KeyError→404) на месте. OK.

## Передать оркестратору (чужие/общие файлы)

### PAYG-credit decrement отсутствует (как и предписано — НЕ чинил, нужен контракт)
- **Call-site метеринга:** `tasks.py` функция `_meter(user_id, job_id, job)` (строки 48-58),
  вызывается в `run_pipeline_job` (**tasks.py:202**, после `set_done`) и в `run_upload_job`
  (**tasks.py:240**). `_meter` зовёт только `db.record_usage(user_id, job_id, minutes, month)`.
- **Гэп:** `db.record_usage` пишет `credits` в МЕСЯЧНЫЙ `usage_events`, но НИКОГДА не
  декрементит `profiles.payg_credits`. Когда месячный лимит исчерпан и стоимость переливается
  в PAYG, `billing.check_quota` (в `_quota_gate`, tasks.py:34-45) уже считает split
  `from_monthly`/`from_payg` (decision), но `_meter` этот split игнорирует и списывает всё
  как месячное. → PAYG-кредиты никогда не списываются.
- **Что нужно (контракт-решение оркестратора):** `_meter` должен получить decision.split
  (или пересчитать) и вызвать `db.add_payg_credits(user_id, -from_payg)` для PAYG-части.
  Это спанит `db.py`/`supa.py` (BE-F) + billing-контракт → не мой домен.

### models.py — изменений НЕ требую
- Все мои фиксы уложились в owned-файлы. `ChaptersData.status`/`error` уже поддерживают
  failed-с-причиной. Контракт не трогал.

### config.py (BE-A) — опциональное улучшение
- Мой `transcript_cache_model` читает `assemblyai_model` через getattr (поля сейчас НЕТ в
  Settings). Когда BE-A реализует assemblyai-провайдера, стоит добавить
  `assemblyai_model: str = "best"` в config.py — мой код подхватит автоматически.

## Не успел / открыто
- Ничего критичного не осталось в домене. Spawn-guard покрывает основные stuck-job классы.
  Полный e2e на Modal (live spawn-failure) не гонял — нет деплоя/секретов (вне границ ночи).
