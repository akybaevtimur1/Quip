-- 0007_agent_runs.sql — W3: агентный чат-редактор клипа. Один ряд = один прогон агента над клипом.
--
-- Применить в Supabase (Dashboard → SQL Editor → Run) ИЛИ через MCP apply_migration. Идемпотентна.
--
-- Кросс-контейнерно (Modal): spawned agent_edit_job ПИШЕТ события, web-контейнер их ЧИТАЕТ (поллинг).
-- events = jsonb-лента [{role,text,action_kind?,before?,after?}, …] (роли: user/thinking/action/
--   agent/error). status = running|done|failed|cancelled (свободный text, как jobs.status).
-- function_call_id + cancellable — Stop (отмена через modal.FunctionCall.from_id(id).cancel()).
-- Биллинг: агент-путь минут НЕ списывает (это правки редактора пост-генерации).

create table if not exists public.agent_runs (
    run_id text primary key,
    job_id text not null,
    clip_id text not null,
    user_id text,
    status text not null default 'running',
    events jsonb not null default '[]'::jsonb,
    error text,
    function_call_id text,
    cancellable boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_agent_runs_clip on public.agent_runs (job_id, clip_id);
create index if not exists idx_agent_runs_running on public.agent_runs (job_id, clip_id, status);
