# Auth & Analytics Layer — Design Spec

> Дата: 2026-06-13  
> Статус: утверждён  
> Контекст: MVP-редактор готов (editor-v3). Добавляем слой аутентификации поверх
> существующего ядра без переписывания пайплайна.

---

## 1. Цель

Добавить полноценные пользовательские аккаунты (email/пароль + Google OAuth) и
базовую аналитику (кто зарегистрировался, сколько джобов/$ потратил каждый юзер).

**Не в scope:** платёжный шлюз, лимиты на джобы, email-уведомления, роли кроме admin.

---

## 2. Архитектура

```
╔══════════════════════════════════════════════════════════╗
║                VERCEL (фронтенд)                         ║
║                                                          ║
║  ┌──────────────────────────────────────────────────┐    ║
║  │  @supabase/ssr  (Next.js App Router)             │    ║
║  │  • email/пароль + Google OAuth                   │    ║
║  │  • middleware.ts — Supabase сессия на всех путях │    ║
║  │  • access_token → заголовок к воркеру            │    ║
║  └──────────────────┬───────────────────────────────┘    ║
║                     │ Authorization: Bearer <JWT>         ║
║  ┌──────────────────────────────────────────────────┐    ║
║  │  /admin  (server component)                       │    ║
║  │  • список юзеров из Supabase (service role key)  │    ║
║  │  • статистика джобов из воркера GET /admin/stats │    ║
║  └──────────────────────────────────────────────────┘    ║
╚══════════════════════════╦═══════════════════════════════╝
                           ║ HTTPS через ngrok
           ╔═══════════════▼════════════════╗
           ║  ЛОКАЛЬНЫЙ ВОРКЕР  :8000        ║
           ║                                 ║
           ║  app/auth.py                    ║
           ║  • PyJWT verify HS256           ║
           ║  • extract sub → user_id        ║
           ║  • Depends(get_current_user)    ║
           ║    на всех /jobs/* эндпоинтах   ║
           ║                                 ║
           ║  SQLite jobs:                   ║
           ║   + user_id TEXT колонка        ║
           ║   + SELECT WHERE user_id = ?    ║
           ║                                 ║
           ║  GET /admin/stats               ║
           ║  (WORKER_ADMIN_KEY header)      ║
           ╚═══════════════╦════════════════╝
                           ║
               ╔═══════════▼═══════════╗
               ║   Supabase (облако)   ║
               ║   Auth + Postgres     ║
               ║   users / sessions /  ║
               ║   accounts            ║
               ║   Studio = дашборд   ║
               ╚═══════════════════════╝
```

---

## 3. Supabase проект

### Настройка (один раз, через UI)
1. Создать проект на supabase.com (free tier)
2. **Auth → Providers**: включить Email (с подтверждением или без) + Google
3. **Auth → URL Configuration**: добавить Vercel URL в `Redirect URLs`
4. Забрать из Settings → API:
   - `SUPABASE_URL` (публичный)
   - `SUPABASE_ANON_KEY` (публичный, JWT подписан anon-ролью)
   - `SUPABASE_SERVICE_ROLE_KEY` (приватный, только сервер)
   - `JWT_SECRET` (для воркера, верификация токенов)

### Схема в Supabase (Auth.js создаёт автоматически)
```
auth.users — встроенная таблица Supabase
  id         UUID (= user_id везде)
  email      TEXT
  created_at TIMESTAMPTZ
  ...
```
Дополнительных таблиц не нужно — джобы живут в локальном SQLite воркера.

---

## 4. Frontend: Next.js изменения

### 4.1 Установка
```bash
pnpm --filter web add @supabase/ssr @supabase/supabase-js
```

### 4.2 Новые файлы
```
apps/web/
  lib/supabase/
    client.ts        ← createBrowserClient (браузер)
    server.ts        ← createServerClient + cookie-хелпер (SSR)
  app/
    api/auth/callback/
      route.ts       ← OAuth callback (Google redirect сюда)
    admin/
      page.tsx       ← дашборд аналитики (server component)
```

### 4.3 Изменённые файлы
```
middleware.ts        ← заменить passcode-гейт на Supabase сессию
app/login/page.tsx   ← email/пароль + кнопка Google
lib/api.ts           ← добавить getAuthHeaders() во все fetch-вызовы к воркеру
```

### 4.4 Логика middleware (замена passcode)
```typescript
// Было: проверка cookie demo_auth === PASSCODE
// Стало: Supabase createServerClient → getUser() → redirect /login если нет
//
// Публичные пути без проверки:
const PUBLIC = ["/login", "/api/auth/callback", "/api/auth"]
```

### 4.5 Добавление auth-заголовка в API-вызовы
```typescript
// lib/supabase/client.ts — браузерный singleton
export const supabase = createBrowserClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
)

// lib/api.ts — хелпер
async function getAuthHeaders(): Promise<Record<string, string>> {
  const { data: { session } } = await supabase.auth.getSession()
  if (!session) return {}
  return { Authorization: `Bearer ${session.access_token}` }
}

// Каждый fetch к воркеру добавляет заголовок:
const res = await fetch(`${BASE}/jobs`, {
  method: "POST",
  headers: { "Content-Type": "application/json", ...await getAuthHeaders() },
  body: JSON.stringify(input),
})
```

### 4.6 Login page
```
/login:
  Форма email + пароль → supabase.auth.signInWithPassword()
  Ссылка «Регистрация» → supabase.auth.signUp()
  Кнопка «Войти через Google» → supabase.auth.signInWithOAuth({ provider: 'google' })
  После успеха → router.replace(from ?? '/')
```

### 4.7 Admin page (/admin)
```typescript
// Server component, защита по email:
const session = await getServerSession()
if (session.user.email !== process.env.ADMIN_EMAIL) notFound()

// Данные из двух источников:
// 1. Supabase service role → список юзеров
// auth.admin.listUsers() требует service role key (не anon)
const { data: { users } } = await supabaseAdmin.auth.admin.listUsers()

// 2. Воркер → статистика джобов
const stats = await fetch(`${WORKER_URL}/admin/stats`, {
  headers: { 'X-Admin-Key': process.env.WORKER_ADMIN_KEY }
}).then(r => r.json())

// Объединяем по user_id → таблица:
// email | зарегистрирован | джобов | клипов | потрачено $
```

---

## 5. Worker: Python изменения

### 5.1 Новая зависимость
```toml
# services/worker/pyproject.toml
"PyJWT>=2.8"
```

### 5.2 Новый файл: app/auth.py (~30 строк)
```python
import jwt
from fastapi import Header, HTTPException
from app.config import get_settings

def get_current_user(authorization: str | None = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing auth token")
    token = authorization.removeprefix("Bearer ")
    try:
        s = get_settings()
        payload = jwt.decode(
            token, s.supabase_jwt_secret,
            algorithms=["HS256"], audience="authenticated"
        )
        return payload["sub"]   # Supabase user UUID
    except jwt.PyJWTError as e:
        raise HTTPException(401, f"Invalid token: {e}") from e
```

### 5.3 app/config.py — новые поля
```python
supabase_jwt_secret: str = ""    # из Supabase → Settings → API → JWT Secret
worker_admin_key: str = ""       # случайный секрет для /admin/stats
```

### 5.4 app/db.py — добавить user_id
```sql
-- Новая колонка в CREATE TABLE jobs:
user_id TEXT

-- Новый запрос для /admin/stats:
SELECT user_id,
       COUNT(*) as job_count,
       SUM(COALESCE(cost_usd, 0)) as total_cost_usd,
       SUM(clip_count) as clip_count
FROM jobs
WHERE user_id IS NOT NULL
GROUP BY user_id
```

### 5.5 app/main.py — изменения
```python
# Все /jobs/* эндпоинты получают Depends(get_current_user):
@app.post("/jobs")
def create_job(body, bg, user_id: str = Depends(get_current_user)):
    db.insert_job(..., user_id=user_id)

@app.get("/jobs/{job_id}")
def get_job(job_id, user_id: str = Depends(get_current_user)):
    job = db.get_job(job_id)
    if job is None or job.get("user_id") != user_id:
        raise HTTPException(404)  # не твой джоб — не видишь

# Обновить CORS:
allow_origins=[
    "http://localhost:3000",
    "https://*.vercel.app",
    # добавить продакшн-домен когда будет
]

# Новый эндпоинт:
@app.get("/admin/stats")
def admin_stats(x_admin_key: str = Header(None)):
    if x_admin_key != get_settings().worker_admin_key:
        raise HTTPException(403)
    return db.get_admin_stats()
```

### 5.6 Backward compatibility
Джобы созданные ДО внедрения auth имеют `user_id = NULL` в SQLite.
Они по-прежнему живут в БД, просто не видны ни одному юзеру (404).
Это нормально — старые анонимные джобы были тестовыми.

---

## 6. Переменные окружения

### Vercel (фронт)
```bash
NEXT_PUBLIC_SUPABASE_URL=https://xxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...anon...
SUPABASE_SERVICE_ROLE_KEY=eyJ...service_role...   # только сервер
NEXT_PUBLIC_WORKER_URL=https://xxx.ngrok.io       # ngrok URL воркера
WORKER_ADMIN_KEY=случайная-длинная-строка
ADMIN_EMAIL=akybaevtimur7@gmail.com
```

### Воркер (.env в корне репо)
```bash
SUPABASE_JWT_SECRET=xxx   # Supabase → Settings → API → JWT Secret
WORKER_ADMIN_KEY=та-же-строка-что-на-Vercel
# существующие ключи не меняются:
DEEPGRAM_API_KEY=...
GEMINI_API_KEY=...
LLM_MODEL=gemini-flash-latest
```

---

## 7. Деплой

### Фронт → Vercel
```bash
# Из корня репо:
npx vercel --cwd apps/web

# Или: подключить GitHub repo в Vercel UI
# Root Directory: apps/web
# Framework: Next.js (автодетект)
```

### Воркер → локально + ngrok
```powershell
# Терминал 1: воркер
$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
Set-Location "C:\Users\user\Desktop\ClipClow\services\worker"
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

# Терминал 2: туннель
ngrok http 8000
# Копируем https://xxx.ngrok.io → вставляем в NEXT_PUBLIC_WORKER_URL на Vercel
```

### Supabase
- Создать проект на supabase.com (бесплатно)
- Всё через UI, никакого кода

---

## 8. Тестирование

1. `just check` зелёный (unit-тесты, mypy, ruff, tsc, anti-drift)
2. **Auth flow**: зарегистрироваться email → попасть на главную → создать джоб → видеть свои джобы
3. **Изоляция**: другой аккаунт → не видит чужие джобы (404)
4. **Google OAuth**: кнопка → Google → редирект → главная
5. **Admin**: `/admin` → таблица юзеров + стоимость
6. **Без токена**: прямой curl к `/jobs` без заголовка → 401

---

## 9. Что НЕ меняется

- Вся логика пайплайна (stage0–5, reframe v3, editor)
- SQLite схема джобов (только добавляется одна колонка)
- Структура URL и API (только добавляется auth-проверка)
- Media-файлы (`/media/...`) — остаются публичными (не чувствительные)
- DEMO_PASSCODE механизм — удаляем (заменяем Supabase)
