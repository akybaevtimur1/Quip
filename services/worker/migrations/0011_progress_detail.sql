-- 0011_progress_detail.sql — live-narration counts shown during processing (before clips exist).
--
-- Применить в Supabase (Dashboard → SQL Editor → Run) ИЛИ через MCP apply_migration. Идемпотентна.
--
-- Эти счётчики наполняет воркер на границах стадий (run.py → db.set_progress_detail):
--   source_minutes  — длина исходника в минутах (после import).
--   transcript_words — число слов транскрипта (после transcribe).
--   moments_found   — число выбранных моментов = число клипов (после select).
-- GET /jobs (row_to_wire) отдаёт их в Job; фронт (JobProgress) показывает «N words / N found»,
-- чтобы окно 0–60% (до появления карточек) не было мёртвым. Все nullable → старые строки/код целы.

alter table public.jobs add column if not exists source_minutes double precision;
alter table public.jobs add column if not exists transcript_words integer;
alter table public.jobs add column if not exists moments_found integer;
