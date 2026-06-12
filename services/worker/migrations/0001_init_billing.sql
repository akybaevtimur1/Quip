-- 0001_init_billing.sql — ClipFlow billing/usage схема (Supabase Postgres).
--
-- Применить (любой способ):
--   • Supabase Dashboard → SQL Editor → вставить и Run; ИЛИ
--   • supabase db push (после `supabase init` + положить файл в supabase/migrations/).
-- Идемпотентна (IF NOT EXISTS / OR REPLACE) — повторный прогон безопасен.
--
-- Принципы (security-чеклист Supabase):
--   • RLS включён на КАЖДОЙ public-таблице.
--   • Политики: TO authenticated + предикат владения (select auth.uid()) = user_id.
--   • UPDATE-политики — с USING И WITH CHECK (нет переназначения чужому юзеру).
--   • Тариф (plan) и расход (usage) ПИШЕТ ТОЛЬКО сервер (service-role обходит RLS):
--     у юзера нет update plan и нет insert usage → нет self-upgrade / подделки расхода.
--   • Лимиты тарифов НЕ в БД, а в app/billing.py (один источник правды, без дрейфа).
--     В БД хранится только profiles.plan ('free'|'starter'|'pro').

-- ─────────────────────────── profiles (1:1 к auth.users) ───────────────────────────
create table if not exists public.profiles (
  id         uuid primary key references auth.users (id) on delete cascade,
  plan       text not null default 'free' check (plan in ('free', 'starter', 'pro')),
  created_at timestamptz not null default now()
);
alter table public.profiles enable row level security;

-- юзер видит только СВОЙ профиль; план меняет сервер (вебхук оплаты, service-role).
drop policy if exists profiles_select_own on public.profiles;
create policy profiles_select_own on public.profiles
  for select to authenticated
  using ((select auth.uid()) = id);

-- авто-создание профиля при регистрации (стандартный паттерн Supabase).
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (id) values (new.id) on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ─────────────────────────── jobs (задачи пользователя) ───────────────────────────
create table if not exists public.jobs (
  id             text primary key,
  user_id        uuid not null references auth.users (id) on delete cascade,
  status         text not null default 'queued',
  source_minutes numeric not null default 0,
  created_at     timestamptz not null default now()
);
alter table public.jobs enable row level security;
create index if not exists idx_jobs_user on public.jobs (user_id);

drop policy if exists jobs_select_own on public.jobs;
create policy jobs_select_own on public.jobs
  for select to authenticated
  using ((select auth.uid()) = user_id);

drop policy if exists jobs_insert_own on public.jobs;
create policy jobs_insert_own on public.jobs
  for insert to authenticated
  with check ((select auth.uid()) = user_id);

-- ─────────────────────── usage_events (учёт расхода для лимитов) ───────────────────────
-- 1 строка = 1 обработанное видео. source_minutes (минуты исходника) — доминанта стоимости.
create table if not exists public.usage_events (
  id             bigint generated always as identity primary key,
  user_id        uuid not null references auth.users (id) on delete cascade,
  job_id         text,
  source_minutes numeric not null,
  month          text not null,  -- 'YYYY-MM' (расчётное месячное окно)
  created_at     timestamptz not null default now()
);
alter table public.usage_events enable row level security;
create index if not exists idx_usage_user_month on public.usage_events (user_id, month);

-- юзер ВИДИТ свой расход (UI «осталось N минут»); пишет ТОЛЬКО сервер (service-role)
-- после обработки видео → нет insert-политики у юзера (нельзя занизить/подделать расход).
drop policy if exists usage_select_own on public.usage_events;
create policy usage_select_own on public.usage_events
  for select to authenticated
  using ((select auth.uid()) = user_id);

-- Месячный агрегат (для квоты/UI). Считать на сервере (service-role) ИЛИ из клиента
-- (RLS отдаст только свои строки):
--   select count(*) as videos, coalesce(sum(source_minutes), 0) as minutes
--   from public.usage_events where user_id = :uid and month = :month;
