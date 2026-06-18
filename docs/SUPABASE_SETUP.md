# Supabase + прайсинг — что вписать фаундеру (T6)

> ⚠️ **УСТАРЕЛО.** Supabase уже подключён (проект `qiagetbnsssvbiowuxpp`, миграции 0001–0007),
> биллинг ЖИВОЙ через **Polar** (не Lemon Squeezy), прайсинг = кредит-модель (**Starter $15 / Pro $35 /
> PAYG $3**), а НЕ старые «$12 / 20 видео» из тела этого файла. Не следуй этому файлу для проводки
> оплаты — см. `docs/README.md` и `services/worker/app/billing.py`. Оставлен как история.

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
пиннят форму: цены/лимиты растут по тарифам). `watermark`/`max_resolution` ПОДКЛЮЧЕНЫ на рендере
(2026-06-18): план владельца резолвится СЕРВЕРНО (`jobs.user_id` → `profiles.plan` →
`billing.resolve_render_policy`); free прожигает drawtext-вотермарку «Made with Quip» и капится
720p. Обойти с клиента нельзя (план не приходит с фронта). См. `app/run.py:resolve_clip_render_policy`.

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
5. **Watermark/кап качества** (СДЕЛАНО 2026-06-18): `PlanLimits.watermark`/`max_resolution`
   прожигаются на рендере. Чистая decision-функция `billing.resolve_render_policy(plan_id, *,
   local_dev)` → `RenderPolicy(watermark, max_resolution)`. Резолвится СЕРВЕРНО из плана владельца
   (`run.resolve_clip_render_policy`: `db.get_user_plan(user_id)`); free → drawtext-вотермарка
   «Made with Quip» (`stage5_render.build_watermark_drawtext`, аддитивный оверлей — кадровую сетку
   Δ=0 НЕ трогает) + кап 720p (`stage5_render.clamp_output_dims`). Батч-путь: `user_id` несётся в
   per-clip фан-аут (`run.clip_spawn_args` → `reframe_render_clip`). Редактор-путь:
   `tasks.render_edit_to_file` резолвит owner из `jobs.user_id`. Local dev (нет owner) → без
   вотермарки. Обойти с клиента невозможно.

---

## 5. Почему так (анти-Vizard)

Простые лимиты «X видео / N минут в месяц», без кредитов-казино и surprise-paywall: юзер
заранее видит, что даёт free, и получает честную причину отказа (`check_quota.reason`).
Тарифы — в коде (прозрачно, версионируется), не в скрытых конфигах. См. `docs/LAUNCH_BRIEF_2026-06-13.md` §2.

---

## 6. Анти-абьюз free-плана: verified email + блок одноразовых доменов (СДЕЛАНО 2026-06-18)

Free = 2 видео абьюзят пачками аккаунтов на одноразовых ящиках. Две меры, **серверно
авторитетные** (фронт — только UX):

1. **Verified email обязателен для free-job.** Гейт `main._enforce_free_identity`
   (вызывается в `create_job`/`create_upload_job`/`create_upload_url`/`complete_upload`
   ПЕРЕД квотой): если план владельца = `free` и email НЕ подтверждён → **HTTP 403**
   «Verify your email…». Платные планы — мимо (заплатил → не абьюз).
2. **Блок одноразовых доменов.** `billing.is_disposable_email(email)` (PURE, денилист
   `DISPOSABLE_EMAIL_DOMAINS`) → free-job с temp-mail домена = **403** «use a real email».
   Зеркало на фронте `apps/web/lib/disposableEmail.ts` (валидация до сабмита в `AuthForm`).

**Где берём «verified».** Supabase access-token (JWT) **НЕ несёт** `email_confirmed_at` —
в нём только `email`, `app_metadata.provider(s)`, `user_metadata.email_verified`
(см. [JWT Claims Reference](https://supabase.com/docs/guides/auth/jwt-fields)). Поэтому
`auth.email_is_verified(claims)` решает так: (1) провайдер Google → verified (Google уже
проверил email; **Google-входы НЕ блокируются**); (2) `user_metadata.email_verified is True`
→ verified; (3) иначе **авторитетный админ-lookup** `auth.users.email_confirmed_at` через
service-role Auth Admin API (`supa.auth_user_email_confirmed` → `GET /auth/v1/admin/users/{id}`).
Ошибка lookup → **502** (видимая, без тихого пропуска абьюзера).

### 🔴 Действие фаундера (ОБЯЗАТЕЛЬНО, иначе мера не работает)

Гейт проверяет `email_confirmed_at`, но **подтверждение должно быть включено в дашборде**:

- **Authentication → Providers → Email → «Confirm email» = ON** (для email/password signup
  Supabase шлёт письмо и НЕ ставит `email_confirmed_at`, пока юзер не подтвердит). Без этого
  email/password-аккаунты создаются сразу «подтверждёнными» → verified-гейт пропускает всех.
- OTP-флоу (код на email в `AuthForm`) подтверждает email самим вводом кода — это и есть
  верификация.
- Гейт активен только при `BILLING_ENABLED` + `SUPABASE_URL` (+ `SUPABASE_SERVICE_ROLE_KEY`
  для админ-lookup). В dev (без них) — инертен.

Расширить денилист одноразовых доменов — добавить строку в `billing.DISPOSABLE_EMAIL_DOMAINS`
И в зеркало `apps/web/lib/disposableEmail.ts` (держать в синхроне).
