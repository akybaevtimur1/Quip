-- 0014_style_preferences.sql — per-user default caption/hook look (domain 5: settings memory).
--
-- Применить в Supabase (Dashboard → SQL Editor → Run) ИЛИ через MCP apply_migration. Идемпотентна.
--
-- ЗАЧЕМ: юзер настроил субтитры/хук под свой стиль → хочет, чтобы СЛЕДУЮЩИЕ видео стартовали
-- с ЭТОГО стиля, а не с захардкоженного preset_a. Храним «look» (caption style + highlight +
-- hook-style-поля) одним jsonb-блобом на профиль (own-scoped, как plan/payg_credits). На создании
-- дефолтного ClipEdit (ensure_edit) воркер читает этот блоб владельца джобы и сидит из него.
-- Это первый шаг «подстройки под стиль юзера». Per-video («применить ко всем клипам») и per-clip
-- стилю отдельная колонка не нужна — они живут в clip_edits.
--
-- service_role пишет/читает (PUT /me/style-preference, ensure_edit). RLS не меняем — profiles уже
-- own-scoped (profiles_select_own), а сервер ходит service-role'ом в обход RLS, как для plan.

alter table public.profiles add column if not exists style_preferences jsonb;
