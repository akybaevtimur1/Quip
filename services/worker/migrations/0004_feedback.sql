-- 0004_feedback.sql — таблица отзывов (фидбэк-виджет на сайте).
--
-- Применить в Supabase (Dashboard → SQL Editor → Run). Идемпотентна.
--
-- Фидбэк-модалка (apps/web FeedbackWidget) пишет сюда напрямую браузерным клиентом
-- (anon/authenticated). INSERT разрешён всем; SELECT-политики НЕТ → читать может только
-- сервер (service_role) / владелец через дашборд. Спам ограничен длиной сообщения.

create table if not exists public.feedback (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete set null,
  email text,
  message text not null,
  path text,
  created_at timestamptz not null default now(),
  constraint feedback_message_len check (char_length(message) between 1 and 5000)
);

alter table public.feedback enable row level security;

drop policy if exists feedback_insert_any on public.feedback;
create policy feedback_insert_any on public.feedback
  for insert to anon, authenticated with check (true);
