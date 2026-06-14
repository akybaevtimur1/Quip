# FE-D — отчёт агента (Core tool flow + API client / polling)

## Сводка
- Файлов проверено: 13 (SourceForm, JobProgress, ClipGrid, ClipCard, StatusBadge, ErrorPanel,
  ReasonChip, lib/api.ts, lib/useJob.ts, lib/format.ts, app/api/mock/** ×2; + read-only:
  dashboard/page.tsx, lib/types.ts, packages/shared контракт, main.py эндпоинты).
- Багов найдено: 3 (crit 0 / high 0 / med 2 / low 1)
- Багов починено: 3 (med 2 / low 1)
- Тесты добавлены: 0 (фронт без unit-харнесса; верификация — tsc + lint, см. ниже).
- Прогон: `pnpm --filter web exec tsc --noEmit` → **TSC_OK**; `pnpm --filter web lint` → **LINT_OK**.

## Что НЕ баг (проверено, оставлено как есть)
Слой `useJob` написан корректно — НЕ нашёл утечек/двойного опроса/гонок:
- **Lifecycle чист.** Всё мутабельное состояние (`active`/`fails`/`pollTimer`/`tick`) живёт
  ВНУТРИ effect-замыкания (per-run). Cleanup на смене `jobId`/unmount: `active=false` +
  `clearInterval(tick)` + `clearTimeout(pollTimer)`. Опрос — рекурсивный `setTimeout` (НЕ
  `setInterval`), наложения тиков нет. Старый in-flight `getJob` после смены job защищён
  `if (!active) return` перед `setJob`. Двойного опроса/leak нет.
- **MAX_FAILS без off-by-one.** `fails` 0→1→2→3; стоп ровно на 3-м ПОДРЯД сбое, ошибка
  СЁРФИТСЯ (`setError`), не зависает на «tracking». `setError` под `if (active)`.
- **Partial-Job безопасен.** `useJob` читает только `j.status` и `j.error` (через `|| fallback`).
  `ClipGrid` — `job.clips ?? []`, `job.metrics` под `m ?`. `ClipCard` — `clip.hook &&`,
  `clip.why_works ?? clip.reason`. Crash-on-partial не воспроизводится.
- **Контракты совпадают.** upload-форма шлёт поля `file` + `max_clips` — совпадает с
  `main.py` (`File(...)` + `Form(max_clips)`). `createJob` тело `{source_type, source_ref,
  max_clips}` = `CreateJobBody`. Mock-роут отдаёт полную форму `Job`/`ClipOut` из контракта.
- **Степпер 1–10** клампится (`clamp`) + кнопки дизейблятся на границах + при `busy`. NaN не
  возникает (счётчик — число в state, не parseInt из input).
- **Двойной сабмит** закрыт: `disabled={!canSubmit}` (`canSubmit = !busy && …`) + ранний
  `if (!canSubmit) return` в `handleSubmit`; `busy` = родительский `submitting`.
- **Скачивание** стаггерится (`i*400ms`) — браузер не режет пачку как попап.

## Баги

### [MED] Висящий ответ воркера → бесконечный спиннер — lib/api.ts:123 (getJob)
**Симптом:** `fetch` без таймаута. Если воркер принял TCP-коннект, но НЕ отвечает (медленный/
завис Modal cold-start, прокси держит сокет), `getJob` НИКОГДА не реджектит → `useJob.loop`
не доходит ни до `catch` (нет инкремента `fails`), ни до перепланирования → опрос ТИХО
стопорится. Юзер навсегда на «Cutting your video…» с тикающим таймером, ошибка не появляется.
README прямо просит проверить «network failure/**timeout** → clear state vs infinite spinner».
**Корень:** нет request-таймаута на polling-пути.
**Фикс:** добавлен `fetchWithTimeout` (AbortController, 15с) и применён в `getJob`. Таймаут →
`AbortError` → throw → засчитывается как сбой опроса → после 3 подряд срабатывает MAX_FAILS и
юзер видит «Lost connection to the worker». Самодостаточно (свой controller, не пересекается с
cleanup `useJob`; `active`-guard цел).
**Тест:** tsc/lint зелёные; логика подтверждена трассировкой ветки `catch → fails++` в useJob.

### [MED] `mmss` не показывает часы для источника >60 мин — lib/format.ts:2
**Симптом:** источник до 90 мин. `mmss(5400)` → `90:00` — читается как «90 секунд:00» /
двусмысленно. Используется в `ClipGrid` для `m.duration_sec` (длина источника) — реальный
видимый кейс на длинных видео.
**Корень:** формат жёстко `M:SS`, без разряда часов.
**Фикс:** при `s >= 3600` → `H:MM:SS` (`1:30:00`); для клипов (<60 мин, редактор/clipRange)
формат `M:SS` не меняется — обратная совместимость.
**Тест:** tsc/lint зелёные.

### [LOW] `mmss`/`usd` от NaN/Infinity печатают мусор — lib/format.ts:2,13
**Симптом:** `mmss(NaN)` → `"NaN:NaN"`, `usd(NaN)` → `"$NaN"`. `duration_sec`/`elapsed_sec`/
`cost_usd` приходят с провода (Metrics) — битый/частичный ответ бэка дал бы мусор в UI.
**Корень:** нет guard на неконечные числа.
**Фикс:** `Number.isFinite(...)` → fallback `0` (`0:00` / `$0.00`).
**Тест:** tsc/lint зелёные.

## Передать оркестратору (чужие/общие файлы)
- Ничего критичного. Контракт `packages/shared` (read-only) и `main.py` эндпоинты совпадают
  с фронтом — расхождений не нашёл.
- (Наблюдение, НЕ баг) Mock `POST /api/mock/jobs` игнорирует тело запроса (`source_ref`/
  `max_clips`) — для мока ок (прогресс детерминируется временем из `id`). Если оркестратор
  захочет, чтобы мок честно отражал `max_clips` в числе клипов — это доработка, не дефект.

## Не успел / открыто
- Фронт-домен без unit-тест-харнесса (Vitest/Jest нет в apps/web) → формальных тестов на
  `mmss`/`fetchWithTimeout` не добавлял; верификация — tsc + lint + ручная трассировка.
  Если оркестратор поднимет vitest для lib/* — стоит зафиксировать `mmss(5400)=="1:30:00"`,
  `mmss(NaN)=="0:00"`, и тайм-аут-ветку getJob.
- `usd()` сейчас нигде не импортируется (мёртвый, но публичный экспорт lib) — оставил
  (захардить дёшево, удалять — вне скоупа «только баги»).
