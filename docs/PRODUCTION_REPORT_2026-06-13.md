# PRODUCTION REPORT — продакшн-оболочка Quip (2026-06-13)

> Автономная сессия по `docs/PRODUCTION_BRIEF_2026-06-13.md` + `/goal`. Цель: превратить
> рабочее ЯДРО (нарезка + редактор) в **продакшн-сайт Quip** — дизайн-система + лендинг +
> авторизация + дашборд + оплата. Ветка **`feat/production-shell`** (от HEAD `feat/mvp-launch`).
> Модель Opus 4.8, дизайн-первым, conventional commits, TDD на pure-логике.

---

## 0. TL;DR

| Фаза | Что | Коммит | Доказательство |
|---|---|---|---|
| **D1** | Дизайн-система зафиксирована | `50a5ff7` | DESIGN.md + globals.css @theme; 3 концепта показаны → ты выбрал |
| **D2** | Продакшн-лендинг (SEO+конверсия) | `feat/production-shell` | 8 секций + OG + sitemap/robots/JSON-LD; скрины `design-md/_research/landing_*` |
| **A1** | Supabase auth (dual-mode) | (web) | вход/регистрация/гейт; `auth_login.png` |
| **D3** | Дашборд / оболочка приложения | `04d67bb` | header+usage+recent+интеграция; `dashboard.png` |
| **P1** | Прайсинг + **Polar.sh** + гейт квоты | (billing) | `/pricing`; вебхук+гейт TDD (18 тестов); `pricing_page.png` |
| **POLISH** | a11y/Lighthouse | `698fdb7` | **Lighthouse 100/100/100/100; LCP 173ms; CLS 0.00** |

**Гейт:** `just check` зелёный (**409 тестов**), `next build` зелёный (15 роутов).
**Бренд:** **Quip** (не ClipFlow — внутреннее имя репо). **Дизайн:** Precision Dark, подогнан под
твой quip.ink (вытащил реальные токены: холодный near-black + скупой коралл + Onest, белый CTA).
**Оплата:** **Polar.sh** (по твоему запросу, не Lemon Squeezy из брифа).

> ⚠️ Лендинг НЕ деплоится на quip.ink, пока ты не проверишь auth+логику — как ты и просил.

---

## 1. Что сделано (по фазам, с DoD)

### D1 — Дизайн-направление (ЗАМОК)
- Изучил `design-md/` двумя fan-out агентами (AI-video кластер: runway/eleven/minimax/replicate/
  lovable; dev-craft кластер: linear/vercel/superhuman/cursor/raycast/framer/stripe) + **вытащил
  реальные computed-токены quip.ink** (browse): фон холодный near-black, заголовок **Onest 700**
  `-2.28px`, текст `#7E8AA4`, белый CTA — НЕ тёплый, как казалось по скрину.
- Собрал **3 живых концепта** (реальный HTML+шрифты, не AI-картинки), показал тебе → выбрал.
  С учётом находки «quip холодный» → строю под реальные токены quip.ink.
- **DESIGN.md** (канон: токены color/type/space/radii/motion, примитивы, анти-слоп, SEO/a11y) +
  **globals.css @theme** (холодная surface-ladder, hairlines, семантическая type-шкала, focus-ring,
  scroll-reveal) с сохранением старых util-имён → редактор переехал на новую тему без поломок.
- Шрифты: **Onest** (дисплей+текст, как quip) + IBM Plex Mono (тайм-коды/цифры/цены).

### D2 — Лендинг
- **Route-groups:** `(marketing)` владеет `/`, `(app)` держит `/dashboard`+`/edit` (переехали с `/`),
  `(auth)` держит `/login`+`/signup`. Editor back-links → `/dashboard?job=`.
- **Примитивы** (`components/ui`): Button (`buttonVariants` для `<button>`/`<Link>`), Container,
  Section, Eyebrow, Reveal (a11y scroll-reveal, видим без JS), Logo, Card, Input. Только токены,
  dependency-free `cn()`.
- **8 секций** (`components/marketing`): Hero (реальный продукт-мокап + reasoning-карточка),
  HowItWorks, WhyQuip (объяснимость = наш wedge), Craft, Comparison (vs «комбайны»), Pricing,
  Faq, FinalCta + MarketingNav (нативное mobile-меню) + Footer.
- **SEO:** generateMetadata + canonical, JSON-LD (Organization+SoftwareApplication+FAQPage,
  `<`-escaped), `app/sitemap.ts`, `app/robots.ts` (закрыл app-роуты), **OG-картинка**
  (`app/opengraph-image.tsx`, локальный TTF, без сети), семантический HTML, RSC по умолчанию,
  next/font (CLS≈0), prefers-reduced-motion.
- DoD: `next build` зелёный, 0 console-ошибок, desktop+mobile проверены.

### A1 — Авторизация (Supabase, dual-mode)
- `@supabase/ssr` (запиннен, lockfile закоммичен): `lib/supabase/{config,client,server}`.
- **`proxy.ts`** (Next 16 переименовал middleware→proxy): рефреш сессии + ОПТИМИСТИЧНЫЙ редирект;
  no-op без Supabase. Удалил `middleware.ts` + демо `/api/auth`.
- **Гейт** в `(app)/layout.tsx` через `getUser()` (валидирует JWT, НЕ getSession); открыт в dev.
- UI: `(auth)` layout, login+signup (server, dual-mode), AuthForm (email/пароль + email-confirm
  состояние), AuthDevNotice (dev-фолбэк), SignOutButton, auth/callback (exchange code).
- **Dual-mode:** без ключей Supabase приложение РАБОТАЕТ открыто (твоё локальное тестирование);
  впишешь ключи → auth активируется сам (формы вместо dev-notice, гейт включается).

### D3 — Дашборд
- **AppHeader** (Logo→/dashboard, Free-plan чип, аккаунт-меню: email при Supabase + sign-out).
- **UsageMeter** (план + квота видео/минут, зеркалит billing.py Free; props → live при Supabase).
- **RecentProjects** (история на localStorage через `useSyncExternalStore` — без бэкенда, deep-link
  на `?job=`; апгрейд на серверный список позже). Дашборд = студия (создание + usage/recent сайдбар).
- Редактор `/edit` уже интегрирован как gated `(app)`-роут, перекрашен новой темой.

### P1 — Прайсинг + Polar.sh + гейт квоты (dual-mode)
- **`/pricing`** (отдельная страница) + общий `PricingCards`. CTA → Polar checkout (`lib/polar.ts`,
  env-ссылки) с фолбэком на `/signup`.
- **Worker (TDD):** `app/polar.py` — проверка подписи **Standard Webhooks** (stdlib HMAC + окно
  времени), **пиннута к ОФИЦИАЛЬНОМУ тест-вектору Standard Webhooks** → спека-корректна без живого
  вызова; product→план; парс payload (external_id/metadata). `POST /webhooks/polar`. Гейт квоты в
  create_job/upload (`check_quota`→402); **инертен без `BILLING_ENABLED` → пайплайн не трогается**.
  `db`: profiles + set/get_user_plan. config: polar_*/supabase_* (опц.).
- **18 новых тестов** (вектор подписи, маппинг, парс, вебхук endpoint, гейт 402/202/no-op).

### POLISH — Lighthouse / a11y
- Прогон chrome-devtools MCP (prod-build). Было a11y 88 → починил: белый primary-CTA (coral-white
  ~3.1:1 фейлил AA → near-white/тёмный текст ~14:1, ЗАОДНО совпало с белым CTA quip.ink), faint
  контраст, dl→div семантика, badge dark-on-coral.
- **Результат (лендинг, prod): Accessibility 100, Best Practices 100, SEO 100, Agentic 100
  (0 фейлов); Performance LCP 173ms, CLS 0.00.** Превышает цель 90+.

---

## 2. Что использовано (референсы / скиллы / OSS)

| Что | Источник |
|---|---|
| Дизайн-методология, анти-слоп, токены | скилл `design-consultation` (методология; gstack-housekeeping пропущен) |
| Референс-синтез | fan-out агенты по `design-md/` (2 кластера) |
| North-star токены | `quip.ink` (browse: computed CSS) |
| Концепты | реальный HTML + browse-скрины (вместо AI-картинок — выше точность, 0 слопа) |
| Auth | **@supabase/ssr** (OSS, getAll/setAll, getUser-гейт) — скилл `supabase` security-чеклист |
| Оплата | **Polar.sh** + Standard Webhooks (официальный тест-вектор) |
| Шрифты | Onest + IBM Plex Mono (next/font); OG — локальный Montserrat.ttf |
| a11y/perf | chrome-devtools MCP `lighthouse_audit` + `performance_start_trace` |
| Next 16 | прочитал `node_modules/next/dist/docs` (middleware→proxy, fonts, metadata/OG) |

Next 16 грабли учтены: **middleware переименован в proxy**; `cookies()` async; OG через `next/og`
ImageResponse (satori требует `display:flex` на multi-child div).

---

## 3. Как запускать

```powershell
$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
Set-Location "C:\Users\user\Desktop\ClipClow"; just check          # гейт (409 тестов)

# Web (dev): pnpm --filter web dev   → :3000   (auth открыт в dev, мок-воркер /api/mock)
# Web (prod-проверка): pnpm --filter web build; pnpm --filter web start
# Worker:  cd services/worker; uv run uvicorn app.main:app --port 8000
```
Лендинг — `/`. Приложение — `/dashboard` (в dev открыто). Прайсинг — `/pricing`. Вход — `/login`.
⚠️ После правок воркера — перезапусти воркер (uvicorn без --reload).

---

## 4. Что ТЫ вписываешь руками (секреты/деплой — не агент)

### 4.1 Supabase (auth + данные + расход)
1. Создай Pro-проект → SQL Editor → выполни `services/worker/migrations/0001_init_billing.sql`.
2. Ключи (Project Settings → API):
   - `NEXT_PUBLIC_SUPABASE_URL` + `NEXT_PUBLIC_SUPABASE_ANON_KEY` → `apps/web/.env.local`.
   - `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` → воркер env (🔴 НИКОГДА в `NEXT_PUBLIC_*`).
3. Готово: вписал ключи → auth активируется сам (формы вместо dev-notice, гейт включается).

### 4.2 Polar.sh (оплата)
1. Создай 2 продукта (Starter $12, Pro $29) → возьми checkout-ссылки + product_id.
2. Frontend env: `NEXT_PUBLIC_POLAR_CHECKOUT_STARTER` / `_PRO` (ссылки).
3. Worker env: `POLAR_WEBHOOK_SECRET` (whsec_...), `POLAR_PRODUCT_STARTER` / `_PRO` (product_id).
4. Вебхук в Polar → `https://<worker>/webhooks/polar` (события subscription.*).
5. Включи гейт: `BILLING_ENABLED=true` (+ см. 4.3 про JWT).
6. В checkout передавай `customer_external_id = supabase user.id` → вебхук свяжет оплату с юзером.

### 4.3 🔴 Безопасность гейта квоты (обязательно перед продом)
Сейчас гейт берёт юзера из заголовка `X-User-Id` — **это плейсхолдер, он спуфится**. Перед включением
`BILLING_ENABLED` на проде воркер ДОЛЖЕН валидировать Supabase-JWT (Authorization: Bearer) и брать
user_id оттуда. Фронт должен слать токен сессии воркеру. (Сейчас инертно по умолчанию → безопасно.)

### 4.4 Деплой / домен
- Vercel (фронт) + Modal (воркер, torch/MediaPipe ~1ГБ+). `NEXT_PUBLIC_SITE_URL=https://quip.ink`,
  `NEXT_PUBLIC_WORKER_URL=https://<worker>`. quip.ink держит waitlist, пока не проверишь всё.

---

## 5. Что НЕ доделано / follow-up (и почему)

- **Живой прувинг auth/оплаты** — нет секретов Supabase/Polar (подписка не оплачена). Всё построено
  dual-mode + TDD на pure-логике; активируется при подключении.
- **Frontend→worker JWT** (§4.3) — гейт квоты безопасен только с валидацией Supabase-JWT.
- **Запись usage в пайплайне** — `db.record_usage` есть, но не вызывается в `run.py` (нужен user_id
  в воркере). Подключить после auth.
- **i18n ядра** — лендинг/auth/дашборд-оболочка на АНГЛИЙСКОМ; внутренности редактора и SourceForm/
  JobProgress/ClipGrid остались РУССКИМИ (ядро, «не ломать»). English-ify — отдельная задача.
- **Серверный список проектов** — сейчас localStorage; нужен worker `GET /jobs` (list) + user-scope.
- **/terms, /privacy** — честные плейсхолдеры (не 404); реальный юр-текст — за тобой.
- **design-shotgun / imagegen / brandkit** скиллы — заменил живыми HTML-концептами + реальным
  Lighthouse (выше точность). taste/anti-slop принципы применены в коде.

---

## 6. Какие флоу работают end-to-end

✅ **Лендинг** `/` — премиум, Lighthouse 100×4, OG, SEO, мобайл; CTA → `/signup`.
✅ **Регистрация/вход** `/signup` `/login` — рендерятся dual-mode; с Supabase = реальный вход+гейт.
✅ **Дашборд** `/dashboard` — создание клипов (реальный пайплайн воркера), usage, recent, редактор.
✅ **Нарезка → редактор** — ядро работает как раньше, перекрашено в новую тему, гейтнуто (app).
✅ **Прайсинг** `/pricing` — план-карты из billing.py; CTA → Polar checkout (при ссылках) / `/signup`.
✅ **Оплата → план** — вебхук Polar (подпись спека-корректна) → `profiles.plan` (при секретах).
✅ **Квота** — `check_quota`→402 в create_job (при `BILLING_ENABLED`).

**Воронка лендинг→регистрация→первый клип→апгрейд собрана; «провод» к Supabase/Polar — твои ключи
по §4.** Дизайн/SEO/перф — мирового уровня (100×4 + LCP 173ms).
