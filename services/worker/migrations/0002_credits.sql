-- 0002_credits.sql — переход на кредит-модель Quip (Supabase Postgres).
--
-- Применить ПОСЛЕ 0001_init_billing.sql (Dashboard → SQL Editor → Run, или supabase db push).
-- Идемпотентна (IF NOT EXISTS) — повторный прогон безопасен.
--
-- Кредит-модель: 1 «видео» = до 60 мин исходника; длиннее → credits = ceil(минуты/60).
-- Лимит плана = число видео-кредитов в месяц (app/billing.py = источник правды чисел).
--   • profiles.payg_credits — не сгорающий баланс разовых покупок ($2/кредит, PAYG).
--   • usage_events.credits  — кредитов списано за обработанное видео (для месячного остатка).

-- Баланс PAYG-кредитов (пишет ТОЛЬКО сервер: вебхук разовой оплаты Polar, service-role).
alter table public.profiles
  add column if not exists payg_credits integer not null default 0;

-- Кредиты, списанные за конкретное обработанное видео.
alter table public.usage_events
  add column if not exists credits integer not null default 1;

-- Месячный агрегат для квоты (сервер, service-role):
--   select coalesce(sum(credits), 0) as credits, count(*) as videos
--   from public.usage_events where user_id = :uid and month = :month;
-- Решение «пускать ли джоб» — app/billing.check_quota(plan, used_credits, payg_credits, minutes):
--   тянет сначала месячный остаток, затем payg_credits (не сгорает).
