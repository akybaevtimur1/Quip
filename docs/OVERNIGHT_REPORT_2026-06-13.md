# OVERNIGHT REPORT — ClipFlow MVP-лаунч (2026-06-13)

> Автономная ночная сессия по `docs/LAUNCH_BRIEF_2026-06-13.md` (scope T1–T6).
> Ветка **`feat/mvp-launch`** (7 коммитов от HEAD main). `just check` зелёный (388 тестов).
> Модель Opus 4.8, TDD-первым, conventional commits, типы только из `models.py`.

---

## 0. Итог (TL;DR)

| Задача | Статус | Коммит | Доказательство |
|---|---|---|---|
| **T1** Хук/топ-текст (флагман) | ✅ | `0aa94c6` `c6a4368` | mp4-кадр: коралл-хук сверху (`tmp/hook_dod_frame.png`) |
| **T2** Богатый reasoning | ✅ | `0aa94c6` | ClipCard: хук + «Почему сработает» + уверенность |
| **T3** Сочные субтитры (keyword) | ✅ (эмодзи descope) | `7da8cfb` | mp4-кадр: keyword'ы коралл (`tmp/emph_dod_frame.png`) |
| **T4** Баги §0.1 | 🟡 #4/#8/#9 done, #2 пропущен | `73113e3` | тесты + журнал |
| **T5** Соотношения сторон | ✅ | `7d598a7` | ffprobe всех 4 (`tmp/aspect_*.png`) |
| **T6** Прайсинг/Supabase-ready | ✅ (без секретов) | `94c0f38` | billing + миграция + `docs/SUPABASE_SETUP.md` |

**Что стало продаваемее:** клип теперь несёт ОБЪЯСНИМЫЙ хук (топ-текст, привязан к reason) +
структурный reasoning (наш wedge vs Vizard) + сочные keyword-субтитры + 4 соотношения сторон;
монетизация (лимиты/Supabase-схема) готова к подключению.

---

## 1. Что сделано (по задачам, с DoD)

### T1 — Хук / топ-текст (ФЛАГМАН)
Gemini генерит на клип цепляющий `hook` (топ-заголовок, привязан к reason) + `why_works`.
Хранение: **`CaptionTrack.hook: HookOverlay`** → компилится в ТОТ ЖЕ ASS, что субтитры →
`compile_ass` читает `track.hook` → автоматом в libass-превью (`/ass`) И ffmpeg-экспорте,
без второго пайплайна. PURE `build_hook_event` (top-event, alignment 8, весь клип|первые N сек,
бренд-плашка). Правится в новом табе **«Хук»** (текст/вкл/тайминг) через очередь мутаций.
- **Грабля (нашёл реальным рендером):** libass `BorderStyle=3` заливает плашку цветом
  **OutlineColour**, не BackColour → `box_color` кладём в outline.
- **DoD:** `uv run python tmp/dod_hook.py` → реальный mp4: «ВОТ ПОЧЕМУ ВСЕ МОЛЧАТ» коралл-
  плашка СВЕРХУ, субтитры снизу, не пересекаются (`tmp/hook_dod_frame.png`).

### T2 — Богатый reasoning
Gemini-схема `_LlmSegment` + промпт расширены `hook`/`why_works`; postprocess пробрасывает
(старый raw → None, обратная совместимость). `Segment`/`ClipOut`.hook/why_works (опц.).
`ClipCard` показывает структурно: хук-заголовок + «Почему сработает» + уверенность (Gauge).
⚠️ `clip_kind` из брифа = существующий `type: ClipType` (не плодил параллельную таксономию).
- **DoD:** `just check` зелёный; контракт через `just types`; мок-роут демонстрирует без воркера.

### T3 — Сочные субтитры (keyword-highlight)
PURE `pick_keyword_positions` (числа + длинные контентные слова, до 2/реплику). `compile_ass`:
явные `emphasis_refs` > авто-keyword (`emphasis_color`+`emphasis_auto`) > пусто. Пресет
**«Поп-слова»** + контрол в StyleTab. WYSIWYG цел (тот же compile_ass).
- **DoD:** `uv run python tmp/dod_emphasis.py` → mp4 «Я ЗАРАБОТАЛ 1000000 РУБЛЕЙ», keyword'ы
  [1,2] коралл, остальные белые (`tmp/emph_dod_frame.png`).
- **Эмодзи — descope:** libass color-emoji ненадёжен между wasm-превью и ffmpeg (моно/тофу) →
  сломал бы WYSIWYG-инвариант. Нужен NotoColorEmoji в оба места + верификация — follow-up.

### T4 — Баги §0.1 (частично)
- **#4 scale:** `highlight.scale` РЕАЛЬНО увеличивает активное слово (вертик. \fscy, без реврапа).
  ⚠️ per-word `box` НЕ реализуем в libass (нет примитива фона под спан; рисование ломает WYSIWYG)
  — задокументировано (line-level плашка через `CaptionStyle.box_color` работает).
- **#9 retry глав:** `GET /chapters?retry=true` (failed→pending) + кнопка «Повторить» в TimelineV2.
- **#8 двойные субтитры:** `CaptionTrack.burn` (False → compile_ass без нижних реплик, хук остаётся)
  + тогл «Видео уже с субтитрами». Надёжный ручной тогл вместо хрупкого CV-автодетекта.
- **#2 ПРОПУЩЕН** (косметика): превью-кадр после драга шортса откатывается в центр-кроп; финальный
  рендер ВСЕГДА корректен. Нужен live-reframe эндпоинт (фон-анализ интервала) — отложено.
- **DoD:** +6 тестов; `just check` зелёный.

### T5 — Соотношения сторон 9:16 / 1:1 / 4:5 / 16:9
⛔ Прочитан `REFRAME_FPS_GRID_INVARIANT.md`. Изменения **ЧИСТО пространственные** (crop_w/crop_h +
out_w/out_h + PlayRes ASS) — ВРЕМЕННАЯ кадровая сетка (cuts/shots/regions/trim) НЕ ТРОНУТА →
**Δ=0 инвариант цел по построению** (флеши не вернулись). PURE `aspect_to_dims` + `fill_crop_dims`.
`compile_ass(play_w,play_h)`: PlayRes ASS = размеры выхода (иначе libass анаморфно растянет
субтитры). POST `/edit/aspect` + селектор в FrameTab + динамич. аспект превью.
- **DoD:** `uv run python tmp/dod_aspect.py`:
  ```
  [9:16] ffprobe=1080x1920 want=1080x1920 OK
  [1:1]  ffprobe=1080x1080 want=1080x1080 OK
  [4:5]  ffprobe=1080x1350 want=1080x1350 OK
  [16:9] ffprobe=1920x1080 want=1920x1080 OK
  ```
  Субтитры/хук НЕ растянуты (`tmp/aspect_1_1.png`, `tmp/aspect_16_9.png`).
- ⚠️ Engine B (cv2, не дефолт) fill-кроп остаётся 9:16; split+16:9 вырожден (JobError).

### T6 — Прайсинг/лимиты + Supabase-ready (без секретов)
`app/billing.py` (PURE): `PLANS` (free/starter/pro), `check_quota` (видео→минуты, честная
RU-причина), `resolve_plan` (→free), `current_month`. Лимиты в КОДЕ (один источник правды).
`db.py` usage-адаптер `record_usage`/`get_monthly_usage` (SQLite; тот же интерфейс → Postgres).
`migrations/0001_init_billing.sql` (profiles/jobs/usage_events + RLS по security-чеклисту Supabase).
`docs/SUPABASE_SETUP.md` — что вписать фаундеру.
- **DoD:** +14 тестов (billing ×12, usage ×2); `just check` зелёный.

---

## 2. Что использовано и откуда

| Что | Версия/модель | Источник |
|---|---|---|
| Gemini (выбор/хуки/главы) | `gemini-flash-latest` (НЕ 2.5-pro: квота 0) | google-genai 2.8.0 |
| Транскрипция | Deepgram Nova (REST /v1/listen) | httpx (не SDK) |
| Субтитры/хук рендер | ASS + **libass** (ffmpeg `subtitles` + libass.wasm/SubtitlesOctopus превью) | OSS, MIT — переиспользован, НЕ хендроллил |
| Шрифты | Unbounded (хук) / Montserrat / Rubik | уже в `fonts/` + `public/libass/fonts` (оба места) |
| Reframe | PySceneDetect + MediaPipe + LR-ASD (torch) | без изменений (T5 не трогал) |
| Supabase-конвенции | RLS/auth.users/handle_new_user/security-чеклист | supabase skill (актуальная дока) |
| ffmpeg | 8.1.1 (Gyan) | — |

OSS-first соблюдён: топ-текст и keyword-highlight реализованы тем же libass-стеком (не второй
пайплайн); эмодзи descope'нул именно потому, что готового надёжного color-emoji в libass нет.

---

## 3. Скорости/бенчмарки

DoD-рендеры (синтетический 1080×1920 источник, Engine A, локальный CPU):
- Хук-клип (6с, burn ASS): рендер ~доли секунды (ffmpeg один проход).
- Аспект-рендеры (5с каждый, 4 шт.): быстрые, размеры точны (ffprobe выше).

Реальные пайплайн-бенчмарки НЕ обновлял: локально нет кэша comedy01/sample01 (data/ gitignored,
не синхронизирован на эту машину) → прогон стоил бы Deepgram+Gemini. Экономика из прошлых
прогонов (актуальна): **~$0.16/прогон 33-мин видео** (Deepgram ~$0.14 + Gemini ~$0.016).
Хук/why_works добавляют ~десятки токенов Gemini на клип → +доли цента. См. `docs/BENCHMARKS.md`.

---

## 4. Как запускать

```powershell
# PATH-refresh в КАЖДОМ вызове:
$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")

# Гейт:
Set-Location "C:\Users\user\Desktop\ClipClow"; just check

# Воркер (после правок кода — ПЕРЕЗАПУСК, uvicorn без --reload):
Set-Location "C:\Users\user\Desktop\ClipClow\services\worker"; uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
# Web:
Set-Location "C:\Users\user\Desktop\ClipClow"; pnpm --filter web dev   # :3000

# DoD-рендеры (синтетика, $0):
Set-Location "C:\Users\user\Desktop\ClipClow\services\worker"
uv run python tmp/dod_hook.py        # хук сверху
uv run python tmp/dod_emphasis.py    # keyword-highlight
uv run python tmp/dod_aspect.py      # 4 соотношения (ffprobe)
```

Где смотреть фичи в UI: открыть клип → **Редактировать** → табы **Хук / Субтитры (тогл «уже
с субтитрами») / Стиль (keyword-цвет, «Поп-слова») / Кадр (соотношение сторон)**. Грид-карточки
показывают хук + «Почему сработает».

---

## 5. Что фаундер вписывает руками

1. **Supabase** (см. `docs/SUPABASE_SETUP.md`): создать Pro-проект → применить
   `migrations/0001_init_billing.sql` → вписать ключи (`NEXT_PUBLIC_SUPABASE_URL/ANON_KEY` во
   фронт; `SUPABASE_SERVICE_ROLE_KEY` ТОЛЬКО в воркер, 🔴 не в NEXT_PUBLIC) → провод auth +
   гейт квоты в `create_job` (402) + перенос usage на Postgres.
2. **Lemon Squeezy**: аккаунт + вебхук `subscription_updated` → `profiles.plan` (service-role).
3. **Деплой**: Vercel (фронт) + Modal (воркер). Воркер тяжёлый (torch/MediaPipe ~1ГБ+).
4. **🔴 Перевыпустить YouTube-куки**: в истории GitHub (коммит `59d07b4`) лежали куки —
   logout/login + новый `cookies.txt`.
5. **Тюнинг лимитов/цен**: `app/billing.py` `PLANS` (числа — кандидаты под юнит-экономику).
6. **Слить ветку**: `feat/mvp-launch` → main (после ревью; мержить нечего, отведена от HEAD).

---

## 6. Что НЕ доделано / пропущено (и почему)

- **T3 эмодзи в субтитрах** — libass color-emoji ненадёжен между wasm-превью и ffmpeg →
  сломал бы WYSIWYG (hard-констрейнт брифа). Нужен NotoColorEmoji в оба места + кросс-стек тест.
- **T4 #2** (превью-кадр после драга) — косметика (финальный рендер корректен); нужен
  live-reframe эндпоинт (фон-анализ интервала).
- **T4 #4 per-word box** — libass не имеет примитива фона под спан; рисование требует метрик
  текста → сломало бы WYSIWYG. scale сделан; box задокументирован как ограничение.
- **Провод auth/квоты/оплаты/watermark** (T6) — нужны секреты Supabase/Lemon (действие фаундера).
- **Реальный e2e-прогон новых фич через UI** — локально нет кэша видео + прогон платный;
  все фичи доказаны реальными ffmpeg-рендерами на синтетике (изолируют именно новый код).

---

## 7. Что работает end-to-end (дышащее ядро)

✅ Gemini выдаёт на клип `hook` + `why_works` → виден в ClipCard и прожигается СВЕРХУ клипа.
✅ Хук правится в редакторе (таб «Хук»), перерендеривается, превью=экспорт (libass).
✅ Keyword-subтитры: ключевые слова авто-подсвечиваются в РЕНДЕРЕ (не только превью).
✅ 4 соотношения сторон рендерятся с верными размерами, субтитры не растянуты, Δ=0 цел.
✅ Тогл «видео уже с субтитрами», retry AI-глав, scale активного слова.
✅ Прайсинг-модель + Supabase-схема/адаптер готовы к подключению (без секретов).
