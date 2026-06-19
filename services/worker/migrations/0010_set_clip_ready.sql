-- 0010_set_clip_ready.sql — атомарный per-clip video_url для инкрементальной выдачи клипов.
--
-- Применить в Supabase (Dashboard → SQL Editor → Run, или MCP apply_migration). Идемпотентна.
--
-- ЗАЧЕМ: run_pipeline теперь персистит ВСЕ клипы со статусом "rendering" и ПУСТЫМ video_url
-- сразу после Select, а каждый параллельный фан-аут-контейнер (reframe_render_clip) проставляет
-- СВОЙ video_url, как только клип отрендерен/залит → юзер видит клипы по одному, а не разом в
-- конце. Параллельные контейнеры обновляют РАЗНЫЕ индексы массива jobs.clips одновременно.
--
-- ПОЧЕМУ RPC, а не PATCH: PostgREST-PATCH целой колонки clips = read-modify-write на клиенте
-- (две гонки потеряли бы запись друг друга). jsonb_set на СЕРВЕРЕ внутри одного UPDATE атомарен:
-- Postgres сериализует UPDATE'ы одной строки (блокировка строки), поэтому два контейнера,
-- пишущие clips[i] и clips[j] (i≠j), НИКОГДА не теряют запись — каждый видит свежий clips и
-- меняет только свой индекс. SECURITY DEFINER + service_role: пишет только сервер (как остальной
-- cloud_state). Возвращает число обновлённых строк (0 = нет джоба/индекса → вызыватель увидит,
-- никаких тихих фолбэков, правило №8).

create or replace function public.set_clip_video_url(
    p_job_id text,
    p_idx int,
    p_url text
) returns int
language plpgsql
security definer
set search_path = public
as $$
declare
    n int;
begin
    update public.jobs
       set clips = jsonb_set(clips, array[p_idx::text, 'video_url'], to_jsonb(p_url), false),
           updated_at = now()
     where id = p_job_id
       and clips is not null
       and jsonb_typeof(clips) = 'array'
       and jsonb_array_length(clips) > p_idx;
    get diagnostics n = row_count;
    return n;
end;
$$;

-- service_role вызывает RPC через PostgREST (POST /rest/v1/rpc/set_clip_video_url).
grant execute on function public.set_clip_video_url(text, int, text) to service_role;
