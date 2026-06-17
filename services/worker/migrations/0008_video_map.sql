-- 0008_video_map.sql — Карта видо (объяснимость): нарратив + главы + цветные моменты.
--
-- Применить в Supabase (Dashboard → SQL Editor → Run) ИЛИ через MCP apply_migration. Идемпотентна.
--
-- Кросс-контейнерно (Modal): spawned generate_video_map_job ПИШЕТ артефакт VideoMap в эту колонку,
-- web-контейнер (GET /jobs/{id}/video-map) его ЧИТАЕТ. Без этой колонки cloud save_video_map
-- упадёт ЯВНО (правило №8 — никаких тихих фолбэков). Локальный dev пишет на диск, колонка не нужна.
--
-- Хранится как jsonb (VideoMap.model_dump): {status, error, narrative, chapters:[{...,moments:[...]}]}.
-- Колонка на той же строке job_artifacts (job_id), что и meta/segments/transcript.

alter table public.job_artifacts
    add column if not exists video_map jsonb;
