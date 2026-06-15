-- 0005_promo_codes.sql — промокоды (бесплатные кредиты для трайла, БЕЗ оплаты/Polar).
--
-- Применить в Supabase (Dashboard → SQL Editor → Run). Идемпотентна.
--
-- Промокод = код → N не-сгорающих PAYG-кредитов, начисляемых НАПРЯМУЮ (не через Polar/checkout).
-- Гасит залогиненный юзер на сайте (`/account` или дашборд → «Redeem a code») вызовом RPC
-- redeem_promo. Атомарно, один раз на юзера (unique code+user), не больше max_uses всего.
-- Создать сам код: insert into promo_codes(code, credits, max_uses, note) values (...);

create table if not exists public.promo_codes (
  code text primary key,
  credits integer not null check (credits > 0),
  max_uses integer not null default 1 check (max_uses > 0),
  used_count integer not null default 0,
  active boolean not null default true,
  note text,
  created_at timestamptz not null default now()
);
alter table public.promo_codes enable row level security;  -- без политик → только definer-функция/service_role

create table if not exists public.promo_redemptions (
  id uuid primary key default gen_random_uuid(),
  code text not null references public.promo_codes(code),
  user_id uuid not null references auth.users(id) on delete cascade,
  credits integer not null,
  created_at timestamptz not null default now(),
  unique (code, user_id)  -- один юзер не погасит код дважды
);
alter table public.promo_redemptions enable row level security;  -- без политик

-- Атомарное погашение: кредитует ТОЛЬКО auth.uid() (вызывающего) на фикс. кредиты кода.
create or replace function public.redeem_promo(p_code text)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_user uuid := auth.uid();
  v_code public.promo_codes;
  v_balance integer;
begin
  if v_user is null then
    return jsonb_build_object('ok', false, 'error', 'not_authenticated');
  end if;
  select * into v_code from public.promo_codes
    where lower(code) = lower(trim(p_code)) and active for update;
  if not found then
    return jsonb_build_object('ok', false, 'error', 'invalid_code');
  end if;
  if v_code.used_count >= v_code.max_uses then
    return jsonb_build_object('ok', false, 'error', 'code_used_up');
  end if;
  begin
    insert into public.promo_redemptions(code, user_id, credits)
      values (v_code.code, v_user, v_code.credits);
  exception when unique_violation then
    return jsonb_build_object('ok', false, 'error', 'already_redeemed');
  end;
  insert into public.profiles(id, plan, payg_credits)
    values (v_user, 'free', v_code.credits)
    on conflict (id) do update
      set payg_credits = public.profiles.payg_credits + excluded.payg_credits
    returning payg_credits into v_balance;
  update public.promo_codes set used_count = used_count + 1 where code = v_code.code;
  return jsonb_build_object('ok', true, 'credits', v_code.credits, 'balance', v_balance);
end;
$$;

revoke all on function public.redeem_promo(text) from public, anon;
grant execute on function public.redeem_promo(text) to authenticated;
