# FE-B — отчёт агента (Auth + App shell + Dashboard)

## Сводка
- Файлов проверено: 16 (owned) + 2 read-only смежных (`proxy.ts`, `lib/api.ts`)
- Багов найдено: 3 (crit 0 / high 1 / med 2 / low 0) + 1 документированный риск
- Багов починено: 3
- Тесты добавлены: 0 (домен без unit-харнесса; верификация = tsc + lint, ниже)
- Прогон: `pnpm --filter web exec tsc --noEmit` → **TSC_OK**; `pnpm --filter web lint` → **чисто (0 ошибок)**

## Баги

### [HIGH] Callback тихо глотает ошибку обмена кода → редирект-петля — `app/auth/callback/route.ts:15`
**Симптом:** По истёкшей/повторно использованной magic-link/OAuth-ссылке (PKCE) пользователь
попадает на callback → код не обменивается на сессию → callback ВСЁ РАВНО редиректит на `next`
(`/dashboard`) → серверный гейт `(app)/layout.tsx` через `getUser()` видит `user=null` →
redirect `/login`. Итог: login → callback → dashboard → login, БЕЗ объяснения. Классический
silent-failure (нарушение правила 8: тихий фолбэк).
**Корень:** `await supabase.auth.exchangeCodeForSession(code)` игнорировал возвращаемый
`{ error }`. (`exchangeCodeForSession` возвращает `AuthTokenResponse` с `{ data, error }` —
подтверждено в `@supabase/auth-js@2.108.1/GoTrueClient.d.ts:808`.)
**Фикс:** Захватываю `error`; при ошибке — редирект на `/login?next=…&error=<понятная причина>`
вместо защищённого маршрута. Login-страница теперь читает `?error` и показывает `role="alert"`
плашку. Open-redirect невозможен: `next` уже валидируется (`startsWith("/") && !"//"`), `error`
— просто текст.
**Тест:** tsc/lint зелёные; ручная трассировка пути (истёкшая ссылка → видимая причина на /login,
петли нет).

### [MED] SignOut навсегда дизейблит кнопку при сетевом сбое — `components/auth/SignOutButton.tsx:13`
**Симптом:** `setBusy(true)` → `await ...signOut()`; если `signOut()` бросает (сеть/таймаут),
`router.replace` не выполняется, `busy` НИКОГДА не сбрасывается → кнопка «Sign out» залипает
disabled до перезагрузки страницы.
**Корень:** Нет `try/finally` вокруг async-логики.
**Фикс:** Обернул в `try/catch`; при ошибке `setBusy(false)` → кнопка снова кликабельна для
ретрая. (Успешный путь не трогает `busy` — навигация всё равно размонтирует компонент.)
**Тест:** tsc/lint зелёные.

### [MED] Ошибка callback не имела куда отобразиться — `app/(auth)/login/page.tsx:14`
**Симптом:** (Следствие фикса HIGH-бага) login-страница не умела показать причину неудачного
входа — параметр `?error` игнорировался.
**Корень:** `searchParams` типизировался только как `{ next? }`, плашки ошибки не было.
**Фикс:** Добавил `error?` в тип, читаю `sp.error`, рендерю `role="alert"` плашку (`text-bad`,
тот же стиль, что в `AuthForm`). Минимально и в стиле страницы.
**Тест:** tsc/lint зелёные.

## Проверено и ПРИЗНАНО КОРРЕКТНЫМ (не баги)
- **`lib/recent.ts` `useSyncExternalStore`-стабильность:** `getRecentServerSnapshot` возвращает
  один и тот же `EMPTY_SNAPSHOT`-реф (стабилен для SSR). `getRecentSnapshot` лениво кэширует
  `snapshot`, и `emit()` вызывает `refresh()` ПЕРЕД нотификацией листенеров → после уведомления
  снапшот всегда свежий, между рендерами — стабильный реф. Бесконечного ре-рендера/SSR-варна нет.
  Все мутации (`addRecentProject`/`removeRecentProject`) и `readStorage` гардятся
  `typeof window === "undefined"` / try-catch на повреждённый localStorage. Корректно.
- **Auth-гейт `(app)/layout.tsx`:** dual-mode корректен — открыт когда `!isSupabaseConfigured`
  (dev пропускается), при наличии ключей валидирует JWT через `getUser()` (не `getSession()`),
  `await` на месте, `redirect("/login")` при `user=null`. Цель `/login` существует.
- **`lib/supabase/server.ts`:** `await cookies()` (Next 16 async) на месте; `setAll` try-catch —
  легитимный паттерн @supabase/ssr (Server Component не пишет куки; сессию рефрешит proxy), НЕ
  тихий фолбэк.
- **`AppHeader`:** `getUser()` клиентом гардится `isSupabaseConfigured`, `.catch(()=>setEmail(null))`.
  Light-dismiss меню (pointerdown/Escape) с корректной очисткой листенеров. ОК.
- **`UsageMeter`/`UsagePill`:** `getUsage()` бросает при недоступности воркера/auth → оба
  откатываются на free-дефолт / пустое состояние (dual-mode). `cancelled`-флаг гасит set-state
  после анмаунта. ОК.

## Передать оркестратору (чужие/общие файлы)
- **[ОТКРЫТО, не баг — продуктовое поведение] `components/auth/AuthForm.tsx:112-117`
  (мой домен, но требует решения):** при password-`signup`, когда Supabase возвращает
  `data.session === null` (требуется подтверждение email), код делает `setStep("code")` и
  ждёт ввода 6-значного OTP. Но `signUp({emailRedirectTo})` по умолчанию шлёт **ссылку-
  подтверждение**, а не числовой код — `verifyOtp({type:"email"})` сработает ТОЛЬКО если в
  Supabase-проекте email-шаблон отдаёт `{{ .Token }}` (OTP), а не `{{ .ConfirmationURL }}`.
  Зависит от настройки проекта фаундера. НЕ чинил (правило 9: не угадывать без проекта/ключей).
  Рекомендация оркестратору: задокументировать требование «Email OTP в шаблонах Supabase» в
  `docs/SUPABASE_SETUP.md` ИЛИ показывать на этом шаге «проверьте письмо со ссылкой».
- **`proxy.ts` (read-only, не трогал):** корректен — гейтит только protected+auth-маршруты,
  `getUser()` (не getSession), dual-mode `!isSupabaseConfigured → next()`. Замечаний нет.
- **`lib/api.ts` (FE-D, read-only):** `authHeaders()` использует `getSession().access_token`
  для Bearer воркеру — норм для client fetch; тихий `catch → {}` это dev-фолбэк (auth выкл).
  Замечаний по моему домену нет.

## Не успел / открыто
- Живой e2e auth-флоу не прогонялся (нет Supabase-ключей в окружении — dual-mode dev). Фиксы
  верифицированы статически (tsc/lint) + трассировкой путей. Реальная проверка callback-петли
  и password-signup OTP — после того как фаундер впишет ключи.
