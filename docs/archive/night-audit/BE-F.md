# BE-F (Billing / Persistence / Auth) — отчёт агента

## Сводка
- Файлов проверено: 9 (billing.py, polar.py, db.py, supa.py, cloud_state.py, storage.py, auth.py, artifacts.py, dispatch.py) + read-only main.py/tasks.py/migrations для трассировки денежного пути.
- Багов найдено: 6 (crit 1 / high 2 / med 2 / low 1)
- Багов починено: 2 (обе в supa.py, мой ownership)
- Тесты добавлены: 4, прогон:
  `uv run python -m pytest tests/unit/test_billing.py tests/unit/test_polar.py tests/unit/test_db.py tests/unit/test_supa.py tests/unit/test_cloud_state.py tests/unit/test_storage.py tests/unit/test_auth.py -q`
  → **96 passed, 1 warning in 0.88s** (было 92). mypy app/supa.py: Success.

## Баги

### [CRITICAL] PAYG-баланс никогда не списывается + PAYG-минуты ещё и засчитываются в месячный пул — billing.py:166-177, tasks.py:_record_usage (~56), db.py:record_usage
**Симптом:** Платный PAYG-баланс пользователя не убывает после обработки видео → бесконечные «купленные» кредиты. ОДНОВРЕМЕННО те же минуты, что покрылись из PAYG, попадают в месячный счётчик расхода (двойной учёт против лимита плана).
**Корень:** `check_quota` корректно считает split списания (`from_monthly_min` / `from_payg_min`), но НИКТО его не применяет:
- `from_payg_min` нигде не читается (grep: только определение и присваивание в billing.py — 0 потребителей).
- Нет примитива `deduct_payg_credits` ни в db.py, ни в supa.py.
- `tasks._record_usage` пишет `db.record_usage(user_id, job_id, ПОЛНЫЕ minutes, ...)` безусловно; `get_monthly_usage` суммирует ВСЕ `source_minutes` за месяц → PAYG-покрытые минуты раздувают месячный остаток.
**Фикс:** НЕ чинил — call-site (`tasks.py`) и решение «как разнести списание» вне моего ownership (BE-G/оркестратор), плюс затрагивает `models.py`/контракт учёта. Нужен новый примитив (`db.deduct_payg_credits(user_id, videos)` + supa-аналог, атомарный `payg_credits = max(0, payg_credits - n)`), и `tasks._record_usage` должен: (1) писать в месячный учёт только `from_monthly_min`, (2) списывать PAYG по `ceil(from_payg_min/60)`. Я могу добавить db/supa-примитив в свой ownership, если оркестратор подтвердит контракт списания.
**Тест:** воспроизводится логически (см. grep `from_payg_min` — 0 потребителей). Тест отложен до решения по контракту (правило 9: не угадываю денежную семантику).

### [HIGH] supa.add_payg_credits: оплата PAYG МОЛЧА теряется, если профиля ещё нет — supa.py:94 (ПОЧИНЕНО)
**Симптом:** Юзер оплатил разовый PAYG-заказ, но `profiles`-строки ещё нет (триггер `handle_new_user` не сработал / гонка signup↔оплата / pre-trigger юзер) → PATCH `profiles?id=eq.<uid>` затрагивает 0 строк, `Prefer: return=minimal` → 200 без ошибки → кредиты исчезают. SQLite-путь (`db.add_payg_credits`) делает upsert (INSERT…ON CONFLICT) и НЕ страдает — асимметрия + тихий фолбэк (нарушение правила №8).
**Корень:** read-modify-write через PATCH без проверки affected-rows и без INSERT-фолбэка.
**Фикс:** `Prefer: return=representation` → если PATCH вернул пустой массив (0 строк), делаем INSERT `{id, plan:"free", payg_credits:n}`. Теперь поведение = upsert, как в SQLite.
**Тест:** `test_supa.py::TestAddPaygCredits` (2): инкремент существующей строки; вставка при отсутствии (мок httpx, без сети).

### [HIGH] supa.set_user_plan: апгрейд подписки МОЛЧА теряется, если профиля ещё нет — supa.py:83 (ПОЧИНЕНО)
**Симптом:** Тот же класс, что выше: PATCH `profiles` по несуществующей строке = 0 строк, юзер оплатил подписку → остаётся `free`. SQLite-путь upsert'ит, Supabase — нет.
**Корень:** PATCH без INSERT-фолбэка.
**Фикс:** `return=representation` + INSERT `{id, plan}` при 0 строк.
**Тест:** `test_supa.py::TestSetUserPlan` (2): PATCH существующей (без INSERT); INSERT при отсутствии.

### [MEDIUM] Гейт-рассинхрон: jobs идут в Postgres, а billing — в локальный SQLite на эфемерном Modal-контейнере — cloud_state.py:26 vs supa.py:25
**Симптом:** На Modal при `STORAGE_BACKEND=r2` + Supabase-ключи, но БЕЗ `BILLING_ENABLED`: `cloud_enabled()` = True (jobs/артефакты в Postgres), но `supa_enabled()` = False → `record_usage`/`get_profile`/`set_user_plan`/`add_payg_credits` пишут в локальную `tmp/jobs.db` Modal-контейнера, который scale-to-zero → расход/план/PAYG ТЕРЯЮТСЯ между запросами.
**Корень:** Два независимых гейта (`cloud_enabled` завязан на `STORAGE_BACKEND=r2`, `supa_enabled` — на `BILLING_ENABLED`). Это задокументировано как намеренное в supa.py docstring, но на боевом Modal без `BILLING_ENABLED` биллинг де-факто не персистится.
**Фикс:** НЕ чинил — это продуктовое решение фаундера (когда включать биллинг). Рекомендация оркестратору/фаундеру: на Modal ставить `BILLING_ENABLED=true` ВМЕСТЕ с `STORAGE_BACKEND=r2`, ИЛИ свести оба к одному cloud-гейту. Сейчас — задокументировать как обязательную пару env на деплое.

### [MEDIUM] PostgREST filter-injection через значения с запятой/спецсимволами — supa.py / cloud_state.py (params eq.{value})
**Симптом:** Значения (`user_id`, `job_id`, `clip_id`, `audio_sha`) подставляются в `params={"id": f"eq.{value}"}`. httpx URL-кодирует большинство символов, НО запятую (sub-delim) не кодирует → значение вида `eq.x,plan.neq.foo` теоретически может расширить PostgREST-фильтр.
**Корень:** конкатенация значения в PostgREST-оператор без экранирования.
**Фикс:** НЕ чинил (низкая эксплуатируемость). `user_id` приходит из проверенного JWT `sub` (UUID), `job_id`/`clip_id` — серверные `job_<hex>`/`clip_NN`, `audio_sha` — hex. Контролируемых пользователем строк с запятой в этих фильтрах нет. Рекомендация: при появлении пользовательских фильтр-значений — PostgREST-quoting (`eq."<value>"` с экранированием `"`).

### [LOW] verify_signature принимает любой scheme-префикс записи подписи, не только v1 — polar.py:71-74
**Симптом:** Запись заголовка `vX,<sig>` с любым префиксом сравнивается с нашим HMAC (мы считаем только v1-HMAC). Если запись без запятой — берётся целиком как sig.
**Корень:** `entry.partition(",")[2] if "," in entry else entry` игнорирует версию.
**Фикс:** НЕ чинил — безопасно: сравнение всё равно constant-time против ПРАВИЛЬНОГО v1-HMAC, чужой scheme просто не совпадёт. Косметика спецификации, не уязвимость. Тайминг-безопасность (`hmac.compare_digest`), анти-replay (окно ±300с) и tampered-body — корректны и покрыты официальным тест-вектором Standard Webhooks.

## Что проверено и ОК (не баги)
- **auth.py JWT:** нет `alg=none`; HS256 и асимметрия (ES256/RS256) — взаимоисключающие пути по `jwt_secret` → нет key-confusion; `exp`+`aud` проверяются; чужой issuer отсекается через JWKS нашего проекта; dual-mode bypass корректно гейтится `supabase_auth_enabled()` (только при заданном `SUPABASE_URL`); ошибки → единый `AuthError` (нет тихих фолбэков).
- **billing.check_quota / credits_per_video:** граница 60 мин = 1 кредит, 61 = 2, 0 = 1; `MAX_VIDEO_MINUTES` потолок для всех планов; per-video cap Free=60; `monthly_remaining = max(0, …)` (нет отрицательных); split месячный→PAYG арифметически верен; `resolve_plan(None|bogus)` → free (безопасный дефолт). Всё покрыто тестами.
- **storage.py D6:** долговечный `r2://<key>` + ре-подпись на чтении (`resolve_media_url`) корректно лечит протухание presigned (403); upload/presign оборачивают сбой в JobError (правило №8).
- **db.row_to_wire:** http/r2-маркер отдаются как есть, относительный префиксится `media/<job>/`; `_resolve_clip_urls` ре-подписывает на чтении.
- **db._ensure_column:** ALTER идемпотентен (проверяет PRAGMA table_info).

## Передать оркестратору (чужие/общие файлы)
1. **[CRITICAL] PAYG не списывается + двойной учёт минут** — нужен новый примитив списания (`db.deduct_payg_credits` + supa) и правка `tasks._record_usage` (минуты в месячный учёт = только `from_monthly_min`; PAYG списывать `ceil(from_payg_min/60)`). Сейчас `check_quota.from_payg_min` имеет 0 потребителей. Готов добавить db/supa-примитив в свой ownership по утверждённому контракту.
2. **[MEDIUM] Гейт-рассинхрон Modal** — на деплое `STORAGE_BACKEND=r2` обязан идти в паре с `BILLING_ENABLED=true`, иначе usage/plan/PAYG теряются на scale-to-zero. Либо унифицировать гейты (правка cloud_state.py/supa.py — мой ownership, но затрагивает продуктовое решение → жду подтверждения).
3. main.py/tasks.py — call-site критического бага №1 (read-only для меня).

## Не успел / открыто
- I/O-функции cloud_state.py (PostgREST jobs/artifacts/clip_edits) покрыты только PURE-хелперами (`first_row`/`lock_applied`); полный httpx-мок-тест обёрток — кандидат, но обёртки тонкие и единообразны с supa.py.
- PostgREST comma-injection (LOW) — оставлен на будущее (нет пользовательских фильтр-значений сегодня).
