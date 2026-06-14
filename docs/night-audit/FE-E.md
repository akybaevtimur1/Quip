# FE-E (Pricing/Checkout) — отчёт агента

## Сводка
- Файлов проверено: 9 owned (pricing/page.tsx, Pricing.tsx, PricingCards.tsx, Comparison.tsx,
  CheckoutNotice.tsx, CheckoutCta.tsx, lib/plans.ts, lib/polar.ts, app/checkout/route.ts)
  + cross-check `services/worker/app/billing.py` (source of truth), `lib/faq.ts`,
  `components/ui/Button.tsx`, `lib/supabase/config.ts` (read-only).
- Багов найдено: **1** (crit 0 / high 1 / med 0 / low 0) — все в ЧУЖИХ файлах (FE-A).
- Багов починено: **0** (единственный баг — в `lib/faq.ts`, чужой ownership → передаю оркестратору).
- Тесты добавлены: 0 (нет правок в моих файлах; pure-логика лимитов живёт в billing.py = BE-F).
- Прогон: `pnpm --filter web exec tsc --noEmit` → **EXIT 0** (чисто);
  `pnpm --filter web lint` → **EXIT 0** (чисто). Baseline зелёный, мои файлы не трогал.

## Number-by-number: lib/plans.ts vs billing.py PLANS (source of truth)

| Поле | billing.py | plans.ts | Совпадает |
|------|-----------|----------|-----------|
| Free price | `price_usd=0.0` | `price: 0` | ✅ |
| Free monthly | `monthly_videos=2` (→120 мин) | `"2 videos / month"`, `"120 min total"` | ✅ |
| Free per-video cap | `max_video_minutes=60` | `"a single video can be up to 60 min"` | ✅ |
| Free watermark | `watermark=True` | `"720p export with a small watermark"` | ✅ |
| Free resolution | `max_resolution=720` | `720p` | ✅ |
| Starter price | `price_usd=10.0` | `price: 10` | ✅ |
| Starter monthly | `monthly_videos=10` (→600 мин) | `"10 videos / month"`, `"600 min total"` | ✅ |
| Starter cap | `max_video_minutes=None` | (нет cap; "minutes proportionally") | ✅ |
| Starter watermark/res | `False` / `1080` | `"No watermark, 1080p export"` | ✅ |
| Pro price | `price_usd=25.0` | `price: 25` | ✅ |
| Pro monthly | `monthly_videos=30` (→1800 мин) | `"30 videos / month"`, `"1800 min total"` | ✅ |
| Pro priority | `priority=True` | `"Priority processing in the queue"` | ✅ |
| Pro cap/res | `None` / `1080` | (нет cap, 1080 наследует) | ✅ |
| PAYG price | `PAYG_PRICE_USD=2.0` | `pricePerVideo: 2` | ✅ |
| PAYG per order | `PAYG_CREDITS_PER_ORDER=1` (=60 мин) | `"one video covers up to 60 minutes"` | ✅ |
| Модель списания | пропорциональная по минутам (docstring: «124 мин ≈ 2.07, НЕ округление вверх до 3») | `"Longer videos use minutes proportionally"` | ✅ |

**Вывод: `lib/plans.ts` ПОЛНОСТЬЮ в синхроне с billing.py. Ни одного расхождения цен/лимитов
в моих файлах.** Копирайт в Pricing.tsx / pricing/page.tsx / Comparison.tsx / PricingCards.tsx
тоже согласован с проп-моделью («one credit = one video, up to 60 minutes», «minutes
proportionally», «never expire»).

## Баги

### [HIGH] FAQ противоречит модели списания billing.py — `apps/web/lib/faq.ts:21,25`
**Симптом:** Customer-facing FAQ даёт ДВА числа, расходящихся с источником правды (billing.py):
1. `faq.ts:21` (вопрос «What is a credit»): *"a 90-minute upload is 2 [credits]"* — описывает
   округление ВВЕРХ. Но гейт квоты (`billing.check_quota`) списывает **пропорционально по
   минутам**: 90 мин = 1.5 видео, не 2 (docstring billing.py явно: «124 мин ≈ 2.07 видео,
   а НЕ округление вверх до 3»). `credits_per_video()` с ceil используется ТОЛЬКО для
   целочисленной колонки лога `usage_events.credits`, а НЕ для расчёта остатка. Так что
   «90 мин = 2» — обещание, противоречащее тому, как реально тратится баланс.
2. `faq.ts:25` (вопрос «Is the free plan actually free»): *"2 videos a month, up to **30
   minutes** each"*. billing.py Free `max_video_minutes=**60**`. Заявленные 30 мин ВДВОЕ
   занижены — пользователь, видя «30 мин», не загрузит 45-минутное видео, которое на самом
   деле разрешено. Прямое расхождение с лимитом.

   (Доп.: `faq.ts:9` «up to 90 minutes» как макс-длина — тоже дрейф: тех. потолок
   `MAX_VIDEO_MINUTES=180`. Низкий приоритет/консервативно, но непоследовательно.)

**Корень:** FAQ написана под раннюю «кредит-ceil» модель; billing.py с тех пор перешёл на
проп-минуты + Free cap=60. plans.ts обновили, faq.ts — нет.
**Фикс:** НЕ чинил — `lib/faq.ts` принадлежит **FE-A** (см. README матрицу: `lib/faq.ts` →
FE-A). Передаю оркестратору. Предлагаемая правка:
- q «What is a credit»: убрать «a 90-minute upload is 2» ИЛИ заменить на проп-формулировку
  («a 90-minute upload uses 1.5 videos / minutes proportionally») — чтобы совпасть с plans.ts
  `"Longer videos use minutes proportionally"`.
- q «Is the free plan actually free»: «up to **60** minutes each» (не 30).
- (опц.) q «videos work best»: «up to **180** minutes» или убрать число.
**Тест:** н/п (копирайт; источник чисел = billing.py, его покрывает test_billing у BE-F).

## Проверено и ЧИСТО (не баги)

- **checkout/route.ts** — token absent → `/pricing?checkout=unavailable` (залогинен) или
  `/signup` (аноним), без краша (line 30-36). `external_id` → `customerExternalId = supabase
  user.id` (line 40-42, корректное имя параметра @polar-sh/nextjs). successUrl на `url.origin`.
  `isSupabaseConfigured`-гейт + try/catch вокруг getUser — деградация без ключей. ✅
- **lib/polar.ts** — `checkoutHref(free)` → `/signup`; платные/PAYG → `/checkout?products=<id>`.
  Нет битых `#`-ссылок. Product IDs override через `NEXT_PUBLIC_*`. ✅
- **CheckoutCta.tsx** — `/checkout` рендерится как простой `<a>` (top-level navigation следует
  307 на polar.sh в один клик, без RSC-prefetch/CORS); внутренние таргеты — `<Link
  prefetch={false}>`. Простой `<a>` не делает RSC-prefetch by design → CORS-проблема Polar
  закрыта корректно. pending-стейт блокирует двойной сабмит. ✅
- **a11y рекомендованного CTA** — Pro CTA `variant="primary"` = `bg-ink text-bg` (near-white
  на тёмном, AA-safe); бейдж «Recommended» = `text-bg` (near-black) на coral (≈5.5:1, AA-safe).
  White-on-coral (3.09:1) НЕ используется на pricing. ✅
- **Копирайт моих файлов** (Pricing/PricingCards/Comparison/CheckoutNotice/pricing page) —
  все числа/модель согласованы с billing.py (см. таблицу). ✅
- **Hydration** — CheckoutNotice/CheckoutCta `"use client"`; useSearchParams обёрнут в
  `<Suspense>` на странице (pricing/page.tsx:19). ✅

## Передать оркестратору (чужие/общие файлы)
- **[HIGH] `apps/web/lib/faq.ts` (FE-A):** Free cap «30 minutes» → должно быть **60**
  (billing.py `max_video_minutes=60`); «90-minute upload is 2 credits» противоречит
  проп-модели списания billing.py. Это customer-facing money-copy → лечить заодно с
  pricing. См. деталь выше.

## Не успел / открыто
- Ничего. Все 9 owned-файлов проверены, оба гейта (tsc/lint) зелёные, мои файлы не правил
  (расхождений в них нет).
