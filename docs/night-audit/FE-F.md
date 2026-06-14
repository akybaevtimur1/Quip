# FE-F — отчёт агента (shared UI primitives + auth proxy)

## Сводка
- Файлов проверено: 15 (13 ui/* кроме CheckoutCta, `proxy.ts`, `lib/cn.ts`)
- Багов найдено: 3 (crit 0 / high 1 / med 1 / low 1)
- Багов починено: 2 (1 high + 1 med). 1 low — задокументирован, не чинил (косметика, держу публичный API/no-op).
- Тесты добавлены: 0 (нет тестового харнесса на фронт-примитивах; нет pure-логики для TDD — изменения проверены статически).
- Прогон: `pnpm --filter web exec tsc --noEmit` → **TSC_OK**; `pnpm --filter web lint` → **LINT_OK** (оба зелёные до и после правок).

## Баги

### [HIGH] proxy.ts роняет ротированные session-куки на редиректах — apps/web/proxy.ts:45-55
**Симптом:** при auth-редиректах (`!user`→`/login`, `user`→`/dashboard`) использовался голый
`NextResponse.redirect(url)`, который НЕ несёт `Set-Cookie`, записанные `setAll` в рабочий `response`.
**Корень:** `supabase.auth.getUser()` может ротировать access/refresh-токен и пишет новые куки в
`response` через `setAll`. Эти куки теряются на любом редиректе → следующий запрос снова рефрешит
(churn), а после истечения старого токена — ложный auth-bounce / редирект-петля у залогиненного юзера.
Это нарушение канонического паттерна Supabase-SSR + Next-middleware (куки обязаны копироваться на
редирект-ответ).
**Фикс:** добавлен `redirectWithCookies(url)` — создаёт `NextResponse.redirect` и копирует на него
все `response.cookies.getAll()`. Оба редирект-бранча теперь идут через него. Публичный контракт
(matcher/экспорт `proxy`/dual-mode) не тронут. tsc/lint зелёные.
**Тест:** нет фронт-харнесса; проверено tsc (тип `ResponseCookie` совместим с `cookies.set`) + ревью
против Supabase-SSR паттерна.

### [MED] Select: dead `peer-focus:` (шеврон не реагирует на фокус) — apps/web/components/ui/Select.tsx:16,31
**Симптом:** шеврон должен темнеть (`text-ink`) при фокусе `<select>`, но не темнел никогда.
**Корень:** утилита `peer-focus:text-ink` на шевроне требует, чтобы предыдущий sibling был помечен
классом `peer`. У `<select>` класса `peer` не было → модификатор `peer-focus:` мёртвый (no-op).
**Фикс:** добавил `peer` в начало className `<select>`. Порядок DOM уже верный (select → chevron).
Чисто косметика фокус-аффорданса; клавиатурная навигация/ринг (глобальный `:focus-visible`) и так
работали через нативный `<select>`.
**Тест:** статическая проверка (Tailwind `peer-*` требует sibling `.peer`); tsc/lint зелёные.

### [LOW] role="switch" без явного aria-checked — apps/web/components/ui/Switch.tsx:27 (НЕ ЧИНИЛ)
**Симптом:** потенциальное беспокойство, что состояние тумблера не озвучивается.
**Корень/вывод:** это НЕ баг. `role="switch"` навешан на нативный `<input type="checkbox">`; современные
браузеры (Chrome/Firefox/Safari) маппят нативный `checked` → `aria-checked` в дерево доступности
автоматически. Состояние + клавиатура (Space/Tab) работают нативно. Добавлять managed `aria-checked`
потребовало бы контролируемого стейта и расширения публичного API — не оправдано.
**Фикс:** не чинил (ложная тревога; держу API стабильным).

## Проверенное и признанное КОРРЕКТНЫМ (без правок)
- **cn.ts** — простой join+filter; в проекте классы намеренно не конфликтуют (нет twMerge). Все
  consumer-вызовы кладут `className` ПОСЛЕДНИМ аргументом → override работает. Ок.
- **Checkbox / Switch** a11y — реальный нативный `<input>` ведёт стейт; `htmlFor`/`id` (useId)
  ассоциируют label; глобальный `:focus-visible` даёт ринг через `peer-focus-visible`. Ок.
- **IconButton** — `aria-label` обязателен в типе (required prop) → нет безымянных icon-кнопок. Ок.
- **Button** — `disabled ?? loading`, `aria-busy` на loading, `focus-visible:outline-none` +
  глобальный ринг; `disabled` исключён из spread (нет дубля). accent disabled = нейтральная
  поверхность (анти-muddy-coral, по DESIGN.md). Ок.
- **Input/Label** — не авто-связаны, НО все consumer'ы (AuthForm) вручную дают `Label htmlFor` +
  `Input id`. Ассоциация есть. Ок.
- **Reveal** — контент скрыт ТОЛЬКО при `.js` + motion-allowed (CSS `globals.css:154`); no-JS/
  crawlers/reduced-motion всегда видят контент. IO одноразовый, `io.disconnect()` в cleanup. Ок.
- **NavProgress** — все таймеры/интервалы/rAF чистятся (`stopCreep`, cleanup-возвраты, финальный
  `useEffect(() => stopCreep, [])`); click-listener снимается в cleanup. Утечки нет. Ок.
- **forwardRef** — НИ ОДИН consumer не передаёт `ref` в Button/Input/Select/Checkbox/Switch
  (consumer'ы используют сырые `<input ref>` напрямую, напр. SourceForm). Отсутствие forwardRef
  не является живым багом → API не расширял.
- **proxy matcher** — корректно исключает `_next/static`, `_next/image`, `favicon.ico` и
  `*.png/jpg/jpeg/svg/ico/txt/xml/webp` (покрывает icon.png/apple-icon.png/robots.txt/sitemap.xml).
  `/opengraph-image` matcher НЕ исключает, но proxy для него — дешёвый `NextResponse.next()`
  (не protected, не auth-page) → безвреден. **Dual-mode корректен:** при `!isSupabaseConfigured`
  и proxy, и `(app)/layout.tsx` — no-op → приложение открыто, без краша и локаута.
- **auth callback** (`app/auth/callback/route.ts`, не мой, но смежный) — `next` валидируется
  против open-redirect (`startsWith("/") && !startsWith("//")`). proxy `next=path` всегда внутренний
  pathname. Ок.

## Передать оркестратору (чужие/общие файлы)
- **globals.css/тема:** проблем НЕ найдено. `:focus-visible` ринг, scroll-reveal-гейт (`.js` +
  reduced-motion), reduced-motion-блок — всё корректно. Замечаний к теме нет.
- Информативно (не баг): proxy-matcher гоняет proxy и на `/api/*` и `/opengraph-image` — это дешёвые
  passthrough'ы (proxy короткозамыкается на не-protected/не-auth). Если оркестратор захочет
  микро-оптимизацию, можно дописать `api|opengraph-image` в negative-lookahead, но это вне моего
  ownership на правку логики matcher'а без сильной причины.

## Не успел / открыто
- Всё в рамках ownership проверено. Открытых пунктов нет.
- 2 правки готовы к коммиту оркестратором: `proxy.ts` (cookie-preserving redirects),
  `Select.tsx` (`peer` класс). Обе под зелёными tsc+lint.
