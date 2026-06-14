-- 0003_usage_idempotency.sql — защита от двойного учёта расхода (Supabase Postgres).
--
-- Применить ПОСЛЕ 0002_credits.sql (Dashboard → SQL Editor → Run, или supabase db push).
-- Идемпотентна (IF NOT EXISTS) — повторный прогон безопасен.
--
-- ЗАЧЕМ: метеринг расхода (app/tasks._meter → db.record_usage + db.deduct_payg) не был
-- идемпотентен — повторный прогон/ретрай одного job_id записал бы расход и СПИСАЛ PAYG
-- второй раз (перезаряд). Код теперь делает check-then-act по job_id (db.py/supa.py:
-- record_usage возвращает False на дубликат → _meter не списывает PAYG повторно), а этот
-- UNIQUE-индекс даёт durable-гарантию на уровне БД (защита от гонки двух воркеров).
--
-- Частичный (WHERE job_id is not null): анонимные/служебные записи без job_id дедупом
-- НЕ покрываются (NULL'ы в Postgres различны — несколько NULL job_id допустимы).
--
-- NB: если в usage_events УЖЕ есть дубли job_id (маловероятно — биллинг ещё не запускался),
-- создание индекса упадёт. Тогда сначала почистить дубли:
--   delete from public.usage_events a using public.usage_events b
--   where a.id > b.id and a.job_id = b.job_id and a.job_id is not null;

create unique index if not exists usage_events_job_id_key
  on public.usage_events (job_id)
  where job_id is not null;
