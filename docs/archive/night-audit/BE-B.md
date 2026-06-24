# BE-B — отчёт агента (Select/Chapters, Gemini)

## Сводка
- Файлов проверено: 5 (`pipeline/stage2_select.py`, `editor/chapters.py`, `prompts/select_moments.v1.txt`, `prompts/describe_chapters.v1.txt` + read-only сверка `main.py` get_chapters / `tasks.py` generate_chapters_job)
- Багов найдено: 3 (crit 0 / high 1 / med 1 / low 1)
- Багов починено: 1 (high — в моём ownership). 2 — передаю оркестратору (вне ownership) / задокументировано
- Тесты добавлены: 9 (класс `TestIsTransientGeminiError`), прогон:
  `uv run python -m pytest tests/unit/test_stage2_select.py tests/unit/test_chapters.py tests/unit/test_chapters_api.py -q`
  → **51 passed, 1 warning** (был 42 → +9). ruff: All checks passed. mypy stage2_select.py: Success.

## Баги

### [HIGH] Ретрай Gemini не классифицирует ошибки — перманентные маскируются 60с бэкоффа — stage2_select.py:280-307 (до фикса)
**Симптом:** `call_gemini_structured` ретраил ЛЮБОЕ исключение без разбора. Перманентные
ошибки (битый `GEMINI_API_KEY`=401/403, несуществующая модель=404, ошибка `response_schema`=400/422)
прогонялись 7× primary (бэкофф 1+2+4+8+16+30 ≈ **61с**) + 3×2 fallback-модели, после чего юзер
получал родовое `"Gemini недоступен после всех попыток: ..."` — корневая причина (401/auth)
**замаскирована** под недоступность, плюс ~2 мин зря потраченного ожидания на каждом джобе с
плохим ключом/конфигом. Free-tier 429/503 — это ЦЕЛЕВЫЕ кандидаты ретрая, остальные 4xx — нет.
Формально правило №8 не нарушено (ошибка в итоге всплывает), но корень скрыт и latency огромна.
**Корень:** `except Exception` без анализа кода ответа; SDK `google.genai.errors.APIError`
несёт `.code` (HTTP-статус); `ClientError`=4xx, `ServerError`=5xx.
**Фикс:** добавлена PURE-функция `is_transient_gemini_error(exc)` (stage2_select.py, перед
секцией промптов): транзиентные = 429 + любой 5xx + сетевые (httpx, без `.code`) + неизвестный
тип (консервативно True); перманентные = {400,401,403,404,422} → ронять сразу. Оба ретрай-цикла
(primary + fallback) теперь на перманентной ошибке делают
`raise JobError(stage, f"Gemini: неретраябельная ошибка: {e}") from e` — fail-fast с корнем,
не дёргая fallback и не накручивая бэкофф.
**Тест:** `TestIsTransientGeminiError` — 429/500/503 → transient; 400/401/403/404 → permanent;
httpx ReadTimeout/ConnectError → transient; RuntimeError → transient (дефолт). 9 кейсов,
проверены и на реальных `errors.ClientError(429)`/`ServerError(503)` (несут `.code`).

## Что проверено и ОК (не баги — для протокола)
- **score clamping:** `clamp_score` клиппит в [0,1] до конструирования `Segment` (pydantic
  `Field(ge=0,le=1)` иначе бы упал). Gemini игнор min/max схемы покрыт. ✓
- **resolve_max_clips:** None→дефолт, кламп [1,12]; hi=12 безвреден (UI-степпер 1-10, CreateJobBody le=10). ✓
- **indices_to_times off-by-one:** `words[end_idx].end` — корректная граница; out-of-range и
  start>end → JobError, ловятся в postprocess (try/except → пропуск битого сегмента, не падение). ✓
- **snap_start_index / snap_end_index edge cases:** negative idx→0; huge idx→IndexError ловится;
  dangling-tail forward-skip (баг «Антимошенника») и сохранение коротких хук-предложений — покрыты
  существующими тестами, перепроверены трассировкой. ✓
- **resolve_overlaps:** касающиеся сегменты (end==start) допускаются (`<=`/`>=`); ties стабильны
  (sorted stable) → детерминизм. ✓
- **postprocess hook/why_works:** тернарник `str(x).strip() or None if x else None` — приоритеты
  корректны (whitespace→None, falsy→None). ✓
- **postprocess_chapters:** кламп [0,dur], сортировка, gap-fill/overlap-cut, contained-chapter
  (start>end после cut → e-s<MIN → drop), последняя дотягивается до duration — трассированы, ОК. ✓
- **generate_chapters word-index clamp:** si/ei клампятся в [0,n-1]; si>ei → негативная глава →
  отфильтруется в postprocess; пустые words → IndexError ловится. ✓
- **Цепочка ошибок surfacing:** `tasks.py` ловит JobError→status=failed (select-путь и
  generate_chapters_job). Quota 429/503 после исчерпания ретраев → JobError → failed, НЕ молчаливые
  0 клипов. ✓ (empty-state «нечего нарезать» — отдельный корректный путь при 0 валидных сегментов.)
- **resp.text None (finish_reason SAFETY/MAX_TOKENS):** `if not text: raise JobError("пустой ответ")`. ✓
- **json parsing:** `json.loads(text).get(...)` обёрнут в `JSONDecodeError`→JobError в обоих
  местах (select + chapters). Усечённый MAX_TOKENS JSON → JSONDecodeError → surfaced. ✓

## Передать оркестратору (чужие/общие файлы)
- **[MED] tasks.py:159-180 `generate_chapters_job` — пустые главы пишутся как `status=done`,
  chapters=[].** Если `generate_chapters` вернул [] (все главы битые / 0 слов / LLM-промах), фронт
  поллит, видит `done` + пустую карту БЕЗ объяснения (тихий «успех-пустышка», граничит с правилом №8).
  Предложение: в `generate_chapters_job` трактовать пустой результат как
  `status=failed, error="карта глав пустая — Gemini не вернул валидных глав"` (или 422-подобный
  статус), чтобы фронт показал причину/кнопку retry. Файл вне моего ownership (BE-G).
- **Инфо (не баг): main.py:343-373 get_chapters** — retry/pending/404 логика корректна, покрыта
  test_chapters_api (5 кейсов зелёные). Ничего менять не требуется.

## Не успел / открыто (низкий приоритет, не трогал)
- **[LOW] stage2_select.py:379-384 `select_to_file` — мёртвый код.** Не вызывается нигде
  (run.py использует `select_segments` напрямую), плюс внутри избыточный `from pathlib import Path`
  (Path уже импортирован на module-level стр.15) и НЕ пробрасывает `max_clips`. Не удалял: публичная
  функция, удаление = риск внешнего импорта; оставляю решение оркестратору (безопасно удалить или
  пометить deprecated).
- **Наблюдение (не баг):** `_FALLBACK_MODELS=("gemini-2.5-flash","gemini-2.0-flash")` зашиты
  константой; если primary `llm_model` уже один из них — fallback частично дублирует. Косметика.
