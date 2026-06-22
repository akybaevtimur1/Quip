-- 0013_reframe_regions.sql — durable per-clip shot regions (domain 1: real shot boundaries).
--
-- Применить в Supabase (Dashboard → SQL Editor → Run) ИЛИ через MCP apply_migration. Идемпотентна.
--
-- ЗАЧЕМ: редактор (таб «Shots») рисует полосу пошотового кадрирования из РЕАЛЬНЫХ границ сцен
-- (PySceneDetect), которые batch-пайплайн уже посчитал в reframe_segment. Но эти регионы НИГДЕ
-- не персистились → /reframe пересчитывал тяжёлый CV (PySceneDetect+ASD+MediaPipe) на лету; на
-- холодном контейнере он медленный/падает (видели 500 на /reframe) → фронт откатывался на ФЕЙКОВЫЕ
-- равные временные чанки (не привязанные к склейкам). Эта колонка делает реальные регионы durable
-- между контейнерами → /reframe для дефолтного интервала отдаёт их МГНОВЕННО, без CV и без скачивания
-- source. Хранится как jsonb-словарь {clip_id: {default_start, default_end, regions:[{t0,t1,mode,
-- points,points_b}]}}; регионы interval-relative (0-based) — ровно то, что вернул reframe_segment.
--
-- Кросс-контейнерно: параллельные фан-аут-контейнеры (render_one_clip) пишут СВОЙ clip_id через
-- atomic-merge RPC ниже (как set_clip_video_url, migration 0010) — без гонок read-modify-write.
-- Локальный dev пишет/читает с диска (analysis/acc_*.json), колонка не нужна (cloud-only, как video_map).

alter table public.job_artifacts add column if not exists reframe_regions jsonb;

-- Атомарный per-clip merge: server-side `||` внутри ОДНОГО UPDATE сериализуется блокировкой строки
-- (Postgres сериализует UPDATE'ы одной строки), поэтому два контейнера, пишущие РАЗНЫЕ clip_id,
-- НИКОГДА не теряют запись друг друга — в отличие от PATCH целой колонки (RMW → гонка, как у
-- set_clip_video_url). Строка job_artifacts уже создана put_job_artifacts (run.py, ДО фан-аута),
-- поэтому UPDATE-only (не INSERT — у job_artifacts NOT NULL meta/segments/transcript). Возвращает
-- число обновлённых строк (0 = нет строки артефактов → вызыватель логирует, не глотает, правило №8).
create or replace function public.merge_reframe_regions(
    p_job_id text,
    p_clip_id text,
    p_value jsonb
) returns int
language plpgsql
security definer
set search_path = public
as $$
declare
    n int;
begin
    update public.job_artifacts
       set reframe_regions = coalesce(reframe_regions, '{}'::jsonb)
                             || jsonb_build_object(p_clip_id, p_value)
     where job_id = p_job_id;
    get diagnostics n = row_count;
    return n;
end;
$$;

-- service_role вызывает RPC через PostgREST (POST /rest/v1/rpc/merge_reframe_regions).
grant execute on function public.merge_reframe_regions(text, text, jsonb) to service_role;
