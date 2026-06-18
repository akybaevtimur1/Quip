-- 0009_agent_runs_rls.sql — закрыть утечку чат-ранов агента (Supabase security advisor: ERROR).
--
-- Применить: Supabase Dashboard → SQL Editor → вставить и Run. Идемпотентна.
--
-- Проблема: public.agent_runs (приватные чат-раны редактора) была в public-схеме БЕЗ RLS →
-- читаема через ПУБЛИЧНЫЙ anon-ключ PostgREST = утечка чужих чатов. Advisor: rls_disabled_in_public.
-- Доступ к таблице идёт ТОЛЬКО через воркер на service-role (фронт её напрямую не читает —
-- supabase.from() на клиенте используется лишь для feedback). service-role обходит RLS, поэтому
-- включение RLS без политик = deny-all для anon/authenticated, поведение приложения НЕ меняется
-- (тот же паттерн, что у promo_codes/promo_redemptions/runs/transcript_cache).

alter table public.agent_runs enable row level security;
