# FE-A — Marketing/Landing/SEO — отчёт агента

## Сводка
- Файлов проверено: 24 (page/layout marketing + 17 marketing-компонентов + terms/privacy + opengraph-image + robots + sitemap + app/layout + lib/site + lib/faq + lib/jsonld)
- Багов найдено: 3 (crit 0 / high 1 / med 1 / low 1)
- Багов починено: 1 (sitemap SEO — high)
- Тесты добавлены: 0 (на этих файлах нет unit-тестов; гейт = tsc + eslint)
- Прогон гейта: `pnpm --filter web exec tsc --noEmit` → exit 0; `pnpm --filter web lint` → exit 0 (оба зелёные ПОСЛЕ фикса)

## Баги

### [HIGH] Sitemap содержит noindex-URL и пропускает индексируемый /pricing — app/sitemap.ts:6-10
**Симптом:** `sitemap.ts` перечислял `/`, `/signup`, `/login`. Но `/signup` и `/login`
оба объявлены `robots: { index: false }` (`app/(auth)/login/page.tsx:7`,
`app/(auth)/signup/page.tsx:7`). При этом `/pricing` — реальная индексируемая страница
с `alternates: { canonical: "/pricing" }` (`app/(marketing)/pricing/page.tsx:13`) — в
sitemap ОТСУТСТВОВАЛА.
**Корень:** sitemap должен содержать ТОЛЬКО канонические индексируемые URL. Перечисление
noindex-страниц = противоречивый сигнал краулеру (sitemap зовёт индексировать, мета-тег
запрещает); пропуск индексируемой страницы = потеря SEO-веса главной платной страницы.
**Фикс:** убрал `/login` + `/signup` (noindex), добавил `/pricing` (priority 0.8,
changeFrequency monthly). `/terms` и `/privacy` тоже noindex (`robots:{index:false}`) →
их в sitemap нет и быть не должно (консистентно). Коммент в файле объясняет правило.
**Тест:** нет unit-теста; верифицировано чтением мета каждой целевой страницы +
tsc/eslint зелёные.

### [MED] Якорные ссылки в подвале мертвы вне главной — components/marketing/Footer.tsx:9-12
**Симптом:** колонка «Product» в Footer ссылается на `#how-it-works`, `#why`,
`#pricing`, `#faq`. Footer рендерится во ВСЕХ marketing-страницах (`/terms`, `/privacy`,
а также `/pricing`). На этих страницах целевых секций нет → клик по якорю ничего не
делает (на /pricing #pricing/#faq частично существуют через секции, но #how-it-works/#why
отсутствуют).
**Корень:** общий Footer с якорями, валидными только на `/`.
**Фикс:** НЕ ЧИНИЛ. Это распространённый и приемлемый паттерн (якоря — навигация по
лендингу); «правильный» фикс — заменить на `/#how-it-works` (абсолютный якорь на главную),
но это меняет поведение навигации на самой главной (лишний переход роутера). Требует
продуктового решения. Документирую как кандидат, не правлю вслепую.
**Тест:** —

### [LOW] ProofStrip: порядок dd→dt инвертирован в <dl> — components/marketing/ProofStrip.tsx:24-32
**Симптом:** внутри `<dl>` каждый item-`<div>` содержит `<dd>` (число) ПЕРЕД `<dt>`
(подпись). По HTML-спеке термин `<dt>` должен предшествовать описанию `<dd>`.
**Корень:** визуальный порядок (большое число сверху) реализован прямым порядком DOM.
**Фикс:** НЕ ЧИНИЛ. Низкая severity (скринридеры всё равно озвучивают оба; визуал
корректен). Корректный фикс требует swap DOM + `flex-col-reverse`/перестройку мобильного
ряда → реальный риск визуальной регрессии ради семантического нита. Per discipline
(«не выдумывать дизайн-ниты, не рисковать лейаутом») — оставил, задокументировал.
**Тест:** —

## Что проверено и ЧИСТО (без багов)
- **Внутренние ссылки.** Nav (`MarketingNav.tsx`) и Footer ведут на `#how-it-works`,
  `#why`, `#pricing`, `#faq` — все 4 ID существуют (HowItWorks/WhyQuip/Pricing/Faq
  Section id). `/login`, `/signup`, `/pricing`, `/terms`, `/privacy`, `/dashboard` —
  все маршруты резолвятся (проверено файловой структурой). Нет мёртвых `#`/dead hrefs.
- **Hydration.** QuipStudio waveform = `useMemo` чистая функция индекса (коммент явно это
  отмечает); нет `Date.now()`/`Math.random()` в render. Footer `new Date().getFullYear()`
  в RSC (рендерится один раз на сервере, без client-расхождения).
- **key props.** Все `.map()` имеют стабильные/уникальные key (Footer по href, QuipStudio
  по `${sampleIdx}-${i}`, FAQ по q, и т.д.). Дублей нет.
- **Scroll-reveal без JS.** `Reveal` тогглит `data-reveal`; CSS прячет ТОЛЬКО под `.js`
  (globals.css:154 `.js [data-reveal]`), а `.js` ставится скриптом в `app/layout.tsx:67`
  до paint → no-JS/краулеры видят весь контент. Корректно.
- **OG image (satori).** `app/opengraph-image.tsx`: КАЖДЫЙ multi-child `<div>` имеет
  `display:flex` (logo-ряд, headline, eyebrow) — ограничение satori соблюдено. Шрифт
  читается локально (`public/libass/fonts/Montserrat.ttf`, без сетевого фетча),
  `runtime="nodejs"`. (Микро-нюанс: контент юзает fontWeight 800, шрифт зарегистрирован
  weight 700 → satori берёт ближайший, рендерится без ошибки — НЕ баг.)
- **JSON-LD.** `lib/jsonld.ts` @graph: Organization + SoftwareApplication(offers из PLANS)
  + FAQPage(из FAQ). Форма валидна; offers читают `PLANS.name/price` (есть в lib/plans.ts);
  FAQ Question/acceptedAnswer корректны; logo `/icon.png` существует (public/icon.png).
  Инъекция-safe: `.replace(/</g,"\\u003c")`.
- **robots.ts.** Disallow `/dashboard`, `/edit/`, `/api/` — все приватные, маршрут
  `/edit/[jobId]/[clipId]` реален. sitemap-ссылка и host корректны (env-driven URL).
- **Метадата.** Root layout title template/OG/twitter/metadataBase — валидны. Terms/Privacy
  noindex. Pricing/Home canonical. Hreflang/alternates консистентны.
- **a11y.** Все интерактивные элементы маркированы: MobileMenu (aria-haspopup/expanded/label,
  Escape+outside-dismiss), QuipStudio timeline-кнопки (aria-label), ClipMockup (role="img"+
  aria-label), декоративные блобы `aria-hidden`, иконки `aria-hidden`. Все `<Image>` имеют
  alt (декоративные — `alt=""`). Heading-порядок: h1 (Hero) → h2 (секции) → h3 (карточки).
- **Хардкод localhost.** Не найдено; URL только через `siteConfig.url` (env `NEXT_PUBLIC_SITE_URL`
  с фолбэком quip.ink).
- **Unescaped entities.** Апострофы/кавычки экранированы (`&rsquo;`, `&mdash;`) — eslint
  react/no-unescaped-entities зелёный.

## Передать оркестратору (чужие/общие файлы)
- **components/ui/** и **globals.css** — без замечаний по моему домену (Reveal/Button/
  Container/Section используются корректно; `.js`-гейтинг reveal в globals.css правильный).
- **Footer dead-anchor** (см. MED-баг) — продуктовое решение, нужен апрув на смену
  `#anchor` → `/#anchor`. Файл мой, но фикс поведенческий — оставляю на твоё усмотрение.
- **(auth)/login + (auth)/signup** (домен FE-B): оба `robots:{index:false}` — это
  правильно, я лишь привёл sitemap в соответствие. Информирую для консистентности.
- **lib/plans.ts** (домен FE-E): мой jsonld зависит от `PLANS[].name/price` — контракт цел,
  если FE-E будет менять форму PLANS, пусть учтёт `lib/jsonld.ts:25-30`.

## Не успел / открыто
- Ничего не заблокировано. Визуальный прогон в браузере (Playwright/Lighthouse) не делал —
  по бюджету ограничился статическим анализом + tsc/eslint; предыдущие сессии уже снимали
  Lighthouse 100×4 на лендинге/прайсинге.
