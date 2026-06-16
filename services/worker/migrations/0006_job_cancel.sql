-- 0006_job_cancel.sql — Stop-кнопка: флаг cancellable + id Modal-функции (для отмены джоба).
--
-- Применить в Supabase (Dashboard → SQL Editor → Run) ИЛИ через MCP apply_migration. Идемпотентна.
--
-- cancellable = true только во FREE-фазе (download/probe, до транскрипции); воркер гасит в false
--   при входе в платную стадию → UI показывает Stop ⇔ cancellable. Отмена в free-фазе = $0 списания
--   (заряд только после set_done; см. tasks._meter).
-- function_call_id = id запущенной Modal-функции (run_job/upload_job), чтобы web-контейнер мог
--   отменить джоб на ДРУГОМ контейнере: modal.FunctionCall.from_id(id).cancel().
-- status='cancelled' — новое значение; jobs.status = свободный text без CHECK (0001) → enum не нужен.

alter table public.jobs add column if not exists function_call_id text;
alter table public.jobs add column if not exists cancellable boolean not null default true;
