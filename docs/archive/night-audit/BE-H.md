# BE-H (Billing accounting — PAYG deduction + double-charge fix) — отчёт агента

## Сводка
- Файлов изменено: 4 (`billing.py`, `db.py`, `supa.py`, `tasks.py`) + 3 тест-файла.
- Багов починено: 1 (CRITICAL, унаследован от BE-F finding) — PAYG-баланс не списывался + двойной учёт минут.
- Тесты добавлены: 17, прогон:
  ```
  uv run python -m pytest tests/unit/test_billing.py tests/unit/test_db.py \
    tests/unit/test_supa.py tests/unit/test_tasks.py -q
  → 62 passed in 0.56s   (было 45)
  ```
  ruff + mypy на owned-файлах (`billing.py db.py supa.py tasks.py`): `All checks passed!` / `Success: no issues found`.

## Баг

### [CRITICAL] PAYG-баланс не списывался + PAYG-минуты дублировались в месячный лимит — tasks._meter / db.record_usage / billing.check_quota
**Симптом:** Под `BILLING_ENABLED` + реальным Polar: (1) платный PAYG-баланс не убывал → бесконечные «купленные» кредиты; (2) те же минуты, что покрылись из PAYG, ещё и засчитывались в месячный счётчик → двойной учёт против лимита плана.
**Корень:** `check_quota` корректно считал split (`from_monthly_min`/`from_payg_min`), но `_meter` его игнорировал: звал `db.record_usage(... ПОЛНЫЕ minutes ...)` и не декрементил `profiles.payg_credits`. У `from_payg_min` было 0 потребителей; примитива списания PAYG не существовало.
**Фикс:** реализован контракт из брифа (см. ниже). Split, авторизованный гейтом, протянут от `_quota_gate` в `_meter` через холдер; в месячный счётчик идёт только `from_monthly_min`, PAYG списывается по `payg_credits_for_split`.
**Тест:** `test_meter_records_only_monthly_part_and_deducts_payg` (+4 meter-кейса), `test_deduct_payg_*` (db+supa), `TestPaygCreditsForSplit` (billing).

## Что изменено по файлам

**`billing.py`** — добавлена PURE `payg_credits_for_split(decision) -> int`: переводит `from_payg_min` (минуты) обратно в целые PAYG-кредиты (1 кредит = 60 мин) округлением ВВЕРХ (`ceil`). Отклонённое решение / нулевая PAYG-часть → 0. Контракт не трогал (`models.py` read-only), новых полей не вводил.

**`db.py`** — добавлен `deduct_payg(user_id, credits)`: SQLite `UPDATE profiles SET payg_credits=MAX(0, payg_credits-?) WHERE user_id=?` (атомарно, пол 0). `credits<=0` → no-op. Нет профиля → UPDATE 0 строк (НЕ создаём строку с отрицательным балансом, в отличие от `add_payg_credits`/upsert — «минус-кредиты» бессмысленны). Дуал-режим: при `supa_enabled()` делегирует в `supa.deduct_payg`.

**`supa.py`** — добавлен `deduct_payg(user_id, credits)`: PostgREST read-modify-write (`get_profile` → PATCH `payg_credits=max(0, current-credits)`), `Prefer: return=representation` в стиле соседних `add_payg_credits`/`set_user_plan` (фикс из wave 1). `credits<=0` или `current<=0` (нет профиля/баланса) → PATCH не дёргаем (no-op). Floor-at-0 зеркалит SQLite.

**`tasks.py`** — (1) `_quota_gate(user_id, holder)` теперь складывает авторизованное `QuotaDecision` в `holder["decision"]` после успешной проверки. (2) `_meter(user_id, job_id, job, holder)` применяет split: `record_usage` получает ТОЛЬКО `from_monthly_min` (фикс двойного учёта), PAYG списывается `deduct_payg(user_id, payg_credits_for_split(decision))`. Без decision (биллинг выключен → гейт не запускался) — старое поведение: полные минуты в месячный счёт, PAYG не трогаем. (3) `run_pipeline_job`/`run_upload_job` создают холдер `quota: dict[str, Any] = {}` и протягивают его в оба колбэка.

## Контракт (реализованный)
1. PAYG-покрытый объём списывается с `profiles.payg_credits` атомарно, пол 0, никогда не отрицателен.
2. PAYG-покрытые минуты НЕ идут в месячный счётчик — записывается только `from_monthly_min` (двойной учёт устранён).
3. Используется split, который УЖЕ посчитал `check_quota`. Гейт кладёт авторизованное решение в холдер, метеринг читает оттуда → нет рекомпьюта и нет дрейфа. Согласованность доказуема: длина источника одна и та же (`meta.duration` на гейте == `metrics.duration_sec` на метеринге, см. `run.py:260`), так что split, авторизованный гейтом, и есть корректный split для метеринга.
4. `deduct_payg` добавлен в db.py (SQLite) и supa.py (PostgREST), одинаковый интерфейс, floor-at-0 в обоих.
5. PAYG→кредиты: `ceil(from_payg_min/60)` — покрытый объём не недосписывается (consistent с тем, как PAYG продаётся: 1 заказ = 1 кредит = 60 мин).

## Допущения (где split-форма была неоднозначна)
- **`from_payg_min` (минуты) → целые PAYG-кредиты округлением ВВЕРХ.** PAYG-баланс хранится в целых «видео»-кредитах, split — в минутах. Округление вверх консервативно к продукту (partial-видео из PAYG = 1 кредит, как при покупке), и `deduct_payg` floor-at-0 не даёт уйти в минус. Альтернатива (дробные кредиты) потребовала бы менять схему БД (`payg_credits INTEGER`) — вне ownership и избыточно.
- **`record_usage` всё равно вызывается даже когда `from_monthly_min == 0`** (видео целиком из PAYG): пишет строку с 0 месячных минут. Это сохраняет аудит-след (job_id, факт обработки), а месячный лимит не раздувается. Кредитная колонка месячного счётчика выводится `record_usage` из переданных минут (0 → 1 по `credits_per_video`, но это месячная celochislennая колонка аудита, гейт считает по минутам — не влияет на лимит).

## Передать оркестратору (чужие/общие файлы)
- **Ничего из моих изменений не выходит за ownership.** `models.py`/контракт не тронут. Миграции (`0001`/`0002`) не менял — `deduct_payg` работает поверх существующей колонки `profiles.payg_credits`.
- BE-F MEDIUM «гейт-рассинхрон Modal» (биллинг в SQLite на эфемерном контейнере без `BILLING_ENABLED`) — продуктовое решение env-пары, вне моего фикса. Мой фикс корректен в обоих режимах (SQLite и Supabase), но персистентность PAYG на Modal требует `BILLING_ENABLED=true` (иначе списание идёт в эфемерную SQLite).

## Остаточный риск (идемпотентность, часть 5 брифа)
- **`record_usage` НЕ идемпотентен** сегодня: безусловный `INSERT` в `usage_events`; `deduct_payg` — безусловный декремент. Нет per-job dedup-ключа.
- **Нормальный поток безопасен:** каждый `POST /jobs` → новый `job_id` → ровно один `run_pipeline_job`/`run_upload_job` → `_meter` ровно один раз после `set_done` в том же таске. Re-render (`render_clip_edit_job`) `_meter` НЕ зовёт → правки/ре-рендеры не списывают повторно.
- **НЕ сделал хуже:** `deduct_payg` floored at 0 (не уйдёт в минус даже при повторе), но при истинном двойном прогоне одного `job_id` (будущая retry-логика / ручной ре-диспатч) PAYG мог бы пере-списаться и месячный счётчик задвоиться.
- **Чистый фикс** (не делал — затрагивает схему вне ownership): `UNIQUE(job_id)` на `usage_events` + idempotent upsert (или таблица `payg_ledger` с job_id PK для точной обратимости). Рекомендация оркестратору/фаундеру при включении биллинга: добавить уникальный констрейнт на `usage_events.job_id` в миграции, чтобы повтор метеринга был no-op.

## Не успел / открыто
- Ничего в домене не осталось. Live e2e под реальным Polar/Supabase не гонял (нет секретов — вне границ ночи); логика покрыта unit-тестами (SQLite-путь реально пишет в БД; supa-путь — httpx-мок).
