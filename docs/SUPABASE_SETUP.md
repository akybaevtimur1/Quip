# Supabase + прайсинг — что вписать фаундеру (T6)

> Код и миграции готовы. Аккаунты/секреты **создаёт фаундер** (агент их не трогает).
> Этот файл — пошаговый чеклист подключения. Лимиты тарифов — в `services/worker/app/billing.py`.

---

## 0. TL;DR что сделано кодом (готово к подключению)

| Слой | Файл | Статус |
|---|---|---|
| Модель тарифов/лимитов (PURE) | `services/worker/app/billing.py` | ✅ `PLANS`, `check_quota`, `resolve_plan`, `current_month` + тесты |
| Учёт расхода (адаптер) | `services/worker/app/db.py` | ✅ `record_usage` / `get_monthly_usage` (SQLite сейчас; тот же интерфейс → Postgres) |
| Схема БД + RLS | `services/worker/migrations/0001_init_billing.sql` | ✅ profiles / jobs / usage_events + политики |
| Этот чеклист | `docs/SUPABASE_SETUP.md` | ✅ |

**Не сделано (нужен фаундер):** Supabase-проект, ключи, провод auth во фронт/воркер,
вебхук оплаты (Lemon Squeezy) → `profiles.plan`, перенос usage-записи на Postgres. См. §4.

---

## 1. Тарифы и лимиты (где крутить)

Источник правды — **`app/billing.py`** (НЕ в БД, чтобы не было дрейфа). В БД хранится
только `profiles.plan`. Текущие дефолты (тюнинг под юнит-экономику — маржа ~76% на Starter):

| План | Цена/мес | Видео/мес | Минут исходника/мес | Watermark | Качество |
|---|---|---|---|---|---|
| Free | $0 | 2 | 20 | да | 720p |
| Starter | $12 | 20 | 200 | нет | 1080p |
| Pro | $29 | 100 | 1000 | нет | 1080p (приоритет) |

Поменять числа/цены → правишь `PLANS` в `app/billing.py` (тесты в `tests/unit/test_billing.py`
пиннят форму: цены/лимиты растут по тарифам). `watermark`/`max_resolution` пока в модели —
прожиг вотермарки и кап качества подключаются на рендере отдельно (follow-up).

Единица стоимости = **минуты исходника** (доминанта затрат — транскрипция). `check_quota`
сначала бьёт по числу видео, потом по минутам, с честной причиной отказа (анти-surprise-paywall).

---

## 2. Создать Supabase-проект и применить схему

1. Создай проект на https://supabase.com (план **Pro** — грант $50; free пауза через 7 дней простоя).
2. Применить миграцию: **SQL Editor → вставить `services/worker/migrations/0001_init_billing.sql` → Run.**
   (Или `supabase init` + положить файл в `supabase/migrations/` + `supabase db push`.)
3. Проверь: в Table Editor появились `profiles`, `jobs`, `usage_events`; на каждой — RLS **ON**.
4. Зарегистрируй тестового юзера (Authentication → Users) → в `profiles` должна авто-появиться
   строка с `plan='free'` (триггер `handle_new_user`).

---

## 3. Ключи (КУДА вписать — ВАЖНО про безопасность)

В дашборде: **Project Settings → API**.

| Переменная | Значение | Куда | ⚠️ |
|---|---|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Project URL | `apps/web/.env.local` | публичный, ок |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | publishable/anon key | `apps/web/.env.local` | публичный, ок |
| `SUPABASE_URL` | Project URL | воркер `.env` (корень) | — |
| `SUPABASE_SERVICE_ROLE_KEY` | **service_role** key | воркер `.env` (корень), **только сервер** | 🔴 НИКОГДА в `NEXT_PUBLIC_*` / фронт |

🔴 **`service_role` обходит RLS.** Любая `NEXT_PUBLIC_*` переменная уезжает в браузер.
Service-role — только в воркере (серверный код), которым пишем `plan` и `usage_events`.

---

## 4. Что доподключить (провод — follow-up для фаундера/след. сессии)

1. **Auth во фронте**: `@supabase/ssr` + `supabase-js` (запиннить версии, коммитить lockfile).
   Логин/сессия → `user.id` (uuid) попадает в запросы создания джоба.
2. **Воркер: usage на Postgres.** Сейчас `record_usage`/`get_monthly_usage` пишут в SQLite.
   Для облака — та же пара функций, но через service-role в `usage_events` (INSERT) и
   агрегат-SELECT (см. хвост миграции). Адаптер уже изолирован в `db.py` → подменить тело.
3. **Гейт квоты при создании джоба** (где включить): в `app/main.py` `create_job`/`create_upload_job`
   ПЕРЕД постановкой задачи:
   ```python
   from app.billing import check_quota, current_month
   plan = get_profile_plan(user_id)              # из profiles (service-role)
   used = db.get_monthly_usage(user_id, current_month())
   d = check_quota(plan, used["videos"], used["minutes"], source_minutes_est)
   if not d.allowed:
       raise HTTPException(status_code=402, detail=d.reason)  # 402 Payment Required
   ```
   `source_minutes_est` — оценка длины исходника (для URL можно по ffprobe после download;
   для upload — после import). Записать расход `db.record_usage(user_id, job_id, minutes, month)`
   ПОСЛЕ успешной транскрипции (точные минуты = `transcript.duration/60`).
4. **Оплата (Lemon Squeezy)**: вебхук `order_created`/`subscription_updated` → серверный
   эндпоинт → `update profiles set plan=... where id=user_id` (service-role). Merchant-of-Record
   сам считает налоги. Маппинг variant_id → plan_id держать рядом с billing.py.
5. **Watermark/кап качества**: `PlanLimits.watermark`/`max_resolution` есть в модели; прожиг
   вотермарки (ASS-оверлей или ffmpeg drawtext) и кап scale до 720p для free — подключить в
   рендере (`tasks.render_edit_to_file`) по плану юзера.

---

## 5. Почему так (анти-Vizard)

Простые лимиты «X видео / N минут в месяц», без кредитов-казино и surprise-paywall: юзер
заранее видит, что даёт free, и получает честную причину отказа (`check_quota.reason`).
Тарифы — в коде (прозрачно, версионируется), не в скрытых конфигах. См. `docs/LAUNCH_BRIEF_2026-06-13.md` §2.
