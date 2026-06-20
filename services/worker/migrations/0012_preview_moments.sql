-- 0012_preview_moments.sql — cosmetic co-watch markers (Part 4). Идемпотентна.
--
-- Применить в Supabase (Dashboard → SQL Editor → Run) ИЛИ через MCP apply_migration.
--
-- job_artifacts.preview_moments — список PreviewMoment {t,kind,intensity}, который воркер пишет
-- ПОСЛЕ transcribe (db.put_job_artifact, upsert), а /jobs/{id}/preview-moments отдаёт фронту для
-- co-watch-маркеров во время обработки. ⚠️ ЧИСТО КОСМЕТИЧЕСКИ: НЕ передаётся в select_segments —
-- LLM-отбор клипов от этого не зависит (качество AI-нарезки не меняется). Nullable → старые строки целы.

alter table public.job_artifacts add column if not exists preview_moments jsonb;
