# CLAUDE.md — Journal (архив истории)

> Полный хронологический журнал прогресса. Вынесен из CLAUDE.md (тот раздулся). Это ИСТОРИЯ / ADR —
> «как и почему так сделано». Актуальное состояние проекта = docs/README.md. Правила = CLAUDE.md.
> Новые заметные решения дописывай СЮДА (не в CLAUDE.md).

### 2026-06-28 (фича) — clip card redesign: tone/key_quote/glow/accordion + stable sort + tiered score color
Полная реализация спека `2026-06-28-clip-card-redesign.md`. Бэкенд: `tone`+`key_quote` добавлены в `Segment`/`ClipOut`/`_LlmSegment`, `postprocess()` читает оба поля, промпт получил STEP 5 `key_quote`, `build_clip_out()` маппит оба поля, новый эндпоинт `POST /jobs/{id}/clips/{id}/refresh-analysis` (+ `RefreshClipBody` в models.py, `patch_clip_analysis` в cloud_state+db). Фронт: `ClipCard` — amber→tiered score (≥90 green/70 amber/50 orange/<50 rose, цвет анимируется при count-up), tone glow на Card, emoji badge, key moment blockquote, accordion «Why this clip ↓» с 4 signal bars, stale banner + Refresh. `ClipGrid` — stable sort по score (useMemo на ID-ключе, позиция не меняется при render complete). Баг пофикшен: `"standalone"` не ClipType → заменён на `"hook"` (4 бара). `just types` прогнан, `just check` зелёный (1023 pytest).

### 2026-06-28 (дизайн) — спека «Remove silences» (Phase 1 client-side)
Забраундстормили и записали полный дизайн фичи удаления пауз из клипов. Phase 1 = чисто фронт: `lib/silenceMap.ts` вычисляет `keepIntervals` из готовых word-timestamps Deepgram, `PreviewPlayer` прыгает через тишину в rVFC-loop (`video.currentTime = silenceEnd`). Новая вкладка `SilenceTab` в редакторе: toggle + slider Natural↔Tight + advanced panel (padding, max_pause). Глобальные дефолты в `/account` через `profiles.style_preferences`. Данные клипа через `ClipEdit.silence_config` + `just types`. Phase 2 (FFmpeg concat re-render + Silero VAD) задокументирована, но ОТЛОЖЕНА. Спека: `docs/superpowers/specs/2026-06-28-silence-removal-design.md`.

### 2026-06-26 (прод-фиксы) — рендер вотермарки + живучесть Gemini
Два бага воркера. **(1) Рендер.** ВСЕ free-клипы падали `ffmpeg exit 8: Filter not found`, потому что
`build_watermark_drawtext` получал `fontsdir` (ПАПКУ `../../fonts`, как для фильтра субтитров) в
`drawtext fontfile=`, который ждёт ФАЙЛ-шрифт → init drawtext падал → весь filter_complex отвергался.
Стало рвать всё только сейчас: коммит `cdfae20` сделал free-вотермарку всегда-включённой, и битый путь
впервые реально выполнился. Фикс: хелпер `_watermark_fontfile(fontsdir) → <dir>/Montserrat.ttf` во всех
3 местах вызова (build_smooth_filter / Engine B / build_timeline_filter). Регресс-тесты (fontfile=ФАЙЛ,
не папка) + проверено реальным ffmpeg (exit 0). Вотермарка собирается заново на каждый рендер →
`reframe_regions`-кэш чистить НЕ надо. **(2) Gemini.** Google часто отдаёт транзиентные 429/503/таймаут;
джоба не должна падать от чиха. `_MAX_ATTEMPTS` 4 → 20 (агент `clip_agent` подхватил централизованно).
Ретраится ТОЛЬКО вызов generate_content (дёшево — до биллинга токенов), парсинг ответа вне цикла.
Поведенческий тест. Гейт `just check` зелёный (971 pytest + 62 vitest + anti-drift).

### 2026-06-25 (лендинг) — новый «Readout»-лендинг интегрирован на /
Перенесли отдельный пакет `quip-landing-delivery/` в прод `apps/web` как боевую главную. Новая
route-group `app/(home)/page.tsx` — async Server Component: читает сессию через `getOptionalUser` и
прокидывает `authed` в Nav/Hero/FinalCta (залогинен → CTA на `/dashboard` «Open the app», гость →
`/signup`). Свои Nav+Footer; старый `app/(marketing)/page.tsx` удалён; под-страницы
(`pricing/terms/privacy/use-case`) остались на общем `MarketingNav`+`Footer` (НЕ тронуты) — на сайте
намеренно два chrome'а (новый на `/`, старый на под-страницах). Секции/компоненты →
`components/landing/{sections,components}`, контент-слой → `lib/landingContent.ts`, депы `motion` +
`@phosphor-icons/react`. `globals.css` — ТОЛЬКО аддитивно (`container-page/graticule/grain/lift/num/
mark-accent/edge-fade`); кривая `--ease-out` (emil) ЗАСКОУПЛЕНА на `.grain`, чтобы глобальная
Tailwind-утилита `ease-out` (dashboard/NavProgress) НЕ менялась. Ассеты `public/clips`+`public/media`
(3 mp4 + постеры/кадры); `.vercelignore` негейтит 3 лендинг-mp4 после неякорного `*.mp4` и исключает
`quip-landing-delivery/` из загрузки. Metadata `/` (title/desc/OG/twitter) задан по брифу, без em-dash.
Ревью 6-мерным адверсариальным workflow (CSS/токены, RSC/Next16, ассеты/деплой, бренд, auth/роутинг,
регрессии — все находки разобраны); фиксы: скоуп `--ease-out`, демоут построчных коралловых галочек в
таблице сравнения → нейтральный ink (правило coral-scarcity, DESIGN.md). Гейт `just check` зелёный
(eslint/mypy/tsc/968 pytest/62 vitest/anti-drift), `next build` чист, 8 ассетов = 200, копия лендинга
0 em-dash. Остаток em-dash в HTML (8) — host JSON-LD (`faq`/`plans`/`siteConfig`), пред-существующий,
невидимый, вне scope задачи. Coral-confidence-гейдж оставлен (намеренный signature motif брифа, хоть
DESIGN.md и предписывает зелёный confidence для in-app дашборда). Octarin-память записана.

### 2026-06-25 (YouTube-надёжность ч.2) — мульти-куки фолбэк + видимый статус скачки
Один cookie-jar на DC-IP — коинфлип. Сделали **пул jar'ов** с фолбэком: фаундер кладёт N
`www.youtube.com_cookies*.txt` в корень → worker.py печёт их в `/root/cookies/jar_NN.txt`
(`ytdlp_cookies.baked_jars()`). `run.py` строит кандидаты = [R2-ротирующийся jar] + [каждый
запечённый jar в writable-temp] и пробует по очереди: бот-гейт (`YoutubeBotGateError`, поднимается
в `download_youtube` когда `is_bot_gate(stderr)`) → СЛЕДУЮЩИЙ jar; НЕ-бот-провал
(private/too-long/removed/age) → сразу fail (другой jar не спасёт); первый успех → push победителя в
R2 (current-best). Падаем ТОЛЬКО если ВСЕ загейтили. Математика: P(хотя бы 1 из N) ≈ 1−(1−p)^N →
~40-70% на jar превращается в ~99% на 5 jar'ах (потолок IP не двигается — флагнутый IP валит все).
Фронт (`JobProgress.tsx`): при `downloading`+`source_kind=youtube` показываем «Fetching from
YouTube» + заметку «best-effort, может упасть → зальёшь файл» — юзер видит фолибл-стадию. Секреты:
`.gitignore` `*_cookies*.txt` (старый `*_cookies.txt` НЕ матчил `(2)/(3)/(4)`). Верификация: probe
гоняет весь пул → **5/5 jar'ов прошли** на боевом IP. Octarin-решение записано.

### 2026-06-25 (YouTube-надёжность) — куки → POT → tv,android_vr; вердикт: best-effort, прокси отклонён
Бот-гейт YouTube на DC-IP Modal бил даже с валидными ротируемыми куками. Прошли цепочку рычагов
(research-workflow'ы + probe-диагностика `probe_youtube_pot` на боевом IP):
1. **bgutil PO-token (deno script mode)** — собрали в образ (переиспользован Deno, без Node; canvas
   ставится prebuilt'ом — 0 apt-депов; `git clone --branch 1.3.1` + `deno install`). Работает, КОГДА
   генерируется, но ненадёжно (~1/6): захардкоженный таймаут плагина 15/20с, холодный
   `deno run generate_once.ts` (компиляция TS + нативный canvas + BotGuard) не успевает на
   scale-to-zero контейнере (известный баг bgutil #232).
2. **Корень глубже (синтез-агент):** клиент `web_safari` ПРИНУЖДАЕТ GVS PO-token. Клиенты
   **`tv`/`android_vr` POT не требуют** и чтут куки → `config.ytdlp_player_client="tv,android_vr"`
   (через `--extractor-args youtube:player_client=...`); POT остаётся бэкстопом для остаточных клиентов.
3. **Честный замер на боевом IP:** ~4/10, ДЕГРАДИРУЕТ под нагрузкой. Причина — НЕ видео/клиент/POT, а
   **репутация IP**: 16+ авто-запросов за ~10 мин сами захардили Modal-IP. Это ровно потолок из
   brutally-honest синтеза: **$0 не пробивает флагнутый DC-IP** (надёжно — только residential-прокси
   ~$10-20/мес на extractor-запрос; seam `YTDLP_PROXY` готов в `build_youtube_cmd`).
**Решение фаундера:** оставить **best-effort бесплатно**, прокси НЕ подключать. Отказы → graceful
«скачай сам и залей» (`classify_youtube_error`). bgutil HTTP-сервер (#2 из синтеза) пропущен: чинит
POT, но POT для tv/android_vr не нужен, а IP-гейт не бьёт. Диагностика в проде:
`modal run deploy/modal/worker.py::probe_youtube_pot --url <u>`. Octarin-решение записано.

### 2026-06-25 (фиксы #2 + ДЕПЛОЙ) — редактор + worker-устойчивость + ротация куков (в ПРОДЕ)
**Деплой:** всё из записи ниже (3 фичи) + эти фиксы уехали в ПРОД: воркер `modal deploy` (Modal),
фронт `vercel deploy --prod` (CLI — GitHub-автодеплой мёртв, акк `akybaevtimur1` заблокан), ветка
смёрджена в `main`. Закрывает «НЕ задеплоено» из записи ниже. По фидбэку фаундера на живом проде,
фикс-агентами (Opus, непересекающиеся домены, TDD, `just check` зелёный):
- **Редактор (3 фикса).** (1) Агент-чат: завершённые ходы больше НЕ зажигают «Working on it…» при
  новом сообщении — корень: единый глобальный флаг `running` гнал спиннер на ВСЕ строки; теперь живёт
  только последняя группа активного рана (чистый `processLiveFlags` + тесты, `lib/agentChat.ts`).
  (2) URL-поле YouTube: двойная рамка (рамка лейбла + глобальное `:focus-visible`-кольцо на инпуте) →
  `focus-visible:shadow-none` на инпуте. (3) Кнопка «Update» на шаблоне — переписывает шаблон на месте
  (`upsert` по id) вместо delete+add; потребовала правки `main.py` (`/me/templates` чтит клиентский id).
- **Worker-устойчивость.** (а) `JobError` теперь круглотрипится через Modal-pickle
  (`super().__init__(stage,reason)` + `__reduce__`) — раньше координатор падал на «missing argument
  reason», и юзер видел сырой traceback. (б) **Per-clip containment:** один сбойный клип (ffmpeg «0
  видео-кадров» — reframe edge-case на конкретном видео) больше НЕ валит весь джоб — логируется,
  остаётся с пустым `video_url`, остальные клипы рендерятся; если ВСЕ упали — джоб честно failed.
  Reframe-математика НЕ тронута (176 reframe-тестов зелёные).
- **Ротация YouTube-куков (бесплатный обход бот-гейта DC-IP — бот-гейт реально сработал на проде).**
  Куки живут в R2 (`internal/ytdlp_cookies.txt`); на каждом скачивании тянем jar в writable-temp,
  yt-dlp ротирует его на месте, пушим обратно при успехе → сессия сама освежается. Keep-warm cron (раз
  в ~2 дня, `--skip-download`) держит её тёплой в простое; `seed_ytdlp_cookies` — разовый засев из
  запечённого `/root/cookies.txt`. Фаундер сеет куки ОДИН раз. Без тихих фолбэков. (Глубже — PO-token —
  отдельным заходом.) Источник: `app/ytdlp_cookies.py` + `run.py` import-branch + `worker.py` cron/seed.

### 2026-06-25 — три фикса (ветка `feat/yt-import-global-templates-set-password`, НЕ задеплоено)
Три независимых фичи, реализованы 3 параллельными Opus-агентами (строгие границы файлов, один владелец на
файл), TDD на чистой логике, `just check` зелёный, без деплоя (правило фаундера на эту сессию).
- **YouTube-импорт вернули (best-effort).** Фича была СПРЯТАНА (коммит `9ec7f1a` убрал URL-инпут из
  `SourceForm`), бэкенд всё это время жив. `SourceForm` снова показывает вторичное URL-поле (upload —
  первичен). Воркер качает серверно (`download_youtube`): avc1-first ≤1080p (reframe-safe), `+faststart`
  (moov-atom), `--match-filter "!is_live & duration<cap"` + `--no-playlist`. Новая чистая
  `classify_youtube_error(stderr)` → понятные английские сообщения «скачай сам через ТГ-бота/другой сайт и
  загрузи файл» (bot-gate/429/403, private, members-only, removed, region, age-gate, live; TDD поймал баг
  порядка: age-gate — подстрока bot-gate). Рычаг `YTDLP_PROXY` (env, OFF — без трат), прокинут через
  `import_youtube`→`run.py`. Образ `yt-dlp`→`yt-dlp[default]` (локальный EJS-солвер) — вступит в силу при
  `modal deploy`. Честный caveat: бот-гейт YouTube на DC-IP нестабилен, yt-dlp надо часто бампать. 44 теста.
- **Стиль-темплейты: глобально + помнят ВСЁ.** UI «My templates» вынесен из таба субтитров в поповер
  «Style templates» в шапке редактора (`EditorHeader`→`TemplatesPanel`). Темплейт теперь хранит
  позицию/размер субтитров + тайминг хука (`full_clip`/`duration_sec`/`enabled`) + позицию хука (раньше —
  только цвета); применение ДВИГАЕТ геометрию (старое правило «position preserved» осознанно снято по
  просьбе фаундера; текст хука НЕ копируется — это контент). `HOOK_LOOK_FIELDS`⇄`HOOK_LOOK_KEYS` — один
  канонический список (lockstep). Переиспользована JSONB-колонка `profiles.style_preferences` (без
  миграции), back-compat для старых темплейтов (геометрию подхватят при пересохранении). 15 тестов.
- **Опциональный set-password в `/account`.** Новая панель `AccountSecurity`
  (`supabase.auth.updateUser({password})`) — OAuth/OTP-юзеры (без пароля) могут включить вход по паролю;
  текст ошибки «Invalid credentials» на логине теперь ведёт passwordless-юзеров к Google/коду + настройкам,
  а не в тупик. ⚠️ Если в Supabase включён «Secure password change» (reauth/nonce) — `updateUser` потребует
  nonce (config-only, фаундеру проверить). Forgot-password — отложено. 56 web-тестов.
- **Free-тир: качество как у платных + ЯВНАЯ вотермарка (решение фаундера 2026-06-25).** Снят кап
  720p → free рендерит ПОЛНОЕ 1080p; единственный отличитель free/paid теперь = вотермарка (сделана
  заметнее: крупнее 3% vs 2.2% высоты / плотнее alpha .92 vs .78 / сильнее тень — в
  `stage5_render.build_watermark_drawtext`). `billing.py` free `max_resolution` 720→1080 (энкод free
  остался crf20/veryfast ради стоимости рендера; платные — crf18/medium + без вотермарки) + зеркало
  `lib/plans.ts` («1080p export with a Quip watermark») + тесты `test_billing`. Скачивание yt-dlp
  (≤1080p avc1) от плана и так не зависело — теперь и ВЫХОД free до 1080p.
- **i18n:** зафиксировано (память + Octarin), что RU+EN — это ПЛАН (`next-intl`, отложенная фаза, НЕ
  установлен); до тех пор весь UI — английский, без хардкода смеси.

### 2026-06-24 (follow-up #2) — хуки: убрать «Имя:»-ярлык и 1-е лицо, писать в 3-м лице вопросом
Фаундер по скрину: хук «TOM HOLLAND: WHY I DELETED INSTAGRAM» — мёртвый. Хочет живое «почему Том удалил
инсту». Ужесточил `prompts/select_moments.v2.txt` + `regenerate_hook.v1.txt`: ⛔ HARD BAN на (а)
`Имя:`/`Имя —`-ярлык, (б) `Name on <topic>`/`thoughts on` (подкаст-заголовок), (в) ПЕРВОЕ ЛИЦО `I/my/me`
(пиши ПРО спикера, не ОТ него) с примерами ✗→✓; дефолт = 3-е лицо, имя как ПОДЛЕЖАЩЕЕ внутри фразы, вести
вопросом Why/How/The real reason. Бенч на реальном транскрипте: «Why Tom Holland pushed through social
anxiety sober», «How sobriety transformed Tom Holland's life» — без двоеточий, без `on`, без `I`. Стили
(story/insight/question/bold_claim/number) не тронуты; `just check` зелёный.

### 2026-06-24 (follow-up по фидбэку фаундера) — reframe: ноги-в-кадре + плавность наведения
Фаундер на ночных клипах: «авто-wide не работает (в кадре ноги), плавное наведение убил — дёрганое».
Разобрано НА КАДРАХ присланных клипов (не угадано), фикс проверен на реальном видео.
- **Ноги/тело = silence-gate.** Реклайн/establishing-планы кропались fill в вертикальный strip по телу.
  Корень (трек-стат clip_2): эти планы — это где субъект МОЛЧИТ (ASD speak −1.68/−2.03), а говорящие
  головы ≥ ~0. Старый гейт «→ wide» требовал И мелкое лицо (width<0.08) — у реклайна width 0.17 → не
  срабатывал. Фикс: одно лицо с РЕАЛЬНЫМ speak < −0.6 → fit (wide). Покадрово: реклайн-планы теперь
  широкий 2-shot (Tom+host+комната), ног нет.
- **Сентинель −9 ≠ молчит (важная ловушка).** `asd_reframe._SILENT=-9` ставится когда ASD ПРОПУЩЕН
  (одна дорожка в сегменте, perf), т.е. «нет скора», а НЕ «молчит». Первый заход гейта `speak<−0.6`
  поймал и −9 → одно-планный talking-head clip_1 ушёл в wide (регресс!). Фикс: гейт требует
  `−5 < speak < −0.6` (исключает −9). clip_1 снова tight fill. Подтверждено покадрово.
- **Плавность = hybrid вместо чистого снапа.** Утренний фикс пол-лица снапил cx на КАЖДОЙ склейке →
  фаундер «дёрганое». Корень (jump-анализ): склейки тут реальные (host↔Tom, контент меняется → снап
  замаскирован), но между ОДНОТИПНЫМИ планами снап лишний. Фикс: hybrid — глайд от прошлого центра если
  |Δcx|≤0.10 (плавно), снап только если дальше (пол-лица). clip_2: было 3 снапа+2 дёрганых fill-на-ногах
  → стало 1 снап (реальный cut) + глайд + 2 широких. TDD: +3 теста (silent→wide, −9→fill, near→glide).
  Синхронь: `docs/REFRAME_FPS_GRID_INVARIANT.md`.

### 2026-06-24 (ночной прогон качества обработки) — reframe init, хуки, моменты, обрезка, split-выпил
Автономный ночной прогон (4 домена), всё проверено на РЕАЛЬНОМ видео фаундера (Tom Holland, 25fps,
111 мин), не на unit-тестах. Доказательства → `docs/NIGHT_RUN_2026-06-24.md`.
- **B — «пол-лица» в начале шота (reframe).** Корень (репро покадрово, не угадан): `plan_regions`
  инитил EMA нового fill-региона от `prev_fill_end_cx` (конец прошлого шота, «анти-телепорт» `ebfc3dc`).
  На склейке к ДРУГОМУ спикеру / на коротком шоте кроп открывался МЕЖДУ людьми и медленно полз = пол-
  лица. Фикс: каждый fill-шот открывается на СВОЁМ говорящем (`init_cx=None` → первый cx цели). Жёсткий
  cut маскирует снап, EMA ВНУТРИ шота не тронут (steady-state плавность та же), кадровая сетка цела.
  Репро seg 240–270: gap traj_start↔face до **0.282 → 0.0** на ВСЕХ 8 шотах. Синхронь:
  `docs/REFRAME_FPS_GRID_INVARIANT.md` §«Что МОЖНО менять».
- **C — хуки переписаны.** Старый промпт пушил `pov` ПЕРВЫМ стилем (фаундер: «POV-кал») и кап ≤6 слов
  (его эталон «How Tom Holland decided to take a break from social media» = 9 слов). Новый промпт
  (`prompts/select_moments.v2.txt` + `regenerate_hook.v1.txt`): grounding WHO+WHAT+SHAPE, стили
  story/insight/question/bold_claim/number (POV выпилен), ≤10 слов, имя спикера из title, бан вагового
  «realization/journey/protects», запрет обещать пейофф вне клипа. Before/after на реальном транскрипте:
  «POV: you're the only ballet kid» → «Tom Holland: 'I was definitely addicted to alcohol'»; адверс.
  судьи: mean 2.75→3.44, POV-мусор исчез, 7/9 accurate. (Хук, обещавший пейофф вне клипа = баг ОБРЕЗКИ,
  домен D.)
- **D2 — обрезка на чистых речевых границах (КРИТИЧНО).** Конец клипа ловил реплику ДРУГОГО спикера
  («рандомный выкрик в конце»): `snap_end_index` тянул вперёд до 8 слов к .?!, пересекая смену
  спикера, а транскрипт вообще не нёс меток спикера. Включил Deepgram `diarize=true` + `Word.speaker`
  (codegen `just types`). `snap_end_index` теперь speaker-aware: режет хвост ЧУЖОГО спикера, не тянет
  границу через смену спикера, при перебивке откатывается к последнему .?! основного. Без меток =
  байт-в-байт legacy (старые тесты целы). TDD: 5 тестов (red→green). Проверка на РЕАЛЬНОМ
  диаризованном транскрипте: 5/12 клипов поправлены, напр. клип гостя сбросил 31 слово ХОСТА в хвосте
  → теперь кончается на фразе гостя; ВСЕ клипы кончаются на .?!. Миграция БД не нужна (speaker опц.).
- **D1 — больше/лучше моментов.** Промпт: блок SELECTION QUALITY (10-20 сильных на длинном видео,
  РАЗБРОС по всему видео; скип rambling / setup-без-пейоффа / small-talk; score = реальная сила, не
  раздувать). Дефолт `max_clips` 8→12 (UI Auto и так шлёт 30). На реальном видео клипы разбросаны
  16:28–53:03, все конкретные/сильные.
- **A — split-режим УДАЛЁН (MVP-упрощение).** Авто теперь: РОВНО одно лицо → fill (тайт), ЛЮБОЙ
  другой случай (>1 лица / нет лиц / объекты) → fit (wide). `config.reframe_split_enabled` True→False
  (авто НИКОГДА не отдаёт split; сигнатуры планировщиков и dead split-код оставлены как safety-net —
  можно удалить позже). UI: тайл «Split (2 speakers)» убран из `FrameTab` (+ узкие типы FrameMode/
  setCropOverride; `CropBody.mode` Literal без split → API 422 на split). Легаси split (persist-регион
  ИЛИ ручной override) gracefully коэрсится в fit: `reframe_cache._region_from_dict/_manual_region/
  _recolor_region`. Кадровая сетка/инвариант не тронуты. Тесты обновлены (split→fit / 422), 896 зелёных.
  ⚠️ Чат-агент тех. ещё принимает mode=split в тулзе, но он коэрсится в fit на рендере → безвреден
  (можно вычистить из tools.py/clip_agent позже).

### 2026-06-23 (свип №5) — 🎯 ФЛЕШ tight↔wide: 1-кадровый offset склейки (fps-зависимый) + зум превью
Фаундер: «переход из вертикального вида в горизонтальный мелькает; должно быть мгновенно по cut, без
зума». Разобрано ПОКАДРОВО на его 25fps видео (Tom Holland), не на глаз. ЧЕТЫРЕ независимых корня
(не один — поэтому не добивалось сразу) + правка вёрстки VIDEO MAP:
- **Корень №1 (рендер):** `detect_scene_cuts` жёстко вычитал `-1` из кадра склейки PySceneDetect. Этот
  `-1` верен ТОЛЬКО для дробного fps (29.97/23.976/59.94 — реэнкод `-r fps` ресэмплит в CFR → детектор
  опаздывает на кадр). На ЦЕЛОМ 25fps ресэмпла нет → склейка точна → `-1` уводил границу режима на
  кадр РАНЬШЕ контент-склейки → 1 кадр старого шота в НОВОМ (wide) режиме = флеш. Фикс:
  `_scene_cut_offset(fps)` = 1 (дробный) / 0 (целый), `2e86b83`. Покадрово: было 401=старый-в-wide;
  стало 401=старый-tight, 402=новый-wide (ровно на склейке). 29.97-путь байт-в-байт прежний.
- **Корень №2 (превью):** мастер-видео в `PreviewPlayer` несло CSS `transition-[object-position] 300ms`
  на ВСЕХ сменах → на смене режима браузер пан-анимировал кроп = «зум-эффект» на стыке. Фикс: мгновенный
  switch на смене режима через `useLayoutEffect` (гасим анимацию на 1 кадр; плавный пан остаётся ВНУТРИ
  fill), `5ac305c`.
- **Корень №3 (стейл):** запечённые `reframe_regions` со старыми границами/ложными wide → `/reframe`
  fast-path отдаёт их без пересчёта → код-фикс «не виден», пока не сбросишь
  `update job_artifacts set reframe_regions = null` ПОСЛЕ деплоя (Octarin-память).
- **Корень №4 (превью, ГЛАВНЫЙ для «мелькает даже на свежем аплоаде»):** `PreviewPlayer` брал текущее
  время (→ режим) из события `timeupdate` (~4Hz) → режим ОТСТАВАЛ от показанного кадра до ~250мс → на
  склейке новый шот висел в старом кропе четверть секунды = мельк, НЕЗАВИСИМО от границы/кэша. Фикс:
  `requestVideoFrameCallback` (покадрово, media-time кадра), rAF-фолбэк, `c6b518b`. Замер на проде:
  250мс → 56мс. Рендер при этом кадрово-точен (0 лага) — скачанный клип чист всегда.
- **Грабли DoD:** `verify_grid_fix.py` (Δ=0) НЕ ловит №1 — он про grid-целочисленность, а не про
  совпадение с КОНТЕНТ-склейкой. tight↔wide проверять ПОКАДРОВЫМ фрейм-степом рендера на стыке.
- **VIDEO MAP клип-теги (вёрстка, `b83aa2b`):** inline-ссылки `Clip #N` в нарративе
  (`VideoMap.parseNarrative`) рвались между строк («Clip»/«#3») и слипались в подчёркнутую стену при
  длинном ряде (Clip #6…#24). Фикс: каждый рендерим как `inline-block whitespace-nowrap` coral-pill →
  тег атомарен (не рвётся), ряд читается раздельными тегами с воздухом. Проверено вживую (Playwright):
  48 тегов, `white-space:nowrap`, `display:inline-block`, `singleLine:true` — без разрывов.

Деплой свипа №5: воркер (Modal, `2e86b83`) + Vercel (`5ac305c`, `c6b518b`, `b83aa2b`). `git push`
заблокирован — GitHub-аккаунт фаундера suspended (403); коммиты целы локально.

### 2026-06-23 (свип №3) — 🎯 АВТО-WIDE НА 2 ЛЮДЯХ: порог был слишком строгий (репро на реальном видео)
Фаундер: «ИИ не уходит в wide, когда в кадре очевидно два человека; приходится вручную ставить wide
посреди шота → резкий зум-„флеш“». Разобрано по REAL-VIDEO (его тестовый клип Tom Holland × Jay
Shetty, 1920×1080 **@25fps**), покадрово, не на глаз.
- **Корень (НЕ Gemini, НЕ mean-vs-perframe):** `_is_wide_shot` требовал размах центров лиц >
  `crop_w_frac` (≈0.317 = полная ширина 9:16-кропа на 1080p). Реальные 2-shot интервью дают размах
  **0.258/0.272/0.284/0.288** — ВСЕ ниже 0.317 → каждый 2-shot падал в fill → tight-кроп на одном,
  второй терялся. Per-frame размах тоже ~0.28 (не помог бы) — дело чисто в пороге. Подтверждено
  диагностикой треков на обоих видео (job_060aaf70f05c: 0.13 → корректно fill; TH: 0.26–0.29 → должно
  быть wide, но было fill).
- **Фикс:** `spread_min = crop_w_frac * _WIDE_SPREAD_RATIO` (0.70 ≈ 0.222). Ловит 0.26+ как wide,
  отвергает кластер/одно лицо (~0.13/0.03). Константа (не конфиг) по конвенции `_MIN_FACE_FRAC`.
  Только режим (fill→fit), границы не двигаются → инвариант цел. Verified на TH-видео: тот же 2-shot
  теперь fit с ОБОИМИ в кадре; одиночные/кластер остались fill. Коммит `9a27978`, гейт зелёный, деплой.
- **Про «флеш»:** на 25fps grid-флеш МАТЕМАТИЧЕСКИ невозможен (точное округление). Покадрово прогнаны
  3 сценария рендера (реальная склейка / override-на-весь-шот / Split-посреди-шота) — wrong-frame НЕТ.
  «Флеш» = резкий зум при ручном wide ПОСРЕДИ непрерывного шота (приходилось, т.к. авто-wide молчал).
  Чиним №1 → авто-wide встаёт на РЕАЛЬНОЙ склейке (зум маскируется сменой контента) → ручной mid-shot
  рез не нужен → резкого зума нет. (Если wrong-frame всё же вылезет — это фронт-ПРЕВЬЮ, копать live.)
- ⚠️ Tuning: 0.70 чуть «щедрый» — пограничный одиночный medium может уйти в wide (fit = полный кадр +
  блюр, никого не режет — безопасный дефолт; фаундер хочет именно «не терять людей»). Тюним константой.

### 2026-06-23 (свип №2) — 🩹 КОРНЕВОЙ фикс editor-флеша + восстановление коротких шотов + Split + jitter
Глубокий разбор (systematic-debugging + параллельные саб-агенты с состязательным ревью). 4 домена,
гейт `just check` зелёный, **реал-видео DoD на 29.97fps** (не только юнит). Корни ⇒ фиксы:
- **A. Editor-флеш tight↔wide (мульти-интервал) — ЗАКРЫТ корень в `flatten_timeline`.** Батч и
  ОДНО-интервальный editor-рендер давно frame-accurate (`-ss aligned_start`), а МУЛЬТИ-интервальный
  (`render_timeline` при >1 интервала → `flatten_timeline`+`build_timeline_filter`, без `-ss`) якорил
  trim-кадры на СЫРОЙ `iv.source_start` + `round(.,3)`, хотя регионы построены reframe_segment от
  `aligned_start=round(source_start*fps)/fps`. На off-grid старте (после трима/нарезки)
  `round((source_start+t0)*fps)` промахивал на ±1 кадр (численно **1.39%** комбо на ≠25fps, 0% после) →
  1 кадр нового шота со старым кропом = флеш (невидим на 25fps/целых стартах → тесты были зелёными
  5 сессий). Фикс: якорим на тот же `aligned` → `src_f0=round((aligned+r.t0)*fps)` =
  `round(source_start*fps)+cut_frame` ТОЧНО. Это closure editor-пути, помеченного в инварианте как
  «НЕ закрыто». `stage5_render.flatten_timeline` + матрица-тест `test_timeline_filter`.
- **C. Детектор «съедал» короткие шоты → нельзя поставить tight.** НЕ порог 27 (H1 снят). Два слоя:
  (1) `ContentDetector` без `min_scene_len` → дефолт либы 15 кадров + FlashFilter MERGE дропал <0.5с
  cut'ы; (2) `merge_short_regions(1.5с)` поглощал короткий регион в предыдущий. Фикс: явный
  `min_scene_len` от нативного fps (кноб `reframe_min_scene_sec=0.25`, протянут во все 4 вызывателя) +
  `reframe_min_hold_sec` 1.5→0.8 (после фикса A смена fill↔fit на реальной склейке = невидимый hard-cut
  → агрессивный merge больше не нужен как анти-флеш, лишь лёгкий анти-строб). Границы — на нативных
  кадрах (Δ=0).
- **C/E. Ручной Split + split на бэке.** `apply_overrides_to_regions` переписан с «recolor целого
  региона по midpoint» на **interval-painting**: режет регион на frame-snapped (`round(t*fps)/fps`)
  под-интервалы и красит каждый по ПОСЛЕДНЕМУ покрывающему override → юзер тайтит ЛЮБОЙ под-диапазон
  слитого шота, и НЕСКОЛЬКО правок на одном шоте не теряются (старый last-wins-на-регион ронял все,
  кроме последней). Фронт: «Split here» на плейхеде (`FitTimeline`, клиентские резы; контракт
  CropOverride НЕ менялся — бэк сам снапит и режет). Все новые границы frame-snapped ⇒ инвариант цел.
- **D. Gemini 503.** Фоллбэк УЖЕ работал (503 транзиентна → ретрай+failover+явный JobError, не тихо).
  Дыра одна — нет jitter в backoff → синхронные «штормы» ретраев при общем 503. Фикс: equal-jitter
  `_backoff_delay` (`stage2_select` + `clip_agent`).
- **B (деплой/кэш).** Авто-wide (`b17d509`) в ветке корректен; нужен передеплой воркера + инвалидация
  запечённых старых `reframe_regions` (старые клипы отдают tight из кэша 0013, пока не пересчитаны).

### 2026-06-23 — 🐛 ФИКС-СВИП 4 бага по фидбэку фаундера (ветка `editor-snapping`) — ЗАДЕПЛОЕНО (Vercel+Modal)
Четыре независимых бага, найдены по systematic-debugging (корень до фикса, без угадывания), гейт зелёный
перед каждым коммитом, деплой в обход GitHub (аккаунт `Varenik-vkusny` suspended → 403): фронт через
Vercel CLI (`vercel deploy --prod`, alias `quip.ink`), воркер через `modal deploy`.
- **Баг 1 — Wide→Auto убивал слежение за лицом (коммит `d1192c9`, `ClipEditorScreen.handleFrameApply`):**
  таб «Кадр» для всего клипа ставил override, но НЕ перечитывал reframe-план (в отличие от
  `handleApplyRange`). При `mode:auto` бэк снимает override (`clear_crop_overrides`), а фронт продолжал
  показывать застрявший «всё wide» → слежение пропадало. Фикс: `void loadReframe()` после применения
  (зеркалит range-путь). dep-array += `loadReframe`.
- **Баг 2 — не выбирался видеофайл, без ошибки в консоли (коммит `364be42`, `lib/videoFile.ts`+тест,
  `SourceForm`):** браузер отдаёт пустой MIME для части контейнеров (.mkv/.mov/.webm/.avi) → старая
  проверка `type.startsWith("video/")` молча отклоняла реальное видео, а `accept="video/*"` гасил их в
  системном диалоге. Фикс: чистый `isAcceptedVideoFile(name, type)` (MIME ИЛИ расширение при пустом MIME)
  + расширен `accept` явными расширениями. TDD: 4 юнит-теста.
- **Баг 3 — переход в wide показывал «секунду неправильный кадр» (коммит `61fb213`, `PreviewPlayer`):**
  корень НЕ в кадровой сетке (инвариант цел, `-1`-фикс на месте, единственная crop-CSS-анимация = 300мс
  → «секунда» физически не может быть анимацией = протухший ДЕКОДИРОВАННЫЙ кадр). Блюр-фон (`auxARef`,
  object-contain полосы 9:16) был СМОНТИРОВАН во всех режимах кроме split, но синкался по времени ТОЛЬКО
  в fit. В fill стоял на паузе на старом кадре → на переходе fill→fit его раскрывали на протухшем кадре
  + слепой сик большого источника ~1с. Фикс: держим `currentTime` фона за мастером ВСЕГДА пока смонтирован
  (в fill — пауза, но decoded-on-frame; играет только в fit) → раскрытие мгновенно на правильном кадре.
  Найдено как баг ПРЕВЬЮ (не рендера) — подтверждено фаундером.
- **Баг 4 — несколько людей (2+ разнесённых лица) кропились в одного, не уходили в wide (коммит `b17d509`,
  был не задеплоен):** правка пер-шот MODE-логики (не границ) — задеплоен на Modal.
- Остаточный микро-артефакт wide→tight (~250мс лаг режима из-за частоты `timeupdate` ~4Гц + 300мс
  object-position пан) НЕ трогали: убрать = 60Гц ре-рендеры тяжёлого дерева редактора (есть perf-риск),
  а доминирующую «секунду» убил фикс фона. Если будет мешать — отдельный заход.

### 2026-06-23 — 🎨 РЕДИЗАЙН UI/UX «приборный язык» + фикс рамки субтитров (ветка `editor-snapping`; уехало на прод 2026-06-23 вместе с фикс-свипом выше — фиксы лежат коммитами ПОВЕРХ редизайна на одной ветке, отдельно не отделить без cherry-pick)
Ночная сессия: полная переработка ДИЗАЙНА (палитра и функционал НЕ тронуты). Бриф/vision —
`docs/REDESIGN_VISION_2026-06-23.md`. Оркестрация: read-only аудит 6 доменов (воркфлоу) → синтез →
параллельные Opus-форки по непересекающимся доменам. Гейт зелёный перед каждым коммитом.
- **Фундамент (коммит `eb35133`):** вынесены общие примитивы `components/ui/` — `Stat` (сигнатурный
  score-readout: mono-число + Eyebrow + Meter), `Eyebrow`, `Numeral`, `Meter`, `Badge`, `Skeleton`,
  `Spinner`, `EmptyState`, `Split` (асимметричный rail+canvas); `Container` (default/wide/prose),
  `Section` (tight/default/loose), `SectionHeading` (mono-индекс). Починен «разброс коралла»:
  Switch/Checkbox «вкл» = ink (не коралл), фокус Input = line-strong, Card += selected (кольцо).
- **Сигнатура:** confidence-score = повторяющийся герой каждой поверхности через `Stat`; mono-цифры =
  язык данных; **score = `ok`/зелёный** (коралл остаётся скуп — только CTA/live), выбор = кольцо+чекбокс,
  hairline-панели вместо плавающих карточек, асимметрия вместо центрированных стопок.
- **Редизайн (коммит `8556a8a`):** дашборд idle = приборная консоль (9:16-intake с угловыми засечками,
  mono-спека, USAGE-readout + RECENT-ledger + slim REDEEM); результаты = masthead-вердикт + mono-полоса,
  ClipCard со score-героем; VideoMap без эмодзи; CoWatch off-palette sky/emerald/amber → токены;
  JobProgress timeline-spine + телеметрия; ErrorPanel без `<pre>`. Лендинг: удалён фиолетовый AI-glow,
  Craft 2×2 icon-сетка → реальный 9:16-артефакт, mono-индексы секций, score-герой в Hero/FinalCta,
  mono-цены. Аккаунт = асимметричная ledger-квитанция. (`momentKinds.ts` raw-rgba → токены.)
- **Фикс рамки субтитров/хука (коммит `ee44d03`, `editor/OverlaySelectionBox`+`ClipEditorScreen`):**
  корень (найден живой инструментацией геометрии) — рамка хугает per-frame union-bbox libass, а коммит
  трактуется как ЯКОРЬ текста; union-bbox ≠ якорь (метрика/плашка/караоке) → телепорт текста/рамки на
  отпускании. Фикс: move коммитит `текущий_якорь + Δрамки` (офсет инвариантен при переносе → bbox
  садится ровно в точку отпускания); resize скейлит вокруг ИСТИННОГО якоря (pos), не кромки bbox.
  Проверено вживую: move-прыжок ~0px (было 5px+), resize позиция/ширина зафиксированы.
- **Редактор (визуальный редизайн):** отдельным Opus-форком (strict visual-only; drag/render/геометрия
  canvas read-only). [в процессе на момент записи]

### 2026-06-22 — 🎯 БОЛЬШОЙ СВИП РЕДАКТОРА: 7 доменов (коммиты 7dc4f5b…fcba7f2) — ЗАДЕПЛОЕНО
Семь продуктовых направлений по фидбэку фаундера, оркестрация параллельными саб-агентами (форками),
все через зелёный `just check`, задеплоено в обход GitHub (Vercel CLI + Modal CLI). Ветка
`editor-snapping`.
- **Д3 — нижний таймлайн (`TimelineV2`/`ClipEditorScreen`):** live-seek как в CapCut (превью сикается
  на границу клипа во время драга/ресайза, `onScrub`+rAF-троттл, без round-trip), реальный плейхед по
  `nowSec`, богатый тултип момента (тип + «% match» + хук + «почему сработает» + CTA «перенести клип
  сюда»). Бэк: `TimelineSegment` += `hook`/`why_works` (`models.py`/`editor/timeline.py`, codegen).
- **Д1 — пер-шот кадрирование:** фронт — `FitTimeline` показывает РЕАЛЬНЫЕ шоты (не равные куски),
  номера/режимы/подсветка активного, честные состояния `ai`/`manual`/`loading` (фейк-фолбэк больше не
  маскируется под шоты). Бэк — персист реальных границ сцен (миграция **0013** `job_artifacts.reframe_regions`
  + merge-RPC): `/reframe` для дефолтного интервала отдаёт их мгновенно (без тяжёлого CV), 503 вместо
  немого 500. Инвариант кадровой сетки Δ=0 цел.
- **Д2 — табы 6→4 (Agent/Subtitles/Hook/Frame):** `Captions`+`Style` слиты в `SubtitlesTab` (текст
  сверху, стиль снизу), `Shots` ушёл внутрь `Frame`. Убрана путаница «Style vs Hook». (Фикс вёрстки:
  `SubtitlesTab` не должен дублировать flex-1/min-h-0 скролл — `Inspector` уже скроллит → иначе пресеты
  наезжали на список реплик.)
- **Д4 — супер-агент (`agent/tools.py`, `clip_agent.py`, промпт):** +9 тулзов — монтаж (`trim_words`/
  `add_section`/`extend_edge`), стиль (`set_caption_style`/`set_hook_style`/`apply_preset`/`list_presets`),
  кадр (`set_crop`/`set_aspect`); `get_clip_state` теперь видит стиль/хук/aspect/burn + слова с глоб.
  индексами. Фронт менять не пришлось (`AgentTab` рендерит действия дженерик). models.py не тронут.
- **Д6 — VideoMap:** ценностный посыл («Video map — why these clips are worth it» + «N chapters · M key
  moments · K clips cut from them»), врезка «мы прочитали ВСЁ видео…», счётчики моментов/клипов в главах,
  ETA в pending.
- **Д7 — процессинг/дашборд:** живые статусы в `RecentProjects` (poll getJob, StatusBadge:
  Processing→New·N clips→✓), прогресс-бар в `JobProgress`, reassurance «можно закрыть таб», флаг
  `reviewed` (готово-но-не-проверено). Долговечность джобы (Modal+Postgres) уже была — сделали видимой.
- **Д5 — память настроек (миграция 0014 `profiles.style_preferences`, `editor/style_prefs.py`):** три
  уровня стиля — на клип (было) → на видео («Apply to all clips», `/jobs/{id}/apply-style-all`) → на все
  будущие видео («Save as my default», `/me/style-preference` → `ensure_edit` сидит новый клип стилем
  юзера вместо `preset_a`). models.py не тронут.
- **Оркестрация:** домены с общим центральным файлом (`ClipEditorScreen`) делались последовательно;
  изолированные — параллельными форками с РАЗДЕЛЕНИЕМ ПО ГЕЙТАМ (worker mypy/pytest ‖ web tsc — не
  мешают; два web-форка — мешают). Коммиты сериализованы (pre-commit `just check` глобален). Миграции
  0013/0014 применены на прод ДО деплоя воркера.

### 2026-06-22 — ⚠️ ДЕПЛОЙ В ОБХОД GITHUB (аккаунт `Varenik-vkusny` ЗАБАНЕН) + `.vercelignore`
**Большая инфра-реальность сессии.** GitHub-аккаунт `Varenik-vkusny` **SUSPENDED** → `git push`
возвращает **403** → штатный флоу (push в `main` → авто-деплой Vercel) **МЁРТВ**. Фаундер написал в
GitHub support, ждём реабилитации. ВСЁ из этой сессии задеплоено в ПРОД **в обход GitHub**:
- **Фронт:** `vercel deploy --prod --scope timurkas-projects` (Vercel CLI напрямую). Проект =
  `timurkas-projects/quip-app`.
- **Воркер:** `modal deploy deploy/modal/worker.py` (Modal CLI, как обычно).
- **`.vercelignore` (коммит f7b3f23):** голый CLI-деплой заливал **1.9 ГБ** и упирался в лимит
  Vercel **100 МБ/файл** → добавлен `.vercelignore`, чтобы CLI грузил только контекст фронт-сборки.
- ⚠️⚠️ **КРИТИЧЕСКИЙ КАВЕАТ:** прод сейчас крутит **CLI-деплои ветки `editor-snapping`**; в `main`
  ЭТИХ 8 КОММИТОВ НЕТ. Когда GitHub реабилитируют — **ОБЯЗАТЕЛЬНО смёрджить `editor-snapping` →
  `main`**, иначе следующая push-to-main сборка Vercel пересоберёт СТАРЫЙ код и **ОТКАТИТ всё это**.
- CORS-allowlist воркера (для локалки): `quip.ink`, `*.vercel.app`, `http://localhost:3000` ТОЛЬКО
  (не :3007) → локальный редактор должен крутиться на **:3000**, чтобы общаться с воркером.

### 2026-06-22 — Лендинг-демо: 44с реального пайплайна из экранки фаундера
Собрано демо-видео для лендинга из СОБСТВЕННОЙ экранной записи фаундера (реальный флоу: лендинг →
загрузка + Make clips → AI читает видео с чипами-моментами → клипы появляются → грид/просмотр →
открытие клипа → редактор → клип играет). Выход: `apps/web/public/demo/quip-demo-pipeline.{mp4,webm}`
+ `-poster.jpg`. ⚠️ `<video>` ЕЩЁ НЕ вшит в hero лендинга (сниппет готов; фаундер может захотеть
вшить в следующую сессию). Оригинал записи фаундера НЕ трогали.

### 2026-06-22 — Вкладка «Shots» + фолбэк ручного кадрирования (коммиты 7c4508f, 0132d72) — ЗАДЕПЛОЕНО
Пер-шот реврейм (`FitTimeline`) был закопан внизу вкладки Frame → вынесен в ОТДЕЛЬНУЮ вкладку рейла
«Shots» (clapperboard, клавиша 6; коммит `7c4508f`). Файлы: `EditorRail.tsx`, `ClipEditorScreen.tsx`.
**Баг, найденный при проверке:** полоса рисовалась ТОЛЬКО из `rawRegions` (AI-шоты от `GET /reframe`).
А `/reframe` гоняет тяжёлый CV на лету (PySceneDetect + ASD/torch) и на «холодном» клипе медленный/
падает → `loadReframe` глотает в `setRawRegions(null)` → мёртвая плашка «Framing follows AI» и НОЛЬ
контроля — ровно когда юзер пришёл поправить кадр. Фикс (`0132d72`, фронт-only): override-путь
(`handleApplyRange` → `reframe_overrides`) НЕ зависит от AI-плана (применяется на рендере + в превью),
поэтому при отсутствии AI-шотов режем клип на ровные временны́е чанки → юзер ВСЕГДА может выделить
момент и форснуть Wide/Tight/Auto. Есть AI-план → реальные границы шотов, как раньше.
**Задеплоено в прод 2026-06-22 (Vercel CLI), live на quip.ink.**

### 2026-06-22 — Cost guard: НЕ используем Gemini 3 (-latest уехал на 3.5) + фидбек скачивания
- **Gemini 3 молча использовался (×10 цена).** Тест-запрос к API: `gemini-flash-latest` сейчас
  резолвится в **`gemini-3.5-flash`** (HTTP 200, ключ рабочий). А `LLM_MODEL` (прод-секрет + локальный
  .env) и фолбэк-цепочка агента (`_AGENT_FALLBACK_MODELS`) были = `gemini-flash-latest` → весь пайплайн
  (select/хуки/главы/video-map/агент) шёл на Gemini 3. Код-дефолт был запинен (2.5-flash), но секрет
  перебивал. Фикс: (1) `config.pin_llm_model` (field_validator) — любой `*-latest`/`gemini-3*` коэрсится
  в `gemini-2.5-flash` с логом (НЕ тихо) → ГАРАНТИЯ даже без смены секрета; (2) `_AGENT_FALLBACK_MODELS`
  → `("gemini-2.5-flash","gemini-2.5-flash-lite")` (убрал -latest); (3) локальный .env LLM_MODEL →
  2.5-flash; +гард-тест `test_config_llm_guard.py`. ⚠️ Рекомендация: обновить и Modal-секрет LLM_MODEL
  на `gemini-2.5-flash` (хотя guard уже коэрсит). **Нужен modal deploy.**
- **Скачивание клипа «висло» без фидбека.** On-demand экспорт (`export/captioned.mp4` / `clean.mp4`)
  рендерится на лету (десятки сек), а были голые `<a download>` → пока сервер рендерит, НИЧЕГО, юзер
  кликал по 3 раза. Фикс (`ExportMenu`): клик качает через `fetch`+blob, показывает спиннер
  «Preparing your clip…» и блокирует пункт; фолбэк на прямую ссылку при CORS/ошибке. Baked-CDN-рендер
  (мгновенный) остаётся нативным `<a>`. Vercel-only.

### 2026-06-22 — Poppins не прожигался + ресайз: текст прыгал ВНУТРИ рамки
Два бага, найдены live-репро + чтением кода (без саб-агента — нужна live-итерация).
- **Poppins не попадал в рендер (превью верное, экспорт — нет).** `PoppinsBlack.ttf` нёс family
  (name ID 1) = **«Poppins Black»**, а ASS просит **«Poppins»** → libass/ffmpeg на ЭКСПОРТЕ не матчат
  → фолбэк. Превью (libass-wasm) матчит типографское имя (ID 16=«Poppins») и баг прячет. Остальные 8
  шрифтов ОК (ID 1 == UI-имя). Фикс: нормализовал name-таблицу Poppins (ID 1/4/16 → «Poppins») в ОБОИХ
  каталогах (`services/worker/fonts` + `apps/web/public/libass/fonts`) — глифы не трогали. +гард-тест
  `tests/unit/test_fonts.py` (ID 1 каждого TTF == UI-family) — ловит класс на будущее. **Нужен
  modal deploy** (шрифт в образе рендера).
- **Ресайз хука/субтитров: текст прыгал ВНУТРИ рамки.** `onHandleUp` снимал scale с РАМКИ сразу
  (`node.style.transform=""`), но scale КАНВАСА держался до reconcile → кадр «рамка старого (мал.)
  размера, текст нового (бол.)» → текст «прыгает в рамке». Фикс: НЕ снимаем box-transform на release —
  рамка и текст держат scale ВМЕСТЕ и сбрасывают вместе. Плюс handoff теперь по ПРЕДИКАТУ
  (`reconcileMatchRef`): чистим трансформ, только когда libass-bbox реально достиг таргета (новый
  pos/размер), а не на первом stale-кадре (иначе снэп). MOVE — предикат по центру/краю, RESIZE — по
  высоте bbox ≈ target. `just check` зелёный.

### 2026-06-22 — Он-видео драг: текст хука/субтитров теперь едет ВМЕСТЕ с рамкой (без рывка)
Фидбек: при перетаскивании рамки хука/субтитров текст «дёргается» — рамка едет, а libass-текст стоит,
и на отпускании текст ТЕЛЕПОРТИТСЯ к рамке (замер: тащим рамку вниз 150px → текст стоит на ~115, на
release прыгает на ~259). Причина: `OverlaySelectionBox` во время жеста двигает ТОЛЬКО рамку
императивно (zero-re-render), а libass-текст — отдельный `<canvas>`, обновляется лишь на commit.
Фикс (фронт-only, Opus-агент): `LibassLayer` тегает канвасы `data-libass-part="hook|caption"`;
`OverlaySelectionBox` во время MOVE накладывает `translate`, во время RESIZE — `scale` (с тем же
origin) на СООТВЕТСТВУЮЩИЙ канвас → текст едет 1:1 с рамкой, снэппинг включён. Трансформ НЕ снимается
сразу на pointerup (иначе кадр flash-back на старую позицию), а держится до следующего `rect`
(libass-bbox отразил новый `\pos`) — бесшовный хэндофф (+400мс safety-timeout, очистка на новом жесте/
unmount). WIDTH (реврап) не трогаем — `scaleX` искажал бы глифы (текст догоняет на commit, как было).
WYSIWYG цел (pos/size-семантика не менялась). `just check` зелёный (44 vitest, tsc/eslint).

### 2026-06-22 — Фикс-пачка: шрифт хука на рендере, прыжки карточек, float-время (параллельные саб-агенты)
Три прод-бага, найдены/пофикшены двумя параллельными Opus-саб-агентами (строгие границы файлов),
интеграция + `just check` + деплой — оркестратором.
- **Шрифт хука не попадал в итоговый рендер (НЕ кэш и НЕ воркер — фронт-гонка).** Правки субтитров/хука
  (вкл. `hook.font`) персистятся через **дебаунс ~300мс** (`editCaptions`→`scheduleFlush`, регрессия из
  `98ffa63`). `handleRender` дёргал `startRenderClip` **без `await flushPending()`** → воркер рендерил
  СТАРЫЙ шрифт (все прочие version-bump операции — trim/crop/aspect/preset — флашат, рендер был
  единственным исключением). Фикс: `handleRender` теперь флашит pending перед рендером. Второй режим
  («скачал без ре-рендера»): `bakedUrl` (снапшот CDN-рендера) не инвалидировался после правки →
  `ExportMenu` отдавал устаревший прожиг (дефолт-шрифт Unbounded). Фикс: pure `captionedDownloadUrl(...,
  dirty)` — при `dirty`/без baked качаем on-demand `export/captioned.mp4` (свежий прожиг текущего
  edit-state, без CDN-ключа). Воркер (`build_hook_event`) корректен — добавлен guard-тест. Фронт-only,
  деплой воркера НЕ нужен.
- **Карточки клипов «прыгали».** Разная длина «why it works»/цитаты → разная высота → кнопка
  Render/«Rendering…»/Download на разной высоте по карточкам. Фикс (`ClipCard`, layout-only): тело
  `flex-1`, `line-clamp-2/3/2` на хук/why/цитату, `mt-auto` на оба футер-варианта → кнопка прибита к низу
  и выровнена по всем карточкам (грид и так `align-items:stretch`).
- **Float-шум во времени обработки.** `CoWatch` печатал `elapsed % 60` без округления → `3:21.751000000000005`.
  Фикс: общий хелпер `mmss()` (`lib/format.ts`, round + finite-guard) + регрессионный тест.
- **Верификация:** `just check` зелёный (**819 pytest, 44 vitest** вкл. 9 новых, tsc/eslint/mypy/ruff,
  anti-drift). Живой смок прожига шрифта — после деплоя.

### 2026-06-22 — Субтитры fit-to-frame + убрана safe-area, выравнивание всегда вкл (ветка `editor-snapping`)
Фидбек фаундера по редактору: (1) размер субтитров «прыгает» с текстом и **вылезает за рамку**,
которую ставишь ручкой — нужно, чтобы текст НЕ превышал рамку, сколько бы слов ни выскочило (лучше
сам кегль уменьшался); (2) убрать плашку safe-zone соц-сетей и сделать выравнивание дефолтом без
тумблера; (3) фронт-мусор (слайдеры/оверлеи). Сделано:
- **Авто-фит субтитров (ОДИН стабильный кегль на клип).** Новый pure-модуль `apps/web/lib/captionFit.ts`
  (`wrapGreedy` + `fitCaptionSize`, **TDD, 10 тестов**): подбирает наибольший кегль, при котором КАЖДАЯ
  страница субтитров влезает в рамку (ширина блока × вертикальный бюджет). Браузер-glue
  `captionFitBrowser.ts` меряет текст реальным `<canvas>` тем же шрифтом (как у libass) + safety-margin
  0.92 (никогда не переполняет в экспорте). Кегль, заданный ручкой/слайдером — это ПОТОЛОК; реальный
  контроль = ширина рамки (шире ⇒ крупнее, у́же ⇒ мельче). Реализовано БЕЗ изменения контракта/воркера:
  пишем результат в `style.size`, который рендер (`captions_v2.compile_ass`) и так чтит буквально →
  CSS-оверлей, libass-превью и ffmpeg-экспорт совпадают сами. Триггеры рефита: угол/бок рамки, слайдер
  Size, правка текста реплики (`ClipEditorScreen.refitCaption`). Известное ограничение v1: сама рамка
  (height/width) не персистится — кегль остаётся, но хэндлы заново обнимают текст после релоада
  (fast-follow: опц. поле `fit_height` + деплой воркера).
- **Убраны safe-area + тумблер snapping.** Удалены `SafeAreaOverlay`, `SnapControls`, `lib/safeAreas.*`,
  `lib/editorPrefs.*`; снято `safeInsets`/`safePlatform`-обвязка и чип «Off·TikTok·Reels·Shorts» поверх
  клипа. Snapping/выравнивание = жёсткий дефолт `true` без UI-тумблера; `SnapGuides` (магнит-линии)
  остаются (центр/края/второй элемент). `buildTargets` потерял `safe`-параметр.
- **Фикс слайдера-внахлёст.** `.range-touch`-ползунок = 20px, а «Show duration» (HookTab) и crop-слайдер
  (FrameTab) клали голый `<input range-touch h-1.5>` сразу под лейблом (`gap-1`=4px) → 20px-thumb лез в
  текст лейбла. HookTab → переведён на общий `DebouncedSlider` (как Size/Position), FrameTab → input в
  `flex h-9 items-center`+`w-full` (центрирует thumb, как DebouncedSlider). Прочие range — плееры/таймлайн
  (full-width seek, лейбла сверху нет) — не трогаем.
- **Верификация:** `just check` зелёный (mypy 50 файлов, **818 pytest**, **35 vitest** вкл. 10 captionFit,
  ruff/tsc/eslint, anti-drift без диффа). ⚠️ Авторизованный визуал ветки заблокирован (OAuth-redirect
  завязан на прод-домен; перенос сессии на localhost справедливо отклонён сейф-классификатором) →
  финальный визуальный смок делает фаундер на Vercel-preview / залогиненном localhost.

### 2026-06-20 — Редактор «Fixed Studio» (WS-A): новый shell + фикс framing-бага
Оверхол IA/лэйаута редактора на ветке `editor-fixed-studio` (не смёрджено, не задеплоено).
Закрыто в коммитах `b5f2d24`…`cadf14d`. Ключевые изменения: Fixed-Studio shell — левый icon-rail
(Agent/Captions/Hook/Style/Frame) + центральный canvas + правый contextual inspector; canvas
вынесен в стабильный регион (размер определяется viewport'ом, а не содержимым панели) → **фикс
P0-бага «Frame-панель уменьшает видео»**; in-page переключение клипов без ремаунта + prefetch
соседних клипов; live Frame mode (без явного Apply); de-overload Hook-инспектора; FitTimeline
перенесён в Frame-контекст; сгруппированная Style-панель + preset grid (caption + hook); английские
имена пресетов; `isascii`-тест (818 ✓); vitest-харнесс в `just check`. Три user-dogfood фикса
сложены: aspect-contain CSS (FIX-A), preset grid (FIX-B), hook preset grid (FIX-C). Perf:
стабилизация `frame`-identity, мемоизованный inspector. 21 unit-тест на pure-логику.

### 2026-06-20 — Co-watch / live moment discovery (видео играет + моменты всплывают при обработке)
Фаундер: ранняя нарратив-лента (Part 3) слишком текстовая → хочет визуальный «со-просмотр». Решение +
**ГЕЙТ КАЧЕСТВА:** маркеры моментов — ЧИСТО КОСМЕТИЧЕСКИ, из отдельной pure-эвристики
(`pipeline/preview_moments.py`: транскрипт-сигналы `?`/`!`/цифра/пауза + аудио-энергия RMS), и
**НИКОГДА не передаются в `select_segments`** → AI-нарезка байт-в-байт та же, качество не меняется
(по правилу фаундера «не влияет на качество → делаем сложную живую версию»). Каждый маркер несёт
РЕАЛЬНУЮ фразу транскрипта (`PreviewMoment.text`). Энергетические маркеры считаются РАНО (после
download, до transcribe) → покрывают самый длинный кусок ожидания; best-effort (сбой extract→[], пайплайн
цел). Персист в `job_artifacts.preview_moments` (миграция 0012), `GET /jobs/{id}/preview-moments`.
Фронт: `CoWatch.tsx` — **v2 после фидбэка** («бар = neiroslop, глаз скачет точка↔линия»): убрали
абстрактный бар, реальную пойманную строку показываем чипом-цитатой ПОВЕРХ видео (фраза + тег), всплывают
по одному (labor illusion). Источник видео = локальный File (object URL, мгновенно, без CORS).
Graceful handoff на грид клипов как только клипы есть. `/dev/cowatch` — харнесс для визуальной проверки.
Ветка `feat/live-moment-discovery` → merge `3773c9f`, `just check` зелёный (817), задеплоено.

### 2026-06-20 — Баг «правки хука (размер) не применяются на рендере» = CDN edge-cache, не ASS
Корень (не угадан — трассировка + тесты): размер хука корректно доходит до ASS (`build_hook_event`
кладёт `hook.size` в Style-строку; PATCH персистит; рендер каждый раз пересобирает ASS, кэша по
размеру нет). Реальная причина — `storage.upload_clip` перезаписывает ТОТ ЖЕ R2-ключ
`{job}/{clip}_captioned.mp4` и отдаёт стабильный CDN-URL (`cdn.quip.ink`), а Cloudflare edge-кэширует
mp4 БЕЗ `Cache-Control` → ре-рендер пишет в origin, но Download тянет СТАРЫЙ закэшированный объект.
Бьёт ЛЮБУЮ правку после первого рендера; размер хука — самое заметное. Фикс (defense-in-depth,
только экспорт/кэш — кадровая сетка не тронута): (1) `Cache-Control: no-cache` на заливке
(`clip_upload_extra_args`); (2) cache-buster `?v=<clip_edit.version>` на render-URL
(`storage.with_cache_bust`, версия растёт на каждый PATCH → гарантированный CDN-miss даже при
Cloudflare «cache everything»). TDD: 13 тестов test_storage.py.

### 2026-06-20 — Качество рендера по плану + «живая лента клипов» до рендера
- **Качество рендера привязано к плану.** Финальный энкод был захардкожен `-preset veryfast
  -crf 20` для ВСЕХ планов (3 точки в stage5_render) → Pro получал то же мыло, что free, только
  1080 вместо 720. Теперь качество — часть серверной `RenderPolicy` (необойдабельно с клиента):
  `PlanLimits.video_crf/video_preset` → free 20/veryfast, платные **18/medium** (чётче на том же
  1080). Протянул crf/preset через `render_clip` + `render_timeline` (пайплайн И редактор) общим
  `_video_out_args`. Только энкод — кадровая сетка (Δ=0) не тронута. TDD на resolve_render_policy.
- **Live Clip Feed (оверхол ожидания до рендера).** Раньше юзер пялился в статичный степпер
  минуты, клипы появлялись ТОЛЬКО после рендера. Ресёрч (OpusClip/Vizard/Klap/Submagic/Descript…):
  никто не стримит метаданные клипов до рендера, «почему клип» — всегда на странице результатов.
  Наш конвейер УЖЕ персистит метаданные (хук/why/score/интервал) — просто поздно. Спека+план:
  `docs/superpowers/{specs,plans}/2026-06-20-live-clip-feed*`.
  - **W1:** `set_clips_pending` зовём СРАЗУ после select (status=selecting, progress 60), а не на
    границе рендера (80) → богатые карточки встают на ~60%, за минуты до видео (фронт уже свопит
    степпер на грид по наличию клипов). Порядок сохранён (idx фан-аута выровнен; regression-тест).
  - **F2/F3:** `PendingThumb` — client-side frame-grab кадра из preview-прокси в «Rendering…»-бокс
    (НЕ crossOrigin: CDN без CORS-заголовков → иначе видео не грузится; рисуем tainted canvas,
    пиксели не читаем); карточки «всплывают» + счёт скора 0→N (respects reduced-motion).
  - **W2/F1 + миграция 0011:** счётчики `source_minutes/transcript_words/moments_found` (nullable)
    наполняются по стадиям (`db.set_progress_detail`, best-effort — косметика не валит рендер),
    `JobProgress` показывает «· 412 words / · 9 found» в окне 0–60%.
  - Проверено вживую: новая джоба → 4 богатые карточки (хук+why+score 0.92) на «0 of 4 ready»,
    ДО рендера. Баг с CORS-превью на превью-картинке пойман на живой проверке и пофикшен.

### 2026-06-19 — Оверхол манипуляции хуком/субтитрами в редакторе (драг/ресайз/ширина/отскок/скролл)
Закрыт давний фейл-класс (чинилось ~5 раз вслепую — редактор под auth, мок не показывал). Все
интерактивные баги воспроизведены и проверены в ЖИВОМ редакторе (quip.ink, Playwright + куки), не
гадая. Что сделано:
- **#5 «шрифт отскакивает»** — НЕ серверный (PATCH/getClipAss отдают новый шрифт корректно, проверено
  по сети). Корень: гонка реконсиляции в `ClipEditorScreen.tsx` — `refreshAss`, начатый ДО новой
  оптимистичной правки, резолвился ПОСЛЕ и перетирал свежий `patchAssStyles` старым серверным ASS
  (self-heal на следующем flush → «поменяй ещё раз»). Фикс: счётчик `optGenRef` (бампится в
  `editCaptions`) — `refreshAss` пропускает `setAssText`, если пришла более новая оптимистичная правка.
  Примитив-ref, не передаём ref-объекты в setState → не злим React-Compiler `immutability`.
- **#2/#3 свободный X/Y + ширина блока** (кросс-стек): в `models.py` добавлены `pos_x`/`pos_y`/
  `wrap_width` (доли, None=легаси-центр; codegen `just types`). Рендер в `captions_v2.py` через
  `\pos(x,y)\anN` + симметричные `MarginL/MarginR` (libass переносит текст внутри ширины — шрифт не
  меняется). Зеркало в `assStyle.ts` (Style-маржины + инъекция `\pos` в Dialogue для инстант-превью).
  Семантика: `pos_x`=центр-X, `pos_y`=якорная грань (caption низ `\an2` / hook верх `\an8`).
  WYSIWYG: превью (libass-wasm) == экспорт (ffmpeg) — один ASS; спайк подтвердил, что под `\pos`
  ширина wrap'а реально задаётся MarginL/R (не косметика). 16 unit-тестов (TDD, агент Opus 4.8).
- **#1 тактильность драга** — `OverlaySelectionBox.tsx` переписан: тело = свободный move X+Y
  (1:1, pointer-capture, императивно без ререндера), угол = размер шрифта, БОКОВЫЕ ручки = ширина
  блока. Чётче/крупнее ручки.
- **#6 лента пресетов не листалась колесом** — хук `useWheelHscroll` (non-passive `wheel`,
  deltaY→scrollLeft) на `PresetStrip` и галерее хук-пресетов в `HookTab`.

## Р–СѓСЂРЅР°Р» РїСЂРѕРіСЂРµСЃСЃР° (Р§РРўРђРўР¬ РџР•Р Р’Р«Рњ РІ РЅРѕРІРѕР№ СЃРµСЃСЃРёРё)

### РЎРѕСЃС‚РѕСЏРЅРёРµ СЃСЂРµРґС‹ (Windows 11, РїСЂРѕРІРµСЂРµРЅРѕ 2026-06-07)
- РЈР¶Рµ СЃС‚РѕСЏС‚: `node` 22.19.0, `pnpm` 10.29.2, `git` 2.49.0, `gh` 2.92.0,
  `python` 3.12.10, `winget` 1.28.
- A1 РґРѕСЃС‚Р°РІРёР»: `ffmpeg` 8.1.1 (Gyan build), `uv` 0.11.19, `just` 1.51.0.

### Р“СЂР°Р±Р»Рё РёРЅСЃС‚СЂСѓРјРµРЅС‚РѕРІ Р°РіРµРЅС‚Р° (РІР°Р¶РЅРѕ РґР»СЏ СЃРєРѕСЂРѕСЃС‚Рё)
- **Bash-РёРЅСЃС‚СЂСѓРјРµРЅС‚ = РЅР°СЃС‚РѕСЏС‰РёР№ bash** (`/usr/bin/bash`), РќР• PowerShell. `Select-Object`
  Рё РїСЂ. PS-РєРѕРјР°РЅРґР»РµС‚С‹ РІ РЅС‘Рј РїР°РґР°СЋС‚. Р”Р»СЏ Windows-СЃРїРµС†РёС„РёРєРё (PATH, СЂРµРµСЃС‚СЂ, winget) вЂ”
  РёРЅСЃС‚СЂСѓРјРµРЅС‚ **PowerShell**.
- **РЎРѕСЃС‚РѕСЏРЅРёРµ shell РјРµР¶РґСѓ РІС‹Р·РѕРІР°РјРё РќР• СЃРѕС…СЂР°РЅСЏРµС‚СЃСЏ** (env-vars/С„СѓРЅРєС†РёРё СЃР±СЂР°СЃС‹РІР°СЋС‚СЃСЏ).
  РџРѕСЌС‚РѕРјСѓ РїРѕСЃР»Рµ СѓСЃС‚Р°РЅРѕРІРєРё Р±РёРЅР°СЂРЅРёРєР° PATH РїРѕРґС‚СЏРіРёРІР°С‚СЊ Р’ РўРћРњ Р–Р• РІС‹Р·РѕРІРµ, РіРґРµ РїСЂРѕРІРµСЂСЏРµС€СЊ:
  ```powershell
  $env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
  ```
  Р­С‚Рѕ Р·Р°РјРµРЅСЏРµС‚ В«РїРµСЂРµР·Р°РїСѓСЃС‚Рё С‚РµСЂРјРёРЅР°Р»В» РґР»СЏ С‚РµРєСѓС‰РµРіРѕ РїСЂРѕС†РµСЃСЃР°.
- **`just check` РіРµР№С‚ РїРѕСЏРІР»СЏРµС‚СЃСЏ С‚РѕР»СЊРєРѕ РІ A6** (РґРѕ СЌС‚РѕРіРѕ РЅРµС‚ justfile/С‚РµСЃС‚РѕРІ). Р‘СѓС‚СЃС‚СЂР°Рї-
  РєРѕРјРјРёС‚С‹ A3вЂ“A5 РёРґСѓС‚ Р”Рћ СЃСѓС‰РµСЃС‚РІРѕРІР°РЅРёСЏ РіРµР№С‚Р° вЂ” СЌС‚Рѕ РЅРѕСЂРјР°Р»СЊРЅРѕ Рё РїРѕ РїР»Р°РЅСѓ.
- **git identity** (РіР»РѕР±Р°Р»СЊРЅР°СЏ): name=`Varenik-vkusny`, email=`akybaevtimur7@gmail.com`
  (РќР• РґР·Р°РєРїРµР»РѕРІСЃРєРёР№ вЂ” СЌС‚Рѕ РѕСЃРѕР·РЅР°РЅРЅС‹Р№ РєРѕРЅС„РёРі С„Р°СѓРЅРґРµСЂР°, РЅРµ С‚СЂРѕРіР°СЋ).
- Р’ РєРѕСЂРЅРµ periodically РїРѕСЏРІР»СЏРµС‚СЃСЏ С‡СѓР¶РѕР№ `debug.log` (ICU-РѕС€РёР±РєРё Electron) вЂ” РѕРЅ РІ
  `.gitignore` (`*.log`), РЅРµ РєРѕРјРјРёС‚РёРј, РЅРµ СѓРґР°Р»СЏРµРј.

### РљР°С‚Р°Р»РѕРі СЂРµРїРѕ вЂ” Р Р•РЁР•РќРћ (2026-06-07)
- **РљРѕСЂРµРЅСЊ СЂРµРїРѕ = `C:\Users\user\Desktop\ClipClow`** (С‚РµРєСѓС‰Р°СЏ СЂР°Р±РѕС‡Р°СЏ РїР°РїРєР°). Р’СЃРµ РїСѓС‚Рё
  РїР»Р°РЅР° В§5 С‚СЂР°РєС‚СѓРµРј РѕС‚РЅРѕСЃРёС‚РµР»СЊРЅРѕ РЅРµС‘.
- **GitHub:** `Varenik-vkusny/clipflow` (private). `origin` СѓР¶Рµ РЅР°СЃС‚СЂРѕРµРЅ. РђРєРєР°СѓРЅС‚ `gh` =
  `Varenik-vkusny` (scopes repo/workflow).
- **PENDING (РїРѕСЃР»РµРґРЅРёРј РґРµР№СЃС‚РІРёРµРј СЃРµСЃСЃРёРё):** РїРµСЂРµРёРјРµРЅРѕРІР°С‚СЊ РїР°РїРєСѓ `ClipClow в†’ clipflow`.
  РџРћР§Р•РњРЈ РЅРµ СЃРµР№С‡Р°СЃ: С…Р°СЂРЅРµСЃСЃ РґРµСЂР¶РёС‚ cwd = `...\ClipClow`; СЂРµРЅРµР№Рј РїРѕСЃСЂРµРґРё СЃРµСЃСЃРёРё СЃР»РѕРјР°РµС‚
  РІСЃРµ РїРѕСЃР»РµРґСѓСЋС‰РёРµ РєРѕРјР°РЅРґС‹. Git/remote РїРµСЂРµР¶РёРІСѓС‚ СЂРµРЅРµР№Рј (РїСѓС‚Рё РѕС‚РЅРѕСЃРёС‚РµР»СЊРЅС‹Рµ). РџРѕСЃР»Рµ
  СЂРµРЅРµР№РјР° вЂ” РїРµСЂРµРѕС‚РєСЂС‹С‚СЊ Claude Code РЅР° `...\clipflow`.

### Р§РµРєР»РёСЃС‚ РїСЂРѕС…РѕР¶РґРµРЅРёСЏ (СЃС‚Р°РІР»СЋ [x] С‚РѕР»СЊРєРѕ РєРѕРіРґР° DoD Р·РµР»С‘РЅС‹Р№ Рё РІС‹РІРѕРґ РїРѕРєР°Р·Р°РЅ)
- [x] **A1** вЂ” ffmpeg/uv/just СѓСЃС‚Р°РЅРѕРІР»РµРЅС‹, РІРµСЂСЃРёРё РїРµС‡Р°С‚Р°СЋС‚СЃСЏ. 2026-06-07.
- [x] **A2** вЂ” `git init -b main` РІ ClipClow + `Varenik-vkusny/clipflow` (private) + origin.
      Р›РµРЅРґРёРЅРі pushedAt РЅРµ РёР·РјРµРЅРёР»СЃСЏ (2026-06-06T18:01:34Z). 2026-06-07.
- [x] **A3** вЂ” `.gitignore` + РґРµСЂРµРІРѕ В§3 + РїРµСЂРІС‹Р№ РєРѕРјРјРёС‚ `a14814e`. git status С‡РёСЃС‚С‹Р№. 2026-06-07.
- [x] **A4** вЂ” `apps/web` (Next 16, Tailwind v4, App Router) + pnpm workspace + prettier.
      `pnpm --filter web dev` в†’ :3000 РѕС‚РґР°С‘С‚ 200. РљРѕРјРјРёС‚ `1f980fd`. 2026-06-07.
- [x] **A5** вЂ” `services/worker` (uv, hatchling, РїР°РєРµС‚ `app`), `/healthz` в†’ ok.
      STOP-GATE С‡РёСЃС‚Рѕ: :3000 (200) + :8000 РѕРґРЅРѕРІСЂРµРјРµРЅРЅРѕ. РљРѕРјРјРёС‚ `3030e00`. 2026-06-07.
- [x] **A6** вЂ” `models.py` (РёСЃС‚РѕС‡РЅРёРє С‚РёРїРѕРІ, С‚РµСЃС‚-РїРµСЂРІС‹Рј) + `export_schema.py` + codegen
      `@clipflow/shared` + `justfile` + mypy strict + `.gitattributes` + pre-commit.
      `just check` Р·РµР»С‘РЅС‹Р№, `just types` РёРґРµРјРїРѕС‚РµРЅС‚РµРЅ, `pre-commit run -a` РѕРє. РљРѕРјРјРёС‚ `0079e50`. 2026-06-07.
      вњ… **Р­РўРђРџ A (Р±СѓС‚СЃС‚СЂР°Рї) Р—РђР’Р•Р РЁРЃРќ.**
- [x] **B1/B2** вЂ” Import: `app/errors.py` (JobError) + `app/pipeline/stage0_import.py`.
      pure-Р»РѕРіРёРєР° (parse_fps, build_source_meta) TDD, 21 unit-С‚РµСЃС‚. Р РµР°Р»СЊРЅС‹Р№ РїСЂРѕРіРѕРЅ
      (EDCwQe7P8T0, ~33 РјРёРЅ): mp4 1920Г—1080 РёРіСЂР°РµС‚СЃСЏ, wav pcm_s16le/16000/mono,
      meta.json (duration=1987.6, fps=23.976). DoD Р·РµР»С‘РЅС‹Р№. РљРѕРјРјРёС‚ `fe47329`. 2026-06-07.
      вљ пёЏ Р’РёРґРµРѕ-РєРѕРґРµРє source.mp4 = **AV1** (YouTube РѕС‚РґР°С‘С‚ AV1-РІ-mp4 РїСЂРё ext=mp4).
      gyan-ffmpeg РґРµРєРѕРґРёС‚ AV1 в†’ СЌС‚Р°Рї G РѕРє. Р•СЃР»Рё РЅР° G РІСЃРїР»С‹РІС‘С‚ РґРµРєРѕРґ вЂ” РґРѕР±Р°РІРёС‚СЊ
      `[vcodec^=avc1]` РІ yt-dlp format. РўРµСЃС‚РѕРІС‹Р№ СЂРѕР»РёРє РјСѓР»СЊС‚РёСЃРїРёРєРµСЂРЅС‹Р№ (Mafia show) вЂ”
      РґР»СЏ C РѕРє (СЂРµС‡СЊ РµСЃС‚СЊ), РґР»СЏ E reframe РѕР¶РёРґР°РµРјРѕ С‚СЂСѓРґРЅРµРµ (R1, РјРЅРѕРіРѕР»РёРєРёР№ РєР°РґСЂ).
- [x] **C1** вЂ” РўСЂР°РЅСЃРєСЂРёРїС†РёСЏ: `app/config.py` (pydantic-settings, fail-fast) +
      `app/pipeline/stage1_transcribe.py`. Deepgram REST `/v1/listen` С‡РµСЂРµР· httpx
      (РќР• РіРµРЅРµСЂС‘РЅС‹Р№ SDK v7). pure-РЅРѕСЂРјР°Р»РёР·Р°С‚РѕСЂ TDD + РєРѕРЅС‚СЂР°РєС‚-С‚РµСЃС‚ РЅР° СЂРµР°Р»СЊРЅРѕР№ С„РёРєСЃС‚СѓСЂРµ.
      Р РµР°Р»СЊРЅС‹Р№ РїСЂРѕРіРѕРЅ sample01: 5446 СЃР»РѕРІ, en, РІСЂРµРјРµРЅР° РІ СЃРµРєСѓРЅРґР°С… (first=30.22),
      last_end 1970.7 в‰¤ dur+0.5, cost в‰€$0.14, 51.8s. DoD Р·РµР»С‘РЅС‹Р№. 2026-06-07.
- [x] **D1/D2** вЂ” Р’С‹Р±РѕСЂ РјРѕРјРµРЅС‚РѕРІ (**Gemini**, structured output) в†’ segments.json. Р“Р›РђР’РќР«Р™ GATE.
      LLM Anthropicв†’**Gemini** (РЅРµС‚ Anthropic-РєР»СЋС‡Р°; swappable). D2 pure (clamp/snap/
      indices_to_times/resolve_overlaps/postprocess) вЂ” 19 С‚РµСЃС‚РѕРІ. D1 `select_segments` СЃ
      СЂРµС‚СЂР°СЏРјРё (R7). Р РµР°Р»СЊРЅС‹Р№ РїСЂРѕРіРѕРЅ sample01: 4вЂ“5 СЃРµРіРјРµРЅС‚РѕРІ, 15вЂ“60СЃ, Р±РµР· overlap, reason
      РљРћРќРљР Р•РўРќР«Р™, scoreв€€[0,1]. ~$0.016/РїСЂРѕРіРѕРЅ, ~39СЃ. DoD Р·РµР»С‘РЅС‹Р№. 2026-06-07.
      вљ пёЏ free-tier: **2.5-pro = РєРІРѕС‚Р° 0**, **2.5-flash С‚СЂР°РЅР·РёРµРЅС‚РЅРѕ 503** в†’ РґРµС„РѕР»С‚
      `gemini-flash-latest` (config + .env.example). РџР»Р°С‚РЅС‹Р№ С‚Р°СЂРёС„ в†’ РјРѕР¶РЅРѕ pro.
      вљ пёЏ Р’ РўР’РћРЃРњ `.env` СЃС‚РѕРёС‚ `LLM_MODEL=gemini-2.5-pro` (РёР· С€Р°Р±Р»РѕРЅР°) вЂ” РїРѕРјРµРЅСЏС‚СЊ РЅР°
      `gemini-flash-latest`, РёРЅР°С‡Рµ РїР°Р№РїР»Р°Р№РЅ 429-РёС‚.
- [x] **E1** вЂ” Reframe 9:16: `app/pipeline/stage3_reframe.py`. PURE (compute_crop_window,
      aggregate_center=РјРµРґРёР°РЅР°) вЂ” 12 С‚РµСЃС‚РѕРІ. I/O: РєР°РґСЂС‹ С‡РµСЂРµР· ffmpeg (AV1), Р»РёС†Р° MediaPipe
      **Tasks API**. Р РµР°Р»СЊРЅС‹Р№ РїСЂРѕРіРѕРЅ sample01 seg0: face_found=True, crop x=880/608Г—1080,
      9:16В±1px, РІ РіСЂР°РЅРёС†Р°С…; РїСЂРµРІСЊСЋ РїРѕРґС‚РІРµСЂРґРёР» Р»РёС†Р° РІ СЂР°РјРєРµ. DoD Р·РµР»С‘РЅС‹Р№. 2026-06-07.
      вљ пёЏ sample01 РјСѓР»СЊС‚РёСЃРїРёРєРµСЂ (R1) в†’ С€РёСЂРѕРєРёР№ РєР°РґСЂ РѕР¶РёРґР°РµРјРѕ; single-speaker РєР°РґСЂРёСЂРѕРІР°Р»СЃСЏ Р±С‹ РїР»РѕС‚РЅРµРµ.
- [x] **F1** вЂ” РЎСѓР±С‚РёС‚СЂС‹ ASS: `app/pipeline/stage4_captions.py`, РІСЃС‘ PURE вЂ” 15 С‚РµСЃС‚РѕРІ.
      `to_clip_time` (R3, t_clip=t_sourceв€’seg.start), group_words (в‰¤5, СЂР°Р·СЂС‹РІ РЅР° .?!/РїР°СѓР·Р°>0.4/
      >2.5СЃ), build_ass (Montserrat 90, РєРѕРЅС‚СѓСЂ 6, MarginV 260, .upper()). Р РµР°Р»СЊРЅС‹Р№ РїСЂРѕРіРѕРЅ
      sample01 seg0: 50 СЃР»РѕРІв†’17 СЂРµРїР»РёРє, РїРµСЂРІР°СЏ 0:00:00.00, РїРѕСЃР»РµРґРЅСЏСЏ=РґР»РёРЅР° РєР»РёРїР°. DoD Р·РµР»С‘РЅС‹Р№. 2026-06-07.
      рџ’Ў РўСЋРЅРёРЅРі-РєР°РЅРґРёРґР°С‚: РЅР° Р±С‹СЃС‚СЂРѕР№ СЂРµС‡Рё Р±С‹РІР°СЋС‚ 1-СЃР»РѕРІРЅС‹Рµ С‡Р°РЅРєРё (РјРёРЅ-СЃР»РѕРІ-РїРµСЂРµРґ-СЂР°Р·СЂС‹РІРѕРј).
- [x] **G1** вЂ” Cut+Encode: `app/pipeline/stage5_render.py`. PURE build_vf/build_ffmpeg_cmd вЂ”
      5 С‚РµСЃС‚РѕРІ. РћРґРёРЅ РїСЂРѕС…РѕРґ ffmpeg: -ss Р”Рћ -i (PTSв†’0, СЃРёРЅРє СЃСѓР±С‚РёС‚СЂРѕРІ R3) + -t, cropв†’scale
      1080Г—1920в†’setptsв†’subtitles, libx264 crf20/aac. Р РµР°Р»СЊРЅС‹Р№ СЂРµРЅРґРµСЂ sample01 clip_01:
      h264 1080Г—1920, aac, 20.85СЃ, 3.81СЃ СЂРµРЅРґРµСЂ. DoD Р·РµР»С‘РЅС‹Р№. 2026-06-07.
      вљ пёЏ РЎРїРѕС‚-С‡РµРє РїРѕР№РјР°Р»: `WrapStyle: 2` СЂРµР·Р°Р» РґР»РёРЅРЅС‹Рµ СЃСѓР±С‚РёС‚СЂС‹ РєСЂР°СЏРјРё в†’ РёСЃРїСЂР°РІРёР» РЅР°
      `WrapStyle: 0` (Р°РІС‚Рѕ-РїРµСЂРµРЅРѕСЃ) РІ stage4. РџСЂРµРІСЊСЋ РїРѕРґС‚РІРµСЂРґРёР»Рѕ РїРµСЂРµРЅРѕСЃ РІ 2 СЃС‚СЂРѕРєРё.
- [x] **H1** вЂ” `app/run.py` СЃРєР»РµР№РєР° Stage 0в†’5 + `job.json` (wire-РєРѕРЅС‚СЂР°РєС‚) + `runs.jsonl`.
      РљСЌС€ РїРѕ РЅР°Р»РёС‡РёСЋ (source/transcript/segments) в†’ РїРѕРІС‚РѕСЂС‹ РЅРµ РїР»Р°С‚СЏС‚ Deepgram/Gemini.
      `just e2e sample01`: 5 РєР»РёРїРѕРІ, 64СЃ, ttfc 15.4СЃ, job.json РІР°Р»РёРґРµРЅ. STOP-GATE 3 РїСЂРѕР№РґРµРЅ. 2026-06-07.
- [x] **I1/I2/I3** вЂ” РњРёРЅРёРјР°Р»СЊРЅС‹Р№ web. РџР°Р»РёС‚СЂР° **в„–1 Warm Charcoal+Coral** (РІС‹Р±СЂР°РЅР° С„Р°СѓРЅРґРµСЂРѕРј
      РёР· 4 РїСЂРµРІСЊСЋ; С‚С‘РјРЅР°СЏ, РЅРµ РґР¶РµРЅРµСЂРёРє). Tailwind v4 `@theme` (СЃРІР°Рї РїР°Р»РёС‚СЂС‹ вЂ” 1 Р±Р»РѕРє
      globals.css). РЁСЂРёС„С‚С‹ Unbounded/Onest/IBM Plex Mono. РўРёРїС‹ РёР· `@clipflow/shared`
      (`import type`, runtime-РёРјРїРѕСЂС‚Р° РЅРµС‚ в†’ transpilePackages РЅРµ РЅСѓР¶РµРЅ). lib (api/useJob
      polling 2.5СЃ/3-С„РµР№Р»Р°/effect-based, format) + РјРѕРє-РІРѕСЂРєРµСЂ (/api/mock, РїСЂРѕРіСЂРµСЃСЃ РїРѕ РІСЂРµРјРµРЅРё).
      РљРѕРјРїРѕРЅРµРЅС‚С‹: SourceForm/JobProgress(СЃС‚РµРїРїРµСЂ+С‚Р°Р№РјРµСЂ+СЃРєРµР»РµС‚РѕРЅС‹)/ClipCard/ClipGrid/
      ReasonChip/StatusBadge/ErrorPanel. page.tsx state-РјР°С€РёРЅР° idleв†’trackingв†’doneв†’error.
      `next build` Р·РµР»С‘РЅС‹Р№, `just check` Р·РµР»С‘РЅС‹Р№. РњРѕРє-С„Р»РѕСѓ idleв†’done РїСЂРѕРІРµСЂРµРЅ СЃРєСЂРёРЅС€РѕС‚Р°РјРё. 2026-06-07.
      вљ пёЏ РљРѕРЅС‚СЂР°РєС‚: `Job.clips`/`metrics`/`error` РћРџР¦РРћРќРђР›Р¬РќР« РІ TS (pydantic default в†’ РЅРµ required
      РІ JSON-СЃС…РµРјРµ) в†’ РЅР° С„СЂРѕРЅС‚Рµ `job.clips ?? []`. РЎРєРёР»Р» `ui-ux-pro-max` РёСЃРїРѕР»СЊР·РѕРІР°РЅ РґР»СЏ РЅР°РїСЂР°РІР»РµРЅРёСЏ.
- [x] **J1** вЂ” worker REST+SQLite: `app/db.py`(+pure row_to_wire, 3 С‚РµСЃС‚Р°), `app/tasks.py`
      (С„РѕРЅ+СЃС‚Р°С‚СѓСЃ), `app/main.py` (POST/GET/healthz, CORS :3000, StaticFiles /media). РљРѕРјРјРёС‚ `6fa3b46`. 2026-06-07.
- [x] **J2** вЂ” Р Р•РђР›Р¬РќР«Р™ РїСЂРѕРіРѕРЅ С‡РµСЂРµР· UI: РІСЃС‚Р°РІРёР» EDCwQe7P8T0 в†’ РїСЂРѕРіСЂРµСЃСЃ в†’ 3 Р¶РёРІС‹С… 9:16-РєР»РёРїР°
      РёР· РІРѕСЂРєРµСЂР° (/media), СЃСѓР±С‚РёС‚СЂС‹/reason/score/Download, CORS РѕРє. $0.16, 74.7СЃ. GET РёР· SQLite
      `done`/3 clips, mp4 HTTP 200. Р“Р›РђР’РќР«Р™ Р“Р•Р™Рў UI РїСЂРѕР№РґРµРЅ. 2026-06-07.
      вњ…вњ… **PHASE 0 Р—РђР’Р•Р РЁРЃРќ (Aв†’J).**
      вљ пёЏ РќР°С…РѕРґРєР°: `language="en"` Р·Р°С…Р°СЂРґРєРѕР¶РµРЅ РІ stage1. Р СѓСЃСЃРєРѕРµ/РЅРµРјРѕ-РІРёРґРµРѕ (РјРѕС‚Рѕ-С‚СЂРёРї
      l5Rzsv8qDOM) в†’ ~5 СЃР»РѕРІ в†’ 0 РєР»РёРїРѕРІ в†’ РєРѕСЂСЂРµРєС‚РЅРѕ СЃСЂР°Р±РѕС‚Р°Р» empty-state В«РќРµС‡РµРіРѕ РЅР°СЂРµР·Р°С‚СЊВ»
      (РќР• Р±Р°Рі вЂ” РЅРµРїРѕРґС…РѕРґСЏС‰РёР№ РєРѕРЅС‚РµРЅС‚). РќР° Р±СѓРґСѓС‰РµРµ: detect_language / РєРѕРЅС„РёРі СЏР·С‹РєР°; РєСЌС€
      С‚СЂР°РЅСЃРєСЂРёРїС†РёРё РїРѕ hash(source) (R6) С‡С‚РѕР±С‹ РїРѕРІС‚РѕСЂРЅС‹Рµ РїСЂРѕРіРѕРЅС‹ РЅРµ РїР»Р°С‚РёР»Рё.

> РџСЂР°РІРёР»Рѕ Р¶СѓСЂРЅР°Р»Р°: РїРѕСЃР»Рµ РљРђР–Р”РћР“Рћ Р·РµР»С‘РЅРѕРіРѕ DoD вЂ” РѕС‚РјРµС‚РёС‚СЊ [x] Р·РґРµСЃСЊ Рё РґРѕРїРёСЃР°С‚СЊ
> РѕРґРЅСѓ СЃС‚СЂРѕРєСѓ В«С‡С‚Рѕ СЃРґРµР»Р°РЅРѕ + С‡РµРј РґРѕРєР°Р·Р°РЅРѕВ». Р­С‚Рѕ РєРѕРЅС‚РµРєСЃС‚ РґР»СЏ СЃР»РµРґСѓСЋС‰РµР№ СЃРµСЃСЃРёРё.

### Р Р°СЃС…РѕР¶РґРµРЅРёСЏ РїР»Р°РЅР° СЃ СЂРµР°Р»СЊРЅРѕСЃС‚СЊСЋ (СѓС‡РµСЃС‚СЊ РЅР° Р±СѓРґСѓС‰РёС… С€Р°РіР°С…)
- **Tailwind v4** (Next 16 СЃС‚Р°РІРёС‚ v4, РЅРµ v3): РќР•Рў `tailwind.config.ts`. РљРѕРЅС„РёРі вЂ”
  С‡РµСЂРµР· CSS `@theme` РІ `apps/web/app/globals.css`. РќР° **I1** РјРѕСЃС‚ С‚РѕРєРµРЅРѕРІ Р»РµРЅРґРёРЅРіР°
  РґРµР»Р°С‚СЊ С‡РµСЂРµР· `@theme`, Р° РќР• С‡РµСЂРµР· `tailwind.config.ts`, РєР°Рє РЅР°РїРёСЃР°РЅРѕ РІ РїР»Р°РЅРµ.
- **Next.js 16** Р»РѕРјР°РµС‚ API РѕС‚РЅРѕСЃРёС‚РµР»СЊРЅРѕ РѕР±СѓС‡Р°СЋС‰РёС… РґР°РЅРЅС‹С… (СЃРј. `apps/web/AGENTS.md`).
  РџРµСЂРµРґ РЅР°РїРёСЃР°РЅРёРµРј web-РєРѕРґР° (I1вЂ“I3) С‡РёС‚Р°С‚СЊ `apps/web/node_modules/next/dist/docs/`
  РёР»Рё СЃРІРµСЂРёС‚СЊСЃСЏ С‡РµСЂРµР· context7.
- **TODO РЅР° A6:** РґРѕР±Р°РІРёС‚СЊ `.gitattributes` (`* text=auto eol=lf`, РїР»СЋСЃ СЏРІРЅС‹Р№ `eol=lf`
  РґР»СЏ `packages/shared/contract.json` Рё `src/types.ts`) вЂ” РёРЅР°С‡Рµ CRLFв†”LF РЅР° Windows
  РјРѕР¶РµС‚ Р»РѕР¶РЅРѕ СЂРѕРЅСЏС‚СЊ anti-drift `git diff --exit-code packages/shared`.
- Р’РµСЂСЃРёРё (Р·Р°С„РёРєСЃРёСЂРѕРІР°РЅРѕ A4): next 16.2.7, react 19.2.4, tailwindcss 4.3.0,
  typescript 5.9.3, eslint 9.39.4, prettier ^3.8.3.
- **Worker layout (A5):** РїР°РєРµС‚ РёРјРїРѕСЂС‚РёСЂСѓРµС‚СЃСЏ РєР°Рє `app` (РќР• src-layout). uv init РїРѕ
  СѓРјРѕР»С‡Р°РЅРёСЋ РґРµР»Р°РµС‚ `src/<name>` + Р±СЌРєРµРЅРґ `uv_build` вЂ” Р·Р°РјРµРЅРµРЅРѕ РЅР° **hatchling**
  (`[tool.hatch.build.targets.wheel] packages=["app"]`). `uv sync` СЃС‚Р°РІРёС‚ РїСЂРѕРµРєС‚
  editable в†’ `app` РёРјРїРѕСЂС‚РёСЂСѓРµС‚СЃСЏ РІРµР·РґРµ.
- **ruff config:** `select` Р¶РёРІС‘С‚ РїРѕРґ `[tool.ruff.lint]` (РЅРµ `[tool.ruff]`, РєР°Рє РІ РїР»Р°РЅРµ) вЂ”
  РёРЅР°С‡Рµ deprecation-РІР°СЂРЅРёРЅРі РІ РЅРѕРІРѕРј ruff.
- **Р“СЂР°Р±Р»Рё Next 16 dev:** `next dev` (Turbopack) РґРµСЂР¶РёС‚ РћРўР”Р•Р›Р¬РќР«Р™ СЃРµСЂРІРµСЂРЅС‹Р№ РїСЂРѕС†РµСЃСЃ +
  lock. `TaskStop` РЅР° pnpm-РѕР±С‘СЂС‚РєРµ РµРіРѕ РќР• СѓР±РёРІР°РµС‚ в†’ Р·РѕРјР±Рё РґРµСЂР¶РёС‚ :3000. Р“Р°СЃРёС‚СЊ web/worker
  РїРѕ РїРѕСЂС‚Сѓ/PID:
  ```powershell
  foreach ($port in 3000,8000) { Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select -Expand OwningProcess -Unique | % { Stop-Process -Id $_ -Force } }
  ```
- Р’РµСЂСЃРёРё РІРѕСЂРєРµСЂР° (A5): mediapipe 0.10.35, opencv-headless 4.13, numpy 2.4.6,
  fastapi 0.136.3, pydantic 2.13.4, ruff 0.15.16, mypy 2.1.0, pytest 9.0.3.

### Р“СЂР°Р±Р»Рё РёРЅСЃС‚СЂСѓРјРµРЅС‚РѕРІ (A6) вЂ” РљР РРўРР§РќРћ РґР»СЏ РєРѕРјРјРёС‚РѕРІ
- **`just` РќР• РІРёРґРµРЅ РІ Bash-РёРЅСЃС‚СЂСѓРјРµРЅС‚Рµ** (winget-С€РёРј РЅРµ РЅР° bash-PATH). Р›СЋР±РѕР№ `just`
  Р·Р°РїСѓСЃРєР°РµРј РёР· **PowerShell СЃ РѕР±РЅРѕРІР»РµРЅРёРµРј PATH РёР· СЂРµРµСЃС‚СЂР°** (СЃС‚СЂРѕРєР° РІС‹С€Рµ). Р”РѕС‡РµСЂРЅРёРµ
  recipe-С€РµР»Р»С‹ РЅР°СЃР»РµРґСѓСЋС‚ PATH в†’ uv/pnpm/git РІРЅСѓС‚СЂРё СЂРµС†РµРїС‚РѕРІ СЂРµР·РѕР»РІСЏС‚СЃСЏ.
- **pre-commit С…СѓРє СѓСЃС‚Р°РЅРѕРІР»РµРЅ** (`.git/hooks/pre-commit`) Рё РЅР° РљРђР–Р”РћРњ РєРѕРјРјРёС‚Рµ РіРѕРЅСЏРµС‚
  `just check`. Р—РЅР°С‡РёС‚ **РєРѕРјРјРёС‚РёРј РўРћР›Р¬РљРћ РёР· PowerShell** (PATH refresh), РёРЅР°С‡Рµ С…СѓРє РЅРµ
  РЅР°Р№РґС‘С‚ `just`. pre-commit Р¶РёРІС‘С‚ РІ venv: `services\worker\.venv\Scripts\pre-commit.exe`.
- **РљРѕРґРёСЂРѕРІРєР° РєРѕРјРјРёС‚-СЃРѕРѕР±С‰РµРЅРёР№:** PowerShell 5.1 РїР°Р№Рї (`$msg | git commit -F -`) Р±СЊС‘С‚
  РєРёСЂРёР»Р»РёС†Сѓ РІ `?????` + РґРѕР±Р°РІР»СЏРµС‚ BOM. РџР РђР’РР›Рћ: РїРёСЃР°С‚СЊ СЃРѕРѕР±С‰РµРЅРёРµ РІ С„Р°Р№Р» (Write-tool,
  UTF-8 Р±РµР· BOM) Рё `git commit -F <С„Р°Р№Р»>` вЂ” git С‡РёС‚Р°РµС‚ Р±Р°Р№С‚С‹ РЅР°РїСЂСЏРјСѓСЋ. РќР°РїСЂРёРјРµСЂ
  `services/worker/tmp/COMMIT_MSG.txt` (gitignored).
- **codegen-С†РµРїРѕС‡РєР° РґР»СЏ anti-drift:** title-РїРѕР»СЏ РёР· pydantic-СЃС…РµРјС‹ РЎР Р•Р—РђР®РўРЎРЇ РІ
  `export_schema.py` (`_strip_titles`) вЂ” РёРЅР°С‡Рµ json2ts РїР»РѕРґРёС‚ РјСѓСЃРѕСЂРЅС‹Рµ Р°Р»РёР°СЃС‹ Рё РєРѕР»Р»РёР·РёРё.
  РњРµРЅСЏС‚СЊ РєРѕРЅС‚СЂР°РєС‚ в†’ С‚РѕР»СЊРєРѕ `app/models.py`, РїРѕС‚РѕРј `just types`.
- Enum'С‹ РІ TS СЃС‚Р°РЅРѕРІСЏС‚СЃСЏ union-С‚РёРїР°РјРё (`type ClipType = "hook" | ...`), РЅРµ TS-enum вЂ”
  СЃРѕРІРјРµСЃС‚РёРјРѕ СЃ Next SWC `isolatedModules`.

### Р“СЂР°Р±Р»Рё РёРЅСЃС‚СЂСѓРјРµРЅС‚РѕРІ (B)
- **PowerShell-РёРЅСЃС‚СЂСѓРјРµРЅС‚ Р”Р•Р Р–РРў cwd РјРµР¶РґСѓ РІС‹Р·РѕРІР°РјРё** Рё СЃРµР№С‡Р°СЃ РѕРЅ РЅР° `services\worker`
  (РЅРµ РЅР° РєРѕСЂРЅРµ!). РћС‚РЅРѕСЃРёС‚РµР»СЊРЅС‹Рµ РїСѓС‚Рё РІ PowerShell СѓРґРІР°РёРІР°Р»РёСЃСЊ (`services\worker\services\worker\...`)
  Рё С‚РёС…Рѕ РїСЂРѕРјР°С…РёРІР°Р»РёСЃСЊ (Remove-Item В«СѓРґР°Р»РёР»В» РЅРµСЃСѓС‰РµСЃС‚РІСѓСЋС‰РµРµ в†’ Р»РѕР¶РЅРѕРµ В«removedВ»).
  РџР РђР’РР›Рћ: РІ PowerShell РІСЃРµРіРґР° **Р°Р±СЃРѕР»СЋС‚РЅС‹Рµ РїСѓС‚Рё** (РёР»Рё Set-Location РЅР° Р°Р±СЃРѕР»СЋС‚РЅС‹Р№ РїСѓС‚СЊ
  РІ РЅР°С‡Р°Р»Рµ). Bash-РёРЅСЃС‚СЂСѓРјРµРЅС‚ cwd РќР• РґРµСЂР¶РёС‚ вЂ” С‚Р°Рј `cd` РІ РєР°Р¶РґРѕР№ РєРѕРјР°РЅРґРµ.
- **ffmpeg/ffprobe РќР• РЅР° PATH Bash-РёРЅСЃС‚СЂСѓРјРµРЅС‚Р°** (winget РїРѕСЃР»Рµ СЃС‚Р°СЂС‚Р° СЃРµСЃСЃРёРё). Р›СЋР±С‹Рµ
  РїСЂРѕРіРѕРЅС‹ РїР°Р№РїР»Р°Р№РЅР°, РґС‘СЂРіР°СЋС‰РёРµ ffmpeg/ffprobe/yt-dlp, вЂ” С‡РµСЂРµР· PowerShell СЃ registry
  PATH refresh + `uv run` (РѕРЅ РїСЂРѕР±СЂР°СЃС‹РІР°РµС‚ PATH Рё venv-СЃРєСЂРёРїС‚С‹ РІ subprocess).
- Р›РёРјРёС‚ РёСЃС‚РѕС‡РЅРёРєР° 90 РјРёРЅ РІ `stage0_import._check_limits` СЂР°Р±РѕС‚Р°РµС‚ (JobError). РўРµСЃС‚РѕРІС‹Р№
  СЂРѕР»РёРє РґРѕР»Р¶РµРЅ Р±С‹С‚СЊ РІ РїСЂРµРґРµР»Р°С… Р»РёРјРёС‚Р°, РёРЅР°С‡Рµ meta.json РЅРµ РїРёС€РµС‚СЃСЏ (РіРµР№С‚ СЂР°РЅСЊС€Рµ Р·Р°РїРёСЃРё).

### Р“СЂР°Р±Р»Рё РёРЅСЃС‚СЂСѓРјРµРЅС‚РѕРІ (C)
- **`deepgram-sdk` 7.3.1 = РіРµРЅРµСЂС‘РЅС‹Р№ РєР»РёРµРЅС‚** (РєСѓС‡Р° `...V1`, Agent-API), РєР»Р°СЃСЃРёС‡РµСЃРєРѕРіРѕ
  `DeepgramClient.listen.rest` РЅРµС‚. Р РµС€РµРЅРёРµ: Р·РѕРІС‘Рј СЃС‚Р°Р±РёР»СЊРЅС‹Р№ REST `/v1/listen` С‡РµСЂРµР·
  **httpx** РЅР°РїСЂСЏРјСѓСЋ (`stage1_transcribe.call_deepgram`). РџСЂРѕРІР°Р№РґРµСЂ-Р°Р±СЃС‚СЂР°РєС†РёСЏ С†РµР»Р°,
  С„РёРєСЃС‚СѓСЂС‹ СЃРЅРёРјР°С‚СЊ РїСЂРѕС‰Рµ. deepgram-sdk РїРѕРєР° РІРёСЃРёС‚ РІ РґРµРїР°С… РЅРµРёСЃРїРѕР»СЊР·СѓРµРјС‹Рј вЂ” РјРѕР¶РЅРѕ СѓР±СЂР°С‚СЊ.
- **smart_format=true СЂР°Р·РґСѓРІР°РµС‚ РѕС‚РІРµС‚:** РґРѕР±Р°РІР»СЏРµС‚ `paragraphs`, РґСѓР±Р»РёСЂСѓСЋС‰РёРµ Р’РЎР• СЃР»РѕРІР°
  (15-СЃР»РѕРІРЅР°СЏ С„РёРєСЃС‚СѓСЂР° Р±С‹Р»Р° 225KB!). Р”Р»СЏ golden-С„РёРєСЃС‚СѓСЂС‹ РІС‹РєРёРґС‹РІР°РµРј `alt["paragraphs"]`
  Рё С‚СЂРёРјРёРј metadata в†’ 3.6KB.
- **config.py:** `.env` С‡РёС‚Р°РµС‚СЃСЏ РїРѕ РђР‘РЎРћР›Р®РўРќРћРњРЈ РїСѓС‚Рё (`parents[3]/.env`), С‚.Рє. РІРѕСЂРєРµСЂ
  РіРѕРЅСЏРµС‚СЃСЏ РёР· `services/worker` (cwd в‰  РєРѕСЂРµРЅСЊ). `get_settings()` Р»РµРЅРёРІ+РєСЌС€РёСЂРѕРІР°РЅ вЂ”
  РІР°Р»РёРґР°С†РёСЏ РєР»СЋС‡Р° РїСЂРё РїРµСЂРІРѕРј РІС‹Р·РѕРІРµ (РЅРµ РїСЂРё РёРјРїРѕСЂС‚Рµ), С‡С‚РѕР±С‹ unit-С‚РµСЃС‚С‹ Р¶РёР»Рё Р±РµР· РєР»СЋС‡РµР№.
- Deepgram Nova pre-recorded в‰€ **$0.0043/РјРёРЅ** (~$0.258/С‡Р°СЃ). РќР°С€ 33-РјРёРЅ СЂРѕР»РёРє в‰€ $0.14.
- **MediaPipe 0.10.35 РІС‹РїРёР»РёР» `mp.solutions`** (Р»РµРіР°СЃРё). РСЃРїРѕР»СЊР·СѓРµРј **Tasks API**
  (`mediapipe.tasks.python.vision.FaceDetector`), РјРѕРґРµР»СЊ `.tflite` РєР°С‡Р°РµС‚СЃСЏ РІ РєСЌС€
  `app/assets/` (gitignored `*.tflite`) РёР· storage.googleapis.com. bounding_box РІ Tasks вЂ”
  РІ РџРРљРЎР•Р›РЇРҐ (РґРµР»РёРј РЅР° С€РёСЂРёРЅСѓ РєР°РґСЂР°), Р° РЅРµ РІ РґРѕР»СЏС…, РєР°Рє Р±С‹Р»Рѕ РІ Р»РµРіР°СЃРё.
- РљР°РґСЂС‹ РґР»СЏ РґРµС‚РµРєС‚Р° Р±РµСЂС‘Рј С‡РµСЂРµР· **ffmpeg** (РґРµРєРѕРґРёС‚ AV1), РќР• `cv2.VideoCapture`
  (Р±Р°РЅРґР»-ffmpeg opencv РјРѕР¶РµС‚ РЅРµ СѓРјРµС‚СЊ AV1). mypy: overrides `ignore_missing_imports`
  РґР»СЏ `cv2`/`mediapipe` (РЅРµС‚ СЃС‚СЂРѕРіРёС… СЃС‚Р°Р±РѕРІ).
- **Р’РЅРµС€РЅРёРµ СЃРµСЂРІРёСЃС‹ Р·Р°РґРѕРєСѓРјРµРЅС‚РёСЂРѕРІР°РЅС‹:** `docs/EXTERNAL_SERVICES.md` (С‡С‚Рѕ/РіРґРµ/С‡РµРј СЃРІР°РїРЅСѓС‚СЊ).

### РџРѕСЃС‚-Phase-0 СѓР»СѓС‡С€РµРЅРёСЏ (РїРѕ Р·Р°РїСЂРѕСЃСѓ С„Р°СѓРЅРґРµСЂР°)
- **Reframe AUTO** (РїРµСЂРІС‹Р№ РІР°СЂРёР°РЅС‚): `decide_reframe_mode` + `build_vf_fit`. reframe_<clip>.json
  Р±С‹Р» `{mode, crop}` (РѕРґРЅРѕ Р·РЅР°С‡РµРЅРёРµ РЅР° РІРµСЃСЊ СЃРµРіРјРµРЅС‚).
  в›” **РџРћР›РќРћРЎРўР¬Р® Р—РђРњР•РќР•РќРћ R1** (per-shot РјРѕРґРµР»СЊ, СЃРј. R1-СЃРµРєС†РёРё РЅРёР¶Рµ). `decide_reframe_mode`,
  `build_vf_fit`, `build_vf_fill`, `build_ffmpeg_cmd`, `shot_centers`, `detect_cuts` (РѕСЃРЅРѕРІРЅРѕР№ РїСѓС‚СЊ)
  вЂ” РІСЃРµ РЈР”РђР›Р•РќР«. `reframe_<clip>.json` С‚РµРїРµСЂСЊ `{shots:[{t0,t1,mode,center}вЂ¦]}`.
  РўРµРєСѓС‰РёР№ РєРѕРґ: `stage3_reframe.py` (pure) + `stage5_render.py` (РѕРґРёРЅ РїСЂРѕС…РѕРґ).
- **РџСЂРѕРјРїС‚ РІС‹РЅРµСЃРµРЅ РІ С„Р°Р№Р»:** `services/worker/prompts/select_moments.v1.txt` (РєСЂСѓС‚РёС‚СЊ Р±РµР·
  РєРѕРґР°); `stage2_select.load_system_prompt()` РіСЂСѓР·РёС‚ РµРіРѕ, fallback вЂ” `DEFAULT_SYSTEM_PROMPT`.

### РС‚РµСЂР°С†РёСЏ РєР°С‡РµСЃС‚РІР° (РїРѕСЃР»Рµ Phase 0, РїРѕ С„РёРґР±РµРєСѓ С„Р°СѓРЅРґРµСЂР°; gate В«СЃРЅР°С‡Р°Р»Р° РєР°С‡РµСЃС‚РІРѕВ»)
- **K3 Р°РІС‚Рѕ-СЏР·С‹Рє РЎР”Р•Р›РђРќ СЂР°РЅРѕ** (RU РЅРµ СЂР°Р±РѕС‚Р°Р» РЅР° en): Deepgram `detect_language` (СЏР·С‹Рє=None),
  `transcript.language`=detected. РљРѕРјРјРёС‚ `9af07ec`. Comedy01 (RU, Р©РµСЂР±Р°РєРѕРІ) в†’ 7949 СЃР»РѕРІ.
- **Р‘РѕР»СЊС€Рµ РєР°РЅРґРёРґР°С‚РѕРІ:** `max_clips=8` (config) + РїСЂРѕРјРїС‚ В«surface ALL strong, РґРѕ NВ» + cap top-N
  РїРѕ score РІ postprocess. РљРѕРјРјРёС‚ `b8e078d`. comedy01: Р±С‹Р»Рѕ 2 в†’ СЃС‚Р°Р»Рѕ 8 РєР»РёРїРѕРІ.
- **eval-С…Р°СЂРЅРµСЃСЃ:** `app/eval.py` (СЂСѓР±СЂРёРєР° C1вЂ“C8, Q) + `docs/EVAL.md`. РљРѕРјРјРёС‚ `358054d`.
- **РџР»Р°РЅ Phase 1 (K1 RQ-РѕС‡РµСЂРµРґСЊ) РЅР°РїРёСЃР°РЅ, РёСЃРїРѕР»РЅРµРЅРёРµ РћРўР›РћР–Р•РќРћ** (РІС‹Р±СЂР°Р»Рё В«СЃРЅР°С‡Р°Р»Р° РєР°С‡РµСЃС‚РІРѕВ»):
  `docs/superpowers/specs/2026-06-07-phase1-reliability-design.md` + `.../plans/...k1-queue.md`.
- **D вЂ” dynamic reframe (РѕРєРЅРѕ РµРґРµС‚ Р·Р° Р»РёС†РѕРј) РЎР”Р•Р›РђРќ.** РљРѕРјРјРёС‚ `dabcdf6`. РўСЂРµРє РєРµР№С„СЂРµР№РјРѕРІ
  РІРјРµСЃС‚Рѕ РѕРґРЅРѕРіРѕ static-РѕРєРЅР°: `smooth_track` (PURE) = СЃРєРѕР»СЊР·СЏС‰РµРµ СЃСЂРµРґРЅРµРµ (РіР°СЃРёС‚ РґСЂРѕР¶СЊ) +
  dead-zone (СЃС‚Р°С‚РёРєР° в†’ 1 РѕРєРЅРѕ, Р±РµР· РґС‘СЂРіР°РЅСЊСЏ) + РєР°Рї; `build_crop_x_expr`/`build_vf_dynamic`
  (PURE) = РєСѓСЃРѕС‡РЅРѕ-Р»РёРЅРµР№РЅРѕРµ x(t) ffmpeg-РІС‹СЂР°Р¶РµРЅРёРµ, `setpts` РџР•Р Р’Р«Рњ (crop РІРёРґРёС‚ РєР»РёРї-РІСЂРµРјСЏ
  0-based), Р·Р°РїСЏС‚С‹Рµ СЌРєСЂР°РЅРёСЂРѕРІР°РЅС‹ `\,` РґР»СЏ filtergraph. render_clip: 1 РѕРєРЅРѕв†’static build_vf,
  >1в†’РґРёРЅР°РјРёРєР°. +14 unit-С‚РµСЃС‚РѕРІ. РџСЂРѕРІРµСЂРµРЅРѕ comedy01 ($0, РєСЌС€): clip_01 kf=12 x 591в†’1020в†’632
  (span 429px), РєР°РґСЂС‹ t=2/4/14 вЂ” СЂР°Р·РЅС‹Р№ РєР°РґСЂ СЃ Р»РёС†РѕРј; clip_06/08 kf=1 (Р±РµР· РґСЂРѕР¶Рё).
  вљ пёЏ РўСЋРЅРёРЅРі-РєР°РЅРґРёРґР°С‚С‹: РЅР° Р¶С‘СЃС‚РєРёС… СЃРєР»РµР№РєР°С… РёСЃС‚РѕС‡РЅРёРєР° РѕРєРЅРѕ РџР›РђР’РќРћ РїР°РЅРёС‚ РјРµР¶РґСѓ РїР»Р°РЅР°РјРё
  (РІ РёРґРµР°Р»Рµ вЂ” РјРіРЅРѕРІРµРЅРЅС‹Р№ СЃРєР°С‡РѕРє РЅР° cut; РґРµС‚РµРєС‚ СЃРєР»РµРµРє = Phase 1+). Р‘РёРјРѕРґР°Р»СЊРЅС‹Р№ РєР°РґСЂ
  (2 СЃРїРёРєРµСЂР°) в†’ MA СѓСЃСЂРµРґРЅСЏРµС‚ Рє С†РµРЅС‚СЂСѓ РјРµР¶РґСѓ РЅРёРјРё (РєР°Рє Рё СЃС‚Р°СЂР°СЏ РјРµРґРёР°РЅР°). РљРЅРѕР±С‹:
  `smooth_track(win, dead_zone, max_keyframes)`, `sample_face_centers(fps)`.
- **D2 вЂ” РЅР°РІРµРґРµРЅРёРµ РџР•Р Р•Р”Р•Р›РђРќРћ РЅР° cut-aware В«РґРµСЂР¶РёРј РїР»Р°РЅ + СЂРµР¶РµРј РЅР° СЃРєР»РµР№РєРµВ»** (С„РёРґР±РµРє
  С„Р°СѓРЅРґРµСЂР°: РїР»Р°РІРЅС‹Р№ РїР°РЅ В«РїР»Р°РІР°Р»/СѓРєР°С‡РёРІР°Р»В» РЅР° Р±С‹СЃС‚СЂРѕ-РјРѕРЅС‚Р°Р¶РЅРѕРј РјРЅРѕРіРѕРєР°РјРµСЂРЅРѕРј С€РѕСѓ). Р–С‘СЃС‚РєР°СЏ
  РїСЂРѕРІРµСЂРєР° РїРѕРєР°Р·Р°Р»Р°: clip_01 = 11 СЃРєР»РµРµРє Р·Р° 21СЃ, РѕРєРЅРѕ РµС…Р°Р»Рѕ РїСѓС‚С‘Рј 1739px РїСЂРё СЂР°Р·РјР°С…Рµ 429px,
  РІ РґРІРёР¶РµРЅРёРё 96% РІСЂРµРјРµРЅРё. РќРћР’РђРЇ РјРѕРґРµР»СЊ: `detect_cuts` (ffmpeg scene, thr 0.3, РєР»РёРї-relative) в†’
  `build_shots` (PURE) РёРЅС‚РµСЂРІР°Р»С‹ РїР»Р°РЅРѕРІ в†’ `shot_centers` (PURE, РјРµРґРёР°РЅР° Р»РёС†/РїР»Р°РЅ; РЅРµС‚ Р»РёС†Р° в†’
  РґРµСЂР¶РёРј РїСЂРµРґС‹РґСѓС‰РёР№) в†’ РћР”РќРћ РѕРєРЅРѕ РЅР° РїР»Р°РЅ; `build_crop_x_step_expr` (PURE) = РЎРўРЈРџР•РќР¬РљРђ (held
  РІРЅСѓС‚СЂРё РїР»Р°РЅР°, РјРіРЅРѕРІРµРЅРЅС‹Р№ СЃРєР°С‡РѕРє РЅР° СЃРєР»РµР№РєРµ) РІРјРµСЃС‚Рѕ Р»РёРЅРµР№РЅРѕР№ РёРЅС‚РµСЂРїРѕР»СЏС†РёРё. РЈРґР°Р»РµРЅС‹
  `smooth_track`/`build_crop_x_expr`. РџСЂРѕРІРµСЂРµРЅРѕ comedy01 ($0, РєСЌС€): clip_01 12 РїР»Р°РЅРѕРІ, 0px
  РґРІРёР¶РµРЅРёСЏ РІРЅСѓС‚СЂРё РїР»Р°РЅР°, 8 СЃРєР°С‡РєРѕРІ РўРћР›Р¬РљРћ РЅР° СЃРєР»РµР№РєР°С…; РєР°РґСЂС‹ t=14/17 (РѕРґРёРЅ РїР»Р°РЅ) вЂ” РѕРґРёРЅР°РєРѕРІС‹Р№
  РєСЂРѕРї (РґРµСЂР¶РёРј), t=11 (РґСЂ. РїР»Р°РЅ) вЂ” РґСЂСѓРіРѕР№ (СЃРєР°С‡РѕРє). +С‚РµСЃС‚С‹ build_shots/shot_centers/step_expr.
  вљ пёЏ thr=0.3 РёРЅРѕРіРґР° РџР РћРџРЈРЎРљРђР•Рў СЃРєР»РµР№РєСѓ (РІ clip_01 ~t15-16 РєРѕРЅС‚РµРЅС‚ СЃРјРµРЅРёР»СЃСЏ РІРЅСѓС‚СЂРё В«РїР»Р°РЅР°В» в†’
  РѕРєРЅРѕ РґРµСЂР¶РёС‚ СЃС‚Р°СЂС‹Р№ РєР°РґСЂ). РљРЅРѕР±: `detect_cuts(threshold=)`. Active-speaker (РєС‚Рѕ РіРѕРІРѕСЂРёС‚, Р° РЅРµ
  РєСЂСѓРїРЅРµР№С€РµРµ Р»РёС†Рѕ) вЂ” Phase 1+.
- **C вЂ” clean-start РЎР”Р•Р›РђРќ** (Р±Р°Рі В«РђРЅС‚РёРјРѕС€РµРЅРЅРёРєР°В»). `snap_start_index` С‚РµРїРµСЂСЊ 3-СѓСЂРѕРІРЅРµРІС‹Р№,
  backward-first: (1) РїСЂРµРґС‹РґСѓС‰РµРµ СЃР»РѕРІРѕ Р·Р°РІРµСЂС€РёР»Рѕ РїСЂРµРґР»РѕР¶РµРЅРёРµ в†’ СЃС‚Р°СЂС‚ С‡РёСЃС‚С‹Р№ (РЎРћРҐР РђРќРЇР•Рњ
  РєРѕСЂРѕС‚РєРёРµ С…СѓРєРё); (2) РЅР°Р·Р°Рґ Рє РЅР°С‡Р°Р»Сѓ С‚РµРєСѓС‰РµРіРѕ РїСЂРµРґР»РѕР¶РµРЅРёСЏ; (3) РµСЃР»Рё РѕРЅРѕ РЅРµРґРѕСЃС‚РёР¶РёРјРѕ РЅР°Р·Р°Рґ в†’
  СЃС‚Р°СЂС‚ РІ РҐР’РћРЎРўР• в†’ СѓС…РѕРґРёРј Р’РџР•Р РЃР” Рє РЅР°С‡Р°Р»Сѓ СЃР»РµРґСѓСЋС‰РµРіРѕ РїСЂРµРґР»РѕР¶РµРЅРёСЏ. +2 unit-С‚РµСЃС‚Р°.
  Р”РѕРєР°Р·Р°РЅРѕ РЅР° СЂРµР°Р»СЊРЅРѕРј comedy01 (РґРµС‚РµСЂРјРёРЅРёСЂРѕРІР°РЅРЅРѕ, $0): clip_01 Р±С‹Р» idx127 В«Р°РЅС‚РёРјРѕС€РµРЅРЅРёРєР°.В»
  (t=64.0) в†’ СЃС‚Р°Р» idx128 В«РЎРµРіРѕРґРЅСЏ Сѓ РјРµРЅСЏ РІ РіРѕСЃС‚СЏС…вЂ¦В» (t=66.0). Р§РёСЃС‚С‹Р№ СЃС‚Р°СЂС‚ РїСЂРµРґР»РѕР¶РµРЅРёСЏ.
  вљ пёЏ РљСЌС€: comedy01/segments.json С…СЂР°РЅРёС‚ РЎРўРђР Р«Р™ СЃРЅСЌРї вЂ” РЅРѕРІС‹Р№ СЃРЅСЌРї РїСЂРёРјРµРЅСЏРµС‚СЃСЏ РїСЂРё СЃРІРµР¶РµРј
  select (РїРµСЂРµРіРµРЅРµСЂР°С†РёСЏ РЅРёР¶Рµ / РЅРѕРІС‹Рµ РїСЂРѕРіРѕРЅС‹).
- **B вЂ” РєСѓСЂРёСЂРѕРІР°РЅРёРµ РІ UI РЎР”Р•Р›РђРќ.** (1) Р’С‹Р±РѕСЂ РєРѕР»РёС‡РµСЃС‚РІР°: СЃС‚РµРїРїРµСЂ в€’/+ (1вЂ“10, РґРµС„РѕР»С‚ 6) РІ
  SourceForm в†’ `max_clips` РІ POST /jobs (CreateJobBody, Field ge=1 le=10) в†’ run_pipeline в†’
  select_segments. PURE `resolve_max_clips(requested, default, lo, hi)` (Noneв†’РґРµС„РѕР»С‚, РєР»Р°РјРї) вЂ”
  +4 С‚РµСЃС‚Р°. (2) РљСѓСЂРёСЂРѕРІР°РЅРёРµ: С‡РµРєР±РѕРєСЃ РЅР° РєР°Р¶РґРѕРј ClipCard (selectedв†’СЂР°РјРєР°-Р°РєС†РµРЅС‚, СЃРЅСЏС‚в†’РїСЂРёРіР»СѓС€С‘РЅ),
  ClipGrid вЂ” СЃС‚РµР№С‚ РІС‹Р±РѕСЂР° (РїРѕ СѓРјРѕР»С‡Р°РЅРёСЋ Р’РЎР• РІС‹Р±СЂР°РЅС‹; `key={job.id}` СЃР±СЂР°СЃС‹РІР°РµС‚ РЅР° РЅРѕРІС‹Р№ РїСЂРѕРіРѕРЅ,
  Р±РµР· СЌС„С„РµРєС‚РѕРІ), Р±Р°СЂ В«Р’С‹Р±СЂР°РЅРѕ N РёР· MВ» + В«Р’С‹Р±СЂР°С‚СЊ/РЎРЅСЏС‚СЊ РІСЃРµВ» + В«РЎРєР°С‡Р°С‚СЊ РІС‹Р±СЂР°РЅРЅС‹Рµ (N)В»
  (РїРѕСЃР»РµРґРѕРІР°С‚РµР»СЊРЅС‹Рµ СЃРєР°С‡РёРІР°РЅРёСЏ). just check + next build Р·РµР»С‘РЅС‹Рµ. РџСЂРѕРІРµСЂРµРЅРѕ СЃРєСЂРёРЅС€РѕС‚Р°РјРё (mock):
  СЃС‚РµРїРїРµСЂ РІ С„РѕСЂРјРµ; РіСЂРёРґ СЃ С‡РµРєР±РѕРєСЃР°РјРё; СЃРЅСЏС‚С‹Р№ РєР»РёРї РїСЂРёРіР»СѓС€Р°РµС‚СЃСЏ, СЃС‡С‘С‚С‡РёРє/РєРЅРѕРїРєРё РѕР±РЅРѕРІР»СЏСЋС‚СЃСЏ.
- **Active-speaker reframe (РЅР°РІРµРґРµРЅРёРµ РЅР° Р“РћР’РћР РЇР©Р•Р“Рћ) вЂ” РЎР”Р•Р›РђРќ Р·Р° С„Р»Р°РіРѕРј** (С„РёРґР±РµРє: В«РїРѕС‡С‚Рё РЅРѕСЂРј,
  РЅРѕ СЃР»РµРґРёС‚СЊ РЅР°РґРѕ Р·Р° РЅСѓР¶РЅС‹Рј С‡РµР»РѕРІРµРєРѕРјВ»; СЂРµСЃС‘СЂС‡ РіРѕС‚РѕРІС‹С… СЂРµС€РµРЅРёР№). РЎРїР°Р№Рє (BENCHMARKS В§6): СЂРµРїРѕ
  LR-ASD РєР°Рє РµСЃС‚СЊ = 170СЃ/15СЃ-РєР»РёРї РЅР° CPU (СѓР·РєРѕРµ РјРµСЃС‚Рѕ вЂ” S3FD 22.5M, 129СЃ); РЅР°С€ MediaPipe-РґРµС‚РµРєС‚
  РІ ~42Г— Р±С‹СЃС‚СЂРµРµ в†’ lean-РїСѓС‚СЊ 15СЃ/15СЃ-РєР»РёРї. РњРѕРґРµР»СЊ ASD 0.84M (РІРµРЅРґРѕСЂРµРЅР° РІ `app/asd/_vendor`, MIT).
  РРЅРєСЂРµРјРµРЅС‚С‹: (1) РІРµРЅРґРѕСЂРёРЅРі СЏРґСЂР° + `app/asd/scorer.py` (Р»РµРЅРёРІС‹Р№ torch, РѕРїС†. РіСЂСѓРїРїР° `asd`);
  (2) PURE `build_tracks` (IOU, numpy) + `pick_speaker_centers` (argmax speak/РїР»Р°РЅ) +8 С‚РµСЃС‚РѕРІ;
  (3) `app/pipeline/asd_reframe.speaker_windows` (MediaPipe@25fpsв†’tracksв†’crop+ASDв†’С†РµРЅС‚СЂ) Р·Р°
  С„Р»Р°РіРѕРј `REFRAME_SPEAKER` (offв†’largest-face D2; torch РЅРµ РЅСѓР¶РµРЅ). РљРѕРјРјРёС‚С‹ `5f1011f`/`70f02b1`/`7e1690b`.
  РџСЂРѕРіРѕРЅ comedy01 (С„Р»Р°Рі on, $0): 5 РєР»РёРїРѕРІ ~374СЃ (~2Г— РґР»РёС‚РµР»СЊРЅРѕСЃС‚Рё РЅР° CPU), С‚СЂРµРє в‰  largest-face,
  РєР°РґСЂС‹ вЂ” Р»РёС†Рѕ РІ С†РµРЅС‚СЂРµ. РџРѕСЃР»Р°Р» С„Р°СѓРЅРґРµСЂСѓ РЅР° РѕС†РµРЅРєСѓ. вљ пёЏ РћРўРљР Р«РўРћ: РєР°С‡РµСЃС‚РІРѕ В«С‚РѕС‚ Р»Рё С‡РµР»РѕРІРµРєВ» вЂ”
  СЃСѓРґРёС‚ С„Р°СѓРЅРґРµСЂ РІРёР·СѓР°Р»СЊРЅРѕ; `reframe_speaker_crop_scale=0.55` С‚СЋРЅРёРј РїРѕРґ MediaPipe-РєСЂРѕРїС‹ (РјРѕРґРµР»СЊ
  РѕР±СѓС‡РµРЅР° РЅР° S3FD; score СЃР¶Р°С‚). Р’РѕСЂРєРµСЂ РЅР° :8000 РїРѕ СѓРјРѕР»С‡Р°РЅРёСЋ Р‘Р•Р— С„Р»Р°РіР° (UI-РїСЂРѕРіРѕРЅС‹ = largest-face).

### R1 вЂ” Reframe 2.0 (per-shot), РЎР”Р•Р›РђРќ 2026-06-08 (С„Р»РµС€Рё by-design СѓР±СЂР°РЅС‹)
Р“Р»Р°РІРЅР°СЏ Р±РѕР»СЊ С„Р°СѓРЅРґРµСЂР°: В«С„Р»РµС€РёВ» (СЃРјРµРЅР° РєСЂРѕРїР° РјРёРјРѕ СЃРєР»РµР№РєРё РЅР° РєР°РґСЂ) + b-roll СЂРµР¶РµС‚СЃСЏ СѓР·РєРёРј
СЃР»Р°Р№СЃРѕРј (В«С‚СЂР°РІР° РІРјРµСЃС‚Рѕ С€РёСЂРѕРєРѕВ»). РљРѕСЂРµРЅСЊ РІ РєРѕРґРµ: (1) СЃС‹СЂРѕР№ ffmpeg scene-РїРѕСЂРѕРі; (2) РєСЂРѕРї
Р’Р«Р РђР–Р•РќРР•Рњ Р’Рћ Р’Р Р•РњР•РќР `crop=вЂ¦:if(lt(t,T),x0,x1)` вЂ” T-float РЅРµ РїРѕРїР°РґР°РµС‚ РЅР° PTS РєР°РґСЂР°-СЃРєР»РµР№РєРё;
(3) СЂРµР¶РёРј fill/fit СЂРµС€Р°Р»СЃСЏ РћР”РРќ СЂР°Р· РЅР° СЃРµРіРјРµРЅС‚. РџРµСЂРµРїРёСЃР°РЅРѕ РЅР° **per-shot** (РєР°Рє Opus/Vizard):
- **R1.1** `352284c` вЂ” PySceneDetect ContentDetector (frame-accurate) РІРјРµСЃС‚Рѕ ffmpeg-РїРѕСЂРѕРіР°.
  pure `scenes_to_clip_cuts` (РѕС„СЃРµС‚ в€’start) + I/O `detect_scene_cuts`. вљ пёЏ scenedetect РќР• Р±С‹Р» РІ
  РґРµРїР°С… (РґРѕРєРё РІСЂР°Р»Рё) в†’ РґРѕР±Р°РІР»РµРЅ РІ Р‘РђР—РћР’Р«Р•; С€РєР°Р»Р° РїРѕСЂРѕРіР° ~27 (РќР• ffmpeg 0..1). comedy01 clip_01:
  14 СЃРєР»РµРµРє vs 8 Сѓ ffmpeg@0.4.
- **R1.2** `29460ad` вЂ” pure `build_shot_plan` + `ShotPlan`: СЂРµР¶РёРј Р Р•РЁРђР•РўРЎРЇ РќРђ РЁРћРў (Р»РёС†Рѕв†’fill+С†РµРЅС‚СЂ;
  РЅРµС‚ Р»РёС†Р°в†’fit С€РёСЂРѕРєРѕ).
- **R1.3a** `1019d40` вЂ” pure-Р±РёР»РґРµСЂС‹: `build_vf_fill`/`build_vf_fit_shot` (Р±РµР· СЃСѓР±С‚РёС‚СЂРѕРІ),
  `build_concat_list`/`build_concat_burn_cmd`, `merge_shot_plan` (СЃР»РёС‚СЊ СЂР°РІРЅС‹Рµ РїР»Р°РЅС‹: СЃС‚Р°С‚РёРєР°в†’1
  РєРѕРґРёСЂРѕРІРєР°, tolerance=dead_zone СЃСЂР°РІРЅ. СЃ Р”Р•Р Р–РРњР«Рњ С†РµРЅС‚СЂРѕРј), `windows_to_shot_plan` (speaker-Р°РґР°РїС‚РµСЂ).
- **R1.3b** `d234b92` вЂ” `render_clip`/`reframe_segment`/`run.py` РџР•Р Р•РџРРЎРђРќР« РЅР° per-shot: РєР°Р¶РґС‹Р№
  РїР»Р°РЅ = РѕС‚РґРµР»СЊРЅС‹Р№ ffmpeg-СЃРµРіРјРµРЅС‚ (cut + static-crop|fit-blur) в†’ concat-РґРµРјСѓРєСЃРµСЂ в†’ burn СЃСѓР±С‚РёС‚СЂРѕРІ
  2-Рј РїСЂРѕС…РѕРґРѕРј (РЅРµ СЂРІСѓС‚СЃСЏ РЅР° РіСЂР°РЅРёС†Рµ С€РѕС‚Р°). РЈРґР°Р»С‘РЅ time-expr (`build_vf_dynamic`/`build_crop_x_step_expr`).
  config `reframe_scene_threshold`/`reframe_min_scene_sec`. reframe_<clip>.json в†’ {shots:[вЂ¦]}.
- **DoD** вњ…: comedy01 (5 РІР°Р»РёРґРЅС‹С… mp4 1080Г—1920, РґР»РёС‚РµР»СЊРЅРѕСЃС‚Рё СЃС…РѕРґСЏС‚СЃСЏ, temp РІС‹С‡РёС‰РµРЅС‹, clip_01
  5 fit-С€РѕС‚РѕРІ РёР· 11 vs 0 СЂР°РЅСЊС€Рµ). Comedians-in-Cars 300вЂ“330СЃ (13 СЃРєР»РµРµРє): fit-РїРµСЂРµР±РёРІРєРё С€РёСЂРѕРєРѕ
  (t=17 РїРµР№Р·Р°Р¶ С†РµР»РёРєРѕРј), reframe СЃР»РµРґРёС‚ Р·Р° РіРѕРІРѕСЂСЏС‰РёРј (РћР±Р°РјР° 0.35 / РЎР°Р№РЅС„РµР»Рґ 0.74), РіСЂР°РЅРёС†Р°
  t=21.655 С‡РёСЃС‚Р°СЏ (РЅРµС‚ РєР°РґСЂР°-С„Р»РµС€Р°). РЎРєСЂРёРЅС‹ С„Р°СѓРЅРґРµСЂСѓ. 150 unit-С‚РµСЃС‚РѕРІ, just check Р·РµР»С‘РЅС‹Р№.
- вљ пёЏ Р“СЂР°Р±Р»Рё: `uv sync` (Р±РµР· `--extra asd`) РЈР”РђР›РЇР•Рў torch в†’ mypy РїР°РґР°РµС‚ РЅР° `app/asd/scorer.py`
  (subclass nn.Module=Any). Р”РµСЂР¶Р°С‚СЊ `uv sync --extra asd`. Comedians С†РµР»РёРєРѕРј С‡РµСЂРµР· UI РЅРµ РїСЂРѕРіРЅР°РЅ вЂ”
  Deepgram 408 SLOW_UPLOAD (upload 37РњР‘ wav, СЃРµС‚РµРІРѕРµ); reframe С‚РµСЃС‚РёР»СЃСЏ РЅР°РїСЂСЏРјСѓСЋ (`tmp/test_reframe_comedians.py`).
- вљ пёЏ РўСЋРЅРёРЅРі-РєР°РЅРґРёРґР°С‚С‹ (С„Р°СѓРЅРґРµСЂ СЃСѓРґРёС‚ РїРѕ СЃРєСЂРёРЅР°Рј): РєРѕСЂРѕС‚РєРёРµ fit-РїРµСЂРµР±РёРІРєРё РјРѕРіСѓС‚ Р±С‹С‚СЊ Р»РѕР¶РЅС‹РјРё
  (РґРµС‚РµРєС‚-РїСЂРѕРјР°С… Р»РёС†Р° РЅР° Р±С‹СЃС‚СЂРѕРј РїР»Р°РЅРµ) в†’ `reframe_min_scene_sec`/`reframe_scene_threshold`;
  speaker-РїСѓС‚СЊ РµС‰С‘ РЅР° ffmpeg detect_cuts (R1 РїРµСЂРµРІС‘Р» С‚РѕР»СЊРєРѕ largest-face РїСѓС‚СЊ).

### R1b вЂ” В«С€РёСЂРѕРєРѕ vs С‚Р°Р№С‚В» РїРѕ РіРµРѕРјРµС‚СЂРёРё Р»РёС† + РЈР РћРљ РїСЂРѕ РІРѕСЂРєРµСЂ, 2026-06-08 (`e8437e6`)
Р¤Р°СѓРЅРґРµСЂ РїСЂРѕС‚РµСЃС‚РёР» R1 РЅР° РЅРѕРІРѕРј РІРёРґРµРѕ (Kanye/Elon РґРёРїС„РµР№Рє) в†’ В«СЃР»РёС€РєРѕРј Р±Р»РёР·РєРѕ / РЅРµ С‚РѕС‚ С‡РµР»РѕРІРµРє /
РЅРµС‚ С€РёСЂРѕРєРѕРіРѕ РІРёРґР° / РїРѕР»РЅР°СЏ С…СѓР№РЅСЏВ». Р РђР—Р‘РћР  (systematic-debugging):
- **РљРѕСЂРµРЅСЊ В«РЅРµ РІРёРґРЅРѕ РёР·РјРµРЅРµРЅРёР№В» = РІРѕСЂРєРµСЂ РЅРµ РїРµСЂРµР·Р°РїСѓС‰РµРЅ** (uvicorn Р±РµР· --reload, СЃС‚Р°СЂС‚ 11:06,
  R1-РєРѕРјРјРёС‚С‹ 13:57+). Р¤Р°СѓРЅРґРµСЂ С‚РµСЃС‚РёР» Р”Рћ-R1 РєРѕРґ. Р”РѕРєР°Р·Р°РЅРѕ: reframe-json РµРіРѕ РґР¶РѕР±Р° СЃС‚Р°СЂРѕРіРѕ С„РѕСЂРјР°С‚Р°
  `{mode,crop}`. РЈСЂРѕРє РІ HANDOFF В§3 (вљ пёЏ РїРµСЂРµР·Р°РїСѓСЃРєР°С‚СЊ РІРѕСЂРєРµСЂ РїРѕСЃР»Рµ РїСЂР°РІРѕРє). Р’РѕСЂРєРµСЂ РїРµСЂРµР·Р°РїСѓС‰РµРЅ.
- **РЎС‚Р°СЂС‹Р№ РєРѕРґ СЂРµР°Р»СЊРЅРѕ РїР»РѕС…** РЅР° СЌС‚РѕРј РІРёРґРµРѕ: РѕРґРЅРѕ СЃС‚Р°С‚РёС‡РЅРѕРµ РѕРєРЅРѕ largest-face РЅР° РІРµСЃСЊ СЃРµРіРјРµРЅС‚ в†’
  clip_01 С‡С‘СЂРЅС‹Р№ РєР°РґСЂ (РѕРєРЅРѕ РЅР° С‚С‘РјРЅРѕР№ РїСѓСЃС‚РѕС‚Рµ), clip_04 Р·Р°С‚С‹Р»РѕРє (РЅРµ РіРѕРІРѕСЂСЏС‰РёР№). РќРѕРІС‹Р№ per-shot
  С‚СЂРµРєР°РµС‚ Р»РёС†Рѕ РїРѕ СЃРєР»РµР№РєР°Рј в†’ Р»РёС†Рѕ РІ РєР°РґСЂРµ (РїРѕРєР°Р·Р°Р» before/after).
- **РќРѕ fit РІРєР»СЋС‡Р°Р»СЃСЏ С‚РѕР»СЊРєРѕ РїСЂРё РћРўРЎРЈРўРЎРўР’РР Р»РёС†** в†’ РІРёРґРµРѕ СЃ Р»РёС†Р°РјРё РІСЃРµРіРґР° С‚Р°Р№С‚-fill. Р¤РёРєСЃ R1b:
  `sample_faces` (Р’РЎР• Р»РёС†Р° РєР°РґСЂР°: cx+С€РёСЂРёРЅР°) + pure `shot_is_wide` (2+ СЂР°Р·РЅРµСЃС‘РЅРЅС‹С… Р»РёС†Р°, СЂР°Р·РјР°С… >
  С€РёСЂРёРЅС‹ 9:16 в†’ С€РёСЂРѕРєРѕ) + `build_shot_plan` РїРѕ РіРµРѕРјРµС‚СЂРёРё (РЅРµС‚ Р»РёС†в†’fit; СЂР°Р·РЅРµСЃС‘РЅРЅС‹Рµв†’fit; РѕРґРЅРѕ/
  РєР»Р°СЃС‚РµСЂв†’fill РЅР° РєСЂСѓРїРЅРµР№С€РµРј). РЈРґР°Р»С‘РЅ РјС‘СЂС‚РІС‹Р№ shot_centers/decide_reframe_mode. 157 С‚РµСЃС‚РѕРІ.
- **РџСЂРѕРґСѓРєС‚РѕРІС‹Рµ СЂРµС€РµРЅРёСЏ С„Р°СѓРЅРґРµСЂР°** (AskUserQuestion): 2 С‡РµР»РѕРІРµРєР° в†’ С€РёСЂРѕРєРѕ РѕР±РѕРёС… (fit, РЅРµ active-
  speaker); РѕРґРёРЅРѕС‡РєР° в†’ full-bleed Р‘Р•Р— Р±Р»СЋСЂ-СЂР°РјРѕРє. вљ пёЏ Р¤РёР·РёРєР°: close-up РЅР° 16:9 + full-bleed = С‚Р°Р№С‚
  (fill = РїРѕР»РЅР°СЏ РІС‹СЃРѕС‚Р° = РјРёРЅРёРјР°Р»СЊРЅС‹Р№ Р·СѓРј full-bleed; РјРµРЅСЊС€Рµ Р·СѓРјР° Р±РµР· СЂР°РјРѕРє РЅРµР»СЊР·СЏ). MEDIUM-СЂРµР¶РёРј
  (РєСЂРѕРї С€РёСЂРµ Р»РёС†Р° + Р»С‘РіРєРёРµ СЂР°РјРєРё, РєР°Рє OpusClip) РїСЂРѕС‚РѕС‚РёРїРёСЂРѕРІР°РЅ Рё РџРћРљРђР—РђРќ, РЅРѕ С„Р°СѓРЅРґРµСЂ РІС‹Р±СЂР°Р»
  full-bleed в†’ РЅРµ РІРЅРµРґСЂСЏР». Р•СЃР»Рё В«СЃР»РёС€РєРѕРј Р±Р»РёР·РєРѕВ» РѕСЃС‚Р°РЅРµС‚СЃСЏ Р±РѕР»СЊСЋ вЂ” РІРµСЂРЅСѓС‚СЊСЃСЏ Рє MEDIUM (РЅСѓР¶РЅС‹ СЂР°РјРєРё).
- вљ пёЏ РќР°С…РѕРґРєРё: РґРІРѕР№РЅС‹Рµ СЃСѓР±С‚РёС‚СЂС‹ (РІРёРґРµРѕ СЃ РІС€РёС‚С‹РјРё СЃСѓР±С‚РёС‚СЂР°РјРё в†’ Р¶Р¶С‘Рј РїРѕРІРµСЂС…); 2-face-wide РќР•
  СЃСЂР°Р±Р°С‚С‹РІР°РµС‚, РєРѕРіРґР° РІС‚РѕСЂРѕР№ С‡РµР»РѕРІРµРє Р·Р°С‚С‹Р»РєРѕРј/РІ РїСЂРѕС„РёР»СЊ (MediaPipe РІРёРґРёС‚ 1 Р»РёС†Рѕ) вЂ” С‡Р°СЃС‚С‹Р№ РєРµР№СЃ РёРЅС‚РµСЂРІСЊСЋ.

### R1c вЂ” РћР”РРќ РїСЂРѕС…РѕРґ СЂРµРЅРґРµСЂР° (С„РёРєСЃ С„Р»РµС€РµР№ + РџРћР”Р›РђР“Рђ РђРЈР”РРћ), 2026-06-08 (`91fbc14`)
Р¤Р°СѓРЅРґРµСЂ: С„Р»РµС€Рё/С‡С‘СЂРЅС‹Рµ РєР°РґСЂС‹ РЅР° РїРµСЂРµС…РѕРґР°С… Р’РЎРЃ Р•Р©РЃ РµСЃС‚СЊ + РџРћР”Р›РђР“ Р—Р’РЈРљРђ РЅР° СЃС‚С‹РєР°С… (РІРёРґРµРѕ СЃ РјРЅРѕРіРёРјРё
СЃРєР»РµР№РєР°РјРё). В«Р’РґСЂСѓРі Сѓ РЅР°СЃ С‚СѓРїРѕРµ СЂРµС€РµРЅРёРµВ». Р”Р° вЂ” Р±С‹Р»Рѕ С‚СѓРїРѕРµ. Р Р°Р·Р±РѕСЂ (systematic-debugging, РїРѕРєР°РґСЂРѕРІРѕ
РЅР° РµРіРѕ РІРёРґРµРѕ): per-shot СЂРµРЅРґРµСЂ (R1.3b) СЂРµР·Р°Р» РєР»РёРї РЅР° N РћРўР”Р•Р›Р¬РќР«РҐ Р¤РђР™Р›РћР’ + concat-РґРµРјСѓРєСЃРµСЂ. Р”Р’Рђ Р±Р°РіР°:
- **РђРЈР”РРћ**: РєР°Р¶РґС‹Р№ AAC-СЃРµРіРјРµРЅС‚ РїСЂРё СЃРєР»РµР№РєРµ РґРѕР±Р°РІР»СЏРµС‚ priming в†’ РЅР° 13 СЃС‚С‹РєР°С… +0.25СЃ (clip_02 Р°СѓРґРёРѕ
  31.82 vs 31.57) = СЂР°СЃСЃРёРЅС…СЂРѕРЅ/РїРѕРґР»Р°Рі. (ffprobe duration вЂ” Р±С‹СЃС‚СЂС‹Р№ РґРµС‚РµРєС‚РѕСЂ.)
- **Р§РЃР РќР«Р™ РљРђР”Р **: СЂРµР°Р»СЊРЅР°СЏ СЃРєР»РµР№РєР° РЅР° РєР°РґСЂРµ 645, СЃС‚Р°СЂС‚ РєР»РёРїР° РЅР° Р”Р РћР‘РќРћРњ РєР°РґСЂРµ 594.12 в†’ РєСЂРѕРї
  РїРµСЂРµРєР»СЋС‡Р°Р»СЃСЏ РЅР° 1 РєР°РґСЂ РјРёРјРѕ в†’ 1 РєР°РґСЂ РќРћР’Р«Р™ РєРѕРЅС‚РµРЅС‚ СЃРѕ РЎРўРђР Р«Рњ РєСЂРѕРїРѕРј (С‚С‘РјРЅС‹Р№ РєСЂР°Р№) = В«С„Р»РµС€В».
  (Р”РѕРєР°Р·Р°РЅРѕ: РЅРµРїСЂРµСЂС‹РІРЅС‹Р№ single-crop СЂРµРЅРґРµСЂ С‚РѕРіРѕ Р¶Рµ СЃРµРіРјРµРЅС‚Р° вЂ” Р‘Р•Р— С‡С‘СЂРЅРѕРіРѕ; source-СЃРєР»РµР№РєР° С‡РёСЃС‚Р°СЏ.)
Р РµС€РµРЅРёРµ вЂ” РћР”РРќ РїСЂРѕС…РѕРґ РґРµРєРѕРґР° (stage5 РїРµСЂРµРїРёСЃР°РЅ): Р°СѓРґРёРѕ РЅРµРїСЂРµСЂС‹РІРЅС‹Рј `-map 0:a` (РќР• СЂРµР¶РµРј в†’ РЅРѕР»СЊ
РїРѕРґР»Р°РіРѕРІ); РІРёРґРµРѕ `[0:v]split=N` в†’ per-shot `trim=start_frame:end_frame` (frame-exact) + crop/fit +
`setsar=1` (РёРЅР°С‡Рµ concat РїР°РґР°РµС‚: fill/fit СЂР°Р·РЅС‹Р№ SAR) в†’ `concat`-С„РёР»СЊС‚СЂ (СЃС‚С‹РєСѓРµС‚ РґРµРєРѕРґРёСЂ. РєР°РґСЂС‹, РЅРµС‚
РґС‹СЂ в†’ РЅРµС‚ С‡С‘СЂРЅС‹С…). РЎС‚Р°СЂС‚ `-ss` Р’Р«Р РћР’РќР•Рќ РЅР° РіСЂР°РЅРёС†Сѓ РєР°РґСЂР° (round(seg_start*fps)/fps) в†’ trim-РєР°РґСЂС‹ =
СЂРµР°Р»СЊРЅС‹Рµ СЃРєР»РµР№РєРё. Р’С‹РїРёР»РµРЅС‹ build_vf_fill/_fit_shot/concat_list/concat_burn_cmd/ffmpeg_cmd. +Р±РёР»РґРµСЂС‹
build_reframe_filter/build_single_pass_cmd (10 С‚РµСЃС‚РѕРІ). Р РµРЅРґРµСЂ ~2.5Г— Р±С‹СЃС‚СЂРµРµ (РЅРµС‚ РґРІРѕР№РЅРѕР№ РєРѕРґРёСЂРѕРІРєРё).
- Р“СЂР°Р±Р»Рё: (1) fit-Р»РµР№Р±Р»С‹ `[bg][fg]` Р“Р›РћР‘РђР›Р¬РќР« РІ filtergraph в†’ СѓРЅРёРєР°Р»РёР·РёСЂРѕРІР°С‚СЊ РїРѕ С€РѕС‚Сѓ `[bg{i}]`,
  РёРЅР°С‡Рµ РєРѕР»Р»РёР·РёСЏ РЅР° 2+ fit. (2) concat-С„РёР»СЊС‚СЂ С‚СЂРµР±СѓРµС‚ РѕРґРёРЅР°РєРѕРІС‹Р№ SAR в†’ `setsar=1` РЅР° РєР°Р¶РґРѕРј СЃРµРіРјРµРЅС‚Рµ.
- вљ пёЏ РћРўРљР Р«РўРћ: Р¶РґС‘Рј РІРµСЂРґРёРєС‚ С„Р°СѓРЅРґРµСЂР° (С„Р»РµС€Рё/Р·РІСѓРє СѓС€Р»Рё?). Р”РІРѕР№РЅС‹Рµ СЃСѓР±С‚РёС‚СЂС‹ вЂ” РѕС‚РґРµР»СЊРЅРѕ.

### R1d вЂ” Р°РЅС‚Рё-С„Р»РµС€ (РєРѕСЂРѕС‚РєРёРµ С€РѕС‚С‹ РґРµСЂР¶Р°С‚ РєР°РґСЂ), 2026-06-08 (`f6bd15c`)
Р¤Р°СѓРЅРґРµСЂ: С„Р»РµС€Рё Р’РЎРЃ Р•Р©РЃ РµСЃС‚СЊ. Р Р°Р·Р±РѕСЂ (РїРѕРєР°РґСЂРѕРІРѕ comedy01): R1c СѓР±СЂР°Р» С‡С‘СЂРЅС‹Рµ РєР°РґСЂС‹/РїРѕРґР»Р°Рі, РЅРѕ
РѕСЃС‚Р°Р»РѕСЃСЊ СЂР°РїРёРґРЅРѕРµ С‡РµСЂРµРґРѕРІР°РЅРёРµ fillв†”fit РЅР° РљРћР РћРўРљРРҐ С€РѕС‚Р°С… (0.43/0.66/0.76СЃ) + СЃРєР°С‡РєРё С†РµРЅС‚СЂР° в†’
РєР°РґСЂ РјРёРіР°Р» С‚Р°Р№С‚-РєСЂРѕРїв†”РІРµСЃСЊ-РєР°РґСЂ-РІ-СЂР°РјРєР°С… РєР°Р¶РґС‹Рµ ~0.5СЃ. Р¤РёРєСЃ вЂ” pure `stabilize_plan(min_hold_sec)`:
С€РѕС‚ РєРѕСЂРѕС‡Рµ min_hold (РґРµС„РѕР»С‚ 1.5СЃ) РќР• РїРµСЂРµРєР»СЋС‡Р°РµС‚ РєР°РґСЂ, РџРћР“Р›РћР©РђР•РўРЎРЇ РїСЂРµРґС‹РґСѓС‰РёРј (РґРµСЂР¶РёРј mode+center).
Р’ reframe_segment РїРѕСЃР»Рµ merge: `merge(stabilize(plan))`. config `reframe_min_hold_sec`. +5 С‚РµСЃС‚РѕРІ.
Р”РѕРєР°Р·Р°РЅРѕ: comedy01 clip_01 11 С€РѕС‚РѕРІ(5 fit)в†’5(1 fit); Р·РѕРЅР° t=4.5-9.7 СЂР°РЅСЊС€Рµ РјРёРіР°Р»Р°, СЃС‚Р°Р»Р° СЃС‚Р°Р±РёР»СЊРЅРѕР№
(СЃРєСЂРёРЅ tmp/flash_ba.png). 156 С‚РµСЃС‚РѕРІ Р·РµР»С‘РЅС‹Рµ.
- **Р”РёР·Р°Р№РЅ СЃР»РµРґ. Р·Р°С…РѕРґР° Р·Р°С„РёРєСЃРёСЂРѕРІР°РЅ** (brainstorming + AskUserQuestion, С„Р°СѓРЅРґРµСЂ РІС‹Р±СЂР°Р» В«СЃРЅР°С‡Р°Р»Р°
  С„Р»РµС€РёВ», РїРѕС‚РѕРј В«С‚РѕС‚ С‡РµР»РѕРІРµРєВ»): РіРёР±СЂРёРґ вЂ” РґРµС‚РµРєС‚ Р›Р®Р”Р•Р™ (С‚РµР»Рѕ, РќР• Р»РёС†Рѕ: С„СЂРѕРЅС‚Р°Р»СЊРЅС‹Р№=РіР»Р°РІРЅС‹Р№, РІР»РµР·Р°РµС‚
  С†РµР»РёРєРѕРј) + Gemini РґР»СЏ СЃРїРѕСЂРЅС‹С… В«С€РёСЂРѕРєРѕ vs С„РѕРєСѓСЃВ»/В«РєС‚Рѕ РіР»Р°РІРЅС‹Р№В»; РґРµСЂР¶Р°С‚СЊ С„РѕРєСѓСЃ per shot, Р‘Р•Р— Р·СѓРјР°
  (С‡РёСЃС‚С‹Р№ РІРµСЂС‚РёРєР°Р»СЊРЅС‹Р№ РєСЂРѕРї), С€РёСЂРѕРєРѕ=fit-СЂР°РјРєРё С‚РѕР»СЊРєРѕ РґР»СЏ СЃСѓС‰РµСЃС‚РІРµРЅРЅС‹С… РїР»Р°РЅРѕРІ. РЎРј. СЌС‚РѕС‚ Р¶СѓСЂРЅР°Р».

### V2 Continuous Reframe, 2026-06-09 (`5b59f2e`) в†’ **Р—РђРњР•РќРЃРќ** cut-aligned path
Р‘С‹Р» РЅР°РїРёСЃР°РЅ РєР°Рє В«Р·Р°РјРµРЅР° R1В» (EMA РЅРµРїСЂРµСЂС‹РІРЅРѕРіРѕ СЃР»РµР¶РµРЅРёСЏ РІРјРµСЃС‚Рѕ per-shot). Р”РІР° РґРІРёР¶РєР° A/B.
Р“Р»Р°РІРЅР°СЏ РёРґРµСЏ: `smooth_centers(alpha=0.15)` РЅРµРїСЂРµСЂС‹РІРЅРѕ СЃРіР»Р°Р¶РёРІР°РµС‚ cx Р»РёС†Р°; `classify_frame` РЅР°
РєР°Р¶РґС‹Р№ 5fps-СЃСЌРјРїР» в†’ `build_trajectory` в†’ `build_regions` РіСЂСѓРїРїРёСЂСѓРµС‚ consecutive-mode СЂРµРіРёРѕРЅС‹.
РџСЂРѕР±Р»РµРјР° РІСЃРєСЂС‹Р»Р°СЃСЊ СЃСЂР°Р·Сѓ: РіСЂР°РЅРёС†С‹ СЂРµР¶РёРјР° РїР°РґР°СЋС‚ РЅР° СЃРµС‚РєСѓ 5fps (РєСЂР°С‚РЅРѕ 0.2СЃ), РЅРµ СЃРѕРІРїР°РґР°СЏ СЃРѕ
СЃРєР»РµР№РєР°РјРё в†’ С„Р»РµС€ РїСЂРё РєР°Р¶РґРѕРј fillв†”fit РїРµСЂРµС…РѕРґРµ. V2 РќРР“Р”Р• РІ production РЅРµ РІС‹Р·С‹РІР°РµС‚СЃСЏ (РѕСЃРЅРѕРІРЅРѕР№ РїСѓС‚СЊ
РІ `reframe_segment` РїРµСЂРµРєР»СЋС‡С‘РЅ РЅР° cut-aligned вЂ” СЃРј. РЅРёР¶Рµ). Р¤СѓРЅРєС†РёРё `build_trajectory`/`build_regions`
РѕСЃС‚Р°РІР»РµРЅС‹ РґР»СЏ РѕР±СЂР°С‚РЅРѕР№ СЃРѕРІРјРµСЃС‚РёРјРѕСЃС‚Рё (legacy). Engine A/B СЂРµРЅРґРµСЂ вЂ” РѕР±Р° Р¶РёРІС‹ Рё СЂР°Р±РѕС‡РёРµ.

### Flash Fix вЂ” Cut-Aligned Reframe, 2026-06-09 (РєРѕРјРјРёС‚С‹ `35e7f4d`вЂ¦`5659e5b`)
**РџСЂРѕР±Р»РµРјР° РґРёР°РіРЅРѕСЃС‚РёСЂРѕРІР°РЅР°** Opus-РїР»Р°РЅРЅРµСЂРѕРј РЅР° СЂРµР°Р»СЊРЅРѕРј РєСЌС€Рµ `comedy01`: V2-РіСЂР°РЅРёС†Р° `fillв†’fit`
СЃС‚РѕСЏР»Р° РЅР° t=11.6СЃ (СЃРµС‚РєР° 0.2), Р±Р»РёР¶Р°Р№С€Р°СЏ СЃРєР»РµР№РєР° вЂ” t=10.44СЃ, СЂР°СЃСЃРёРЅС…СЂРѕРЅ **+29 РєР°РґСЂРѕРІ**. Р’ РѕРєРЅРµ
В±1СЃ СЃРєР»РµРµРє РЅРµС‚ РІРѕРѕР±С‰Рµ. Р”РѕРєР°Р·Р°С‚РµР»СЊСЃС‚РІРѕ: `tmp/proof_montage.png` (6 РєР°РґСЂРѕРІ РґРѕ/РїРѕСЃР»Рµ 11.6 вЂ” РЅРµРїСЂРµСЂС‹РІРЅС‹Р№
РїР»Р°РЅ, РЅРёРєР°РєРёС… СЃРєР»РµРµРє). Р РµС€РµРЅРёРµ: РєР°Рє Сѓ Google AutoFlip / OpusClip вЂ” СЂРµР¶РёРј **РѕРґРёРЅ СЂР°Р· РЅР° РїР»Р°РЅ**.

**РќРѕРІС‹Рµ PURE-С„СѓРЅРєС†РёРё РІ `stage3_reframe.py`:**
- `samples_in_shot(raw, t0, t1)` вЂ” С„РёР»СЊС‚СЂ СЃСЌРјРїР»РѕРІ РІ РїРѕР»СѓРёРЅС‚РµСЂРІР°Р» [t0,t1). РўСЂРёРІРёР°Р»СЊРЅР°СЏ, РЅРѕ СЏРІРЅР°СЏ.
- `decide_shot_mode(shot_samples, *, crop_w_frac, mode_setting, wide_ratio=0.5)` вЂ” majority-vote
  `classify_frame` РїРѕ РїР»Р°РЅСѓ в†’ `"fill"` / `"fit"`. mode_setting override. РќРµС‚ СЃСЌРјРїР»РѕРІ в†’ fit.
- `build_shot_trajectory(shot_samples, smoothing)` вЂ” EMA cx РІРЅСѓС‚СЂРё РїР»Р°РЅР°; **init = РїРµСЂРІС‹Р№ СЂРµР°Р»СЊРЅС‹Р№
  cx** (РЅРµ 0.5 вЂ” РєР»СЋС‡РµРІРѕР№ С„РёРєСЃ: СЃС‚Р°СЂС‹Р№ РєРѕРґ РґР°РІР°Р» РїР°РЅ РѕС‚ С†РµРЅС‚СЂР° РІ РЅР°С‡Р°Р»Рµ РєР°Р¶РґРѕРіРѕ РїР»Р°РЅР°).
- `build_regions_from_shots(shots, raw, ...)` вЂ” СЃРѕР±РёСЂР°РµС‚ `TrackRegion` РїРѕ РїР»Р°РЅР°Рј + `merge_short_regions`.
  Р“СЂР°РЅРёС†Р° СЂРµРіРёРѕРЅР° = РіСЂР°РЅРёС†Р° РїР»Р°РЅР° = СЂРµР°Р»СЊРЅР°СЏ СЃРєР»РµР№РєР° в†’ С„Р»РµС€ С„РёР·РёС‡РµСЃРєРё РЅРµРІРѕР·РјРѕР¶РµРЅ.

**РР·РјРµРЅРµРЅРёСЏ РІ `reframe_segment`:** СЃС‚Р°СЂС‹Р№ `build_trajectory в†’ build_regions` Р·Р°РјРµРЅС‘РЅ РЅР°
`detect_cuts в†’ build_shots в†’ build_regions_from_shots`. РќРѕРІС‹Р№ config-РєРЅРѕР± `REFRAME_WIDE_RATIO=0.5`.
`run.py` РїСЂРѕР±СЂР°СЃС‹РІР°РµС‚ `wide_ratio=s.reframe_wide_ratio`.

**Р’РµСЂРёС„РёРєР°С†РёСЏ:** `tmp/verify_newregions.py` в†’ РІСЃРµ 3 РіСЂР°РЅРёС†С‹ СЂРµР¶РёРјР° comedy01/clip_01: О” = **0 РєР°РґСЂРѕРІ**.

**180 unit-С‚РµСЃС‚РѕРІ** (Р±С‹Р»Рѕ 167), `just check` Р·РµР»С‘РЅС‹Р№.

**вљ пёЏ GATED Task 6** вЂ” РїР»Р°РІРЅС‹Р№ zoom-РїРµСЂРµС…РѕРґ (~0.3СЃ) РґР»СЏ intra-shot wide-reveal. Р”РµР»Р°С‚СЊ С‚РѕР»СЊРєРѕ
РїРѕСЃР»Рµ РІРµСЂРґРёРєС‚Р° С„Р°СѓРЅРґРµСЂР° В«РѕСЃРЅРѕРІРЅС‹Рµ С„Р»РµС€Рё СѓС€Р»РёВ». Plan in `docs/superpowers/plans/2026-06-09-reframe-cut-snap-flash-fix.md`.

### Editor v3 вЂ” РЅРѕС‡РЅР°СЏ Р°РІС‚РѕРЅРѕРјРЅР°СЏ СЃРµСЃСЃРёСЏ (РІРµС‚РєР° feat/editor-v3), 2026-06-13
Р—Р°РїСЂРѕСЃ С„Р°СѓРЅРґРµСЂР°: В«СЂРµРґР°РєС‚РѕСЂ РІС‹РіР»СЏРґРёС‚ СѓРµР±Р°РЅСЃРєРё в†’ СЃРґРµР»Р°С‚СЊ РєР°Рє РІ РЅРѕСЂРјР°Р»СЊРЅС‹С… СЂРµРґР°РєС‚РѕСЂР°С…,
С„РёРЅР°Р»СЊРЅС‹Р№ РІРёРґ, РґРѕ РіРѕС‚РѕРІРѕРіРѕВ»; РѕС‚РІРµС‚С‹ (AskUserQuestion): СЃС‚СЂР°РЅРёС†Р° (РІРѕР·РІСЂР°С‚ Р±РµР·СѓРїСЂРµС‡РЅС‹Р№),
AI-РєР°СЂС‚Р° РїРѕР»РЅР°СЏ, split Р°РІС‚Рѕ+РІСЂСѓС‡РЅСѓСЋ, СЃСѓР±С‚РёС‚СЂС‹ РІСЃС‘. РЎРїРµРєР°+РїР»Р°РЅ РІ docs/superpowers.
- **РЎРЅР°С‡Р°Р»Р°**: main Р·Р°РїСѓС€РµРЅ (РЅР° remote Р±С‹Р»Р° СЂР°Р·РІРёР»РєР° СЃ **youtube-РєСѓРєР°РјРё РІ РєРѕРјРјРёС‚Рµ 59d07b4** вЂ”
  СЃРјРµСЂР¶РµРЅР° Р±РµР· РєСѓРє; вљ пёЏ РєСѓРєРё РІ РёСЃС‚РѕСЂРёРё GitHub в†’ С„Р°СѓРЅРґРµСЂСѓ РїРµСЂРµРІС‹РїСѓСЃС‚РёС‚СЊ). Р”РѕРєРё СЃРїР°СЃРµРЅС‹.
- **Р‘СЌРєРµРЅРґ**: Chapter/ChaptersData + CropOverride.center_b + HighlightStyle.animation
  (РєРѕРЅС‚СЂР°РєС‚С‹ в†’ just types); РѕР±С‰Р°СЏ retry-РѕР±С‘СЂС‚РєР° `call_gemini_structured` (select+chapters);
  `editor/chapters.py` (postprocess PURE + Gemini + РєСЌС€) + `GET /chapters` (pendingв†’С„РѕРЅв†’done);
  Р°РЅРёРјР°С†РёРё СЃР»РѕРІ pop/bounce (`word_animation_tags`, \t РѕС‚ РЅР°С‡Р°Р»Р° РЎРўР РћРљР, animation="none"
  РѕС‚РєР»СЋС‡Р°РµС‚ РєР°СЂР°РѕРєРµ С†РµР»РёРєРѕРј вЂ” primary РѕСЃС‚Р°С‘С‚СЃСЏ С†РІРµС‚РѕРј С‚РµРєСЃС‚Р°); 12 РїСЂРµСЃРµС‚РѕРІ (EвЂ“L);
  **split**: `_split_pair` (СЂРѕРІРЅРѕ 2 С‚СЂРµРєР° РїРѕРєСЂС‹С‚РёРµРј в‰Ґ60% С€РѕС‚Р°) РІ plan_regions (РіСЂР°РЅРёС†С‹
  СЂРµРіРёРѕРЅРѕРІ РќР• РґРІРёРіР°СЋС‚СЃСЏ вЂ” РёРЅРІР°СЂРёР°РЅС‚ С†РµР»), `_region_chain` (РѕР±С‰РёР№ fit/fill/split РґР»СЏ РѕР±РѕРёС…
  Р±РёР»РґРµСЂРѕРІ, Р»РµР№Р±Р»С‹ [pa{i}][pb{i}]), points_b РїРѕ РІСЃРµРјСѓ РїСѓС‚Рё, СЂСѓС‡РЅРѕР№ override center+center_b,
  mode="auto" СЃРЅРёРјР°РµС‚ override; fontsdir РІ subtitles-С„РёР»СЊС‚СЂРµ.
- **Р¤СЂРѕРЅС‚**: СЃС‚СЂР°РЅРёС†Р° `/edit/[jobId]/[clipId]` (РїСЂСЏРјРѕР№ URL СЂР°Р±РѕС‚Р°РµС‚; вЂ№ вЂє РєР»РёРїС‹; РІРѕР·РІСЂР°С‚
  `/?job=`), PreviewPlayer (СЃРІРѕРё РєРѕРЅС‚СЂРѕР»С‹: СЃРєСЂР°Р± РєР»РёРїР°, fullscreen РќРђ РљРћРќРўР•Р™РќР•Р Р•),
  РѕРЅ-РІРёРґРµРѕ РїСЂР°РІРєР° (РєР»РёРє=textarea РЅР° РјРµСЃС‚Рµ; РґСЂР°Рі РїРѕ Y=РїРѕР·РёС†РёСЏ СЃ РіР°Р№РґРѕРј), С‚Р°Р±С‹ РЎСѓР±С‚РёС‚СЂС‹/
  РЎС‚РёР»СЊ(12 РїСЂРµСЃРµС‚РѕРІ+РєР°СЃС‚РѕРјРёР·Р°С†РёСЏ)/РљР°РґСЂ(РђРІС‚Рѕ/РўР°Р№С‚/РЁРёСЂРѕРєРѕ/Split), TimelineV2 (РїРѕР»РѕСЃР° РіР»Р°РІ+
  Р·СѓРј/РїР°РЅ), РјРѕРґР°Р»РєР° Рё СЃС‚Р°СЂС‹Р№ TimelineEditor СѓРґР°Р»РµРЅС‹.
- **рџ”‘ В«Worker error: {}В» Р РђРЎРљР Р«Рў** (Р¶РёРІРѕР№ РґРµР±Р°Рі, РїРµСЂРµС…РІР°С‚ ErrorEvent): (1) РѕРєС‚РѕРїСѓСЃ РіСЂСѓР·РёС‚
  fallback-С€СЂРёС„С‚ `default.woff2` Р РЇР”РћРњ РЎ Р’РћР РљР•Р РћРњ вЂ” РЅРµ С…РѕСЃС‚РёР»СЃСЏ в†’ РІРѕСЂРєРµСЂ РїР°РґР°Р» в†’ РўРРҐРР™
  CSS-С„РѕР»Р±СЌРє (С„Р°СѓРЅРґРµСЂ РЅРёРєРѕРіРґР° РЅРµ РІРёРґРµР» libass!); С„РёРєСЃ fallbackFont=Montserrat.ttf.
  (2) video-СЂРµР¶РёРј РїРѕР·РёС†РёРѕРЅРёСЂСѓРµС‚ РєР°РЅРІР°СЃ РїРѕ object-CONTAIN РіРµРѕРјРµС‚СЂРёРё, Сѓ РЅР°СЃ cover в†’
  РєР°РЅРІР°СЃ 342Г—192 РјРёРјРѕ РєР°РґСЂР°; С„РёРєСЃ: **canvas-СЂРµР¶РёРј** (СЃРІРѕР№ РєР°РЅРІР°СЃ РЅР° РІРµСЃСЊ 9:16 РєРѕРЅС‚РµР№РЅРµСЂ,
  ResizeObserver+resize(), РІСЂРµРјСЏ РІСЂСѓС‡РЅСѓСЋ setCurrentTime РІ rAF). Р‘РѕРЅСѓСЃ: СЃРјРµРЅР° РёРЅС‚РµСЂРІР°Р»Р°
  РЅРµ РїРµСЂРµСЃРѕР·РґР°С‘С‚ WASM.
- **РљРѕРґРіРµРЅ-РіСЂР°Р±Р»СЏ**: `_strip_titles` РІ export_schema СѓРґР°Р»СЏР» РџРћР›Р• РјРѕРґРµР»Рё СЃ РёРјРµРЅРµРј "title"
  (Chapter.title РїСЂРѕРїР°Р» РёР· TS) вЂ” РІРЅСѓС‚СЂРё "properties" РєР»СЋС‡Рё С‚РµРїРµСЂСЊ РЅРµ Р·Р°С‡РёС‰Р°СЋС‚СЃСЏ + С‚РµСЃС‚.
- **РЁСЂРёС„С‚С‹**: Unbounded/Rubik (+Montserrat) РІ public/libass/fonts Р services/worker/fonts;
  ffmpeg `subtitles=:fontsdir=` РѕС‚РЅРѕСЃРёС‚РµР»СЊРЅС‹Рј РїСѓС‚С‘Рј (Р±РµР· СЌРєСЂР°РЅРёСЂРѕРІР°РЅРёСЏ C:).
- **DoD**: just check 297 С‚РµСЃС‚РѕРІ Р·РµР»С‘РЅС‹Р№; next build Р·РµР»С‘РЅС‹Р№; fps-grid О”=0.00000
  (tmp/verify_grid_fix.py, вљ пёЏ РЅСѓР¶РµРЅ PYTHONIOENCODING=utf-8 РЅР° Windows-РєРѕРЅСЃРѕР»Рё);
  split-СЂРµРЅРґРµСЂ РЅР°РїСЂСЏРјСѓСЋ: 1080Г—1920, РєР°РґСЂ=РґРІР° СЃС‚СЌРєР°-РєСЂРѕРїР° (tmp/split_frame.png);
  e2e Р¶РёРІСЊС‘Рј: libass СЂРёСЃСѓРµС‚ (РєР°РЅРІР°СЃ 342Г—610), РїСЂРµСЃРµС‚ Hormozi РїСЂРёРјРµРЅРёР»СЃСЏ live, СЂРµРЅРґРµСЂ
  РёР· UI в†’ mp4 СЃ Р·РµР»С‘РЅС‹Рј РєР°СЂР°РѕРєРµ (tmp/render_styled.png), РІРѕР·РІСЂР°С‚ РІРѕСЃСЃС‚Р°РЅРѕРІРёР» РіСЂРёРґ,
  AI-РєР°СЂС‚Р° comedy01 = 16 СЂРµР°Р»СЊРЅС‹С… РіР»Р°РІ. РЎРєСЂРёРЅС‹ tmp/editor_v3_*.png.
- вљ пёЏ РћС‚РєСЂС‹С‚Рѕ: split РєР»РёРєРѕРј РІ UI РЅРµ РїСЂРѕРІРµСЂРµРЅ РіР»Р°Р·Р°РјРё (Р±СЌРєРµРЅРґ РґРѕРєР°Р·Р°РЅ); РїРѕР»РёСЂРѕРІРєР° РІРёРґР° вЂ”
  РІРµСЂРґРёРєС‚ С„Р°СѓРЅРґРµСЂР°; PowerShell-РєРѕРЅСЃРѕР»СЊ cp1251 РґСѓС€РёС‚ О”-РїРµС‡Р°С‚СЊ (utf-8 env).

### Editor v3 вЂ” С„РёРєСЃС‹ РїРѕ Р¶РёРІРѕРјСѓ С„РёРґР±РµРєСѓ С„Р°СѓРЅРґРµСЂР° (С‚Р° Р¶Рµ РЅРѕС‡СЊ, `8370d4e` + `5352bff`)
Р¤Р°СѓРЅРґРµСЂ С‚РµСЃС‚РёР» РїР°СЂР°Р»Р»РµР»СЊРЅРѕ. РўСЂРё РІРѕР»РЅС‹ С„РёРґР±РµРєР° в†’ РєРѕСЂРЅРё Рё С„РёРєСЃС‹:
- **В«РЎСѓР±С‚РёС‚СЂС‹ РґС‘СЂРіР°СЋС‚СЃСЏ / СЃР»РѕРІРѕ РїСЂС‹РіР°РµС‚ РЅР° 2-СЋ СЃС‚СЂРѕРєСѓВ»**: (Р°) \fscx РІ Р°РЅРёРјР°С†РёСЏС… РјРµРЅСЏР»
  РЁРР РРќРЈ СЃС‚СЂРѕРєРё в†’ libass РїРµСЂРµРїРµСЂРµРЅРѕСЃРёР» РµС‘ РЅР° РєР°Р¶РґРѕРј РєР°РґСЂРµ в†’ Р°РЅРёРјР°С†РёРё СЃС‚Р°Р»Рё С‚РѕР»СЊРєРѕ
  РІРµСЂС‚РёРєР°Р»СЊРЅС‹РјРё (\fscy118 pop / 115-96-100 bounce) + С‚РµСЃС‚-Р·Р°РїСЂРµС‚ \fscx; (Р±) \t РІ ASS
  РґРµР№СЃС‚РІСѓРµС‚ РЅР° Р’Р•РЎР¬ РїРѕСЃР»РµРґСѓСЋС‰РёР№ С‚РµРєСЃС‚ в†’ Р°РЅРёРјР°С†РёСЏ 1-РіРѕ СЃР»РѕРІР° РґС‘СЂРіР°Р»Р° РІСЃСЋ СЃС‚СЂРѕРєСѓ, Сѓ
  СЃР»РµРґСѓСЋС‰РёС… В«РЅРµ СЂР°Р±РѕС‚Р°Р»Р°В» в†’ РєР°Р¶РґС‹Р№ Р±Р»РѕРє СЃР±СЂР°СЃС‹РІР°РµС‚ \fscy100 РїРµСЂРµРґ СЃРІРѕРёРј \t (СЃС‚Р°РЅРґР°СЂС‚
  РєР°СЂР°РѕРєРµ-С€Р°Р±Р»РѕРЅРѕРІ). +С‚РµСЃС‚ РЅР° СЃР±СЂРѕСЃ.
- **РќРµСЃС‚Р°Р±РёР»СЊРЅС‹Р№ РґСЂР°Рі РёРЅС‚РµСЂРІР°Р»Р°**: refetchAfter СЃС‚Р°Р» Р°С‚РѕРјР°СЂРЅС‹Рј (analysis+ASS РґРѕ
  setState РѕРґРЅРёРј Р±Р°С‚С‡РµРј вЂ” СѓР±СЂР°РЅРѕ РѕРєРЅРѕ В«СЃС‚Р°СЂС‹Р№ ASS СЃ РЅРѕРІС‹Рј РѕС„С„СЃРµС‚РѕРјВ», РјРёРіР°Р»Рё РЅРµ С‚Рµ
  СЃР»РѕРІР°); refreshAss СЃРµРєРІРµРЅСЃРёСЂРѕРІР°РЅ (seq-С‚РѕРєРµРЅ); TimelineV2 Р±Р»РѕРєРёСЂСѓРµС‚ РЅРѕРІС‹Р№ РґСЂР°Рі РїРѕРєР°
  СЃРѕС…СЂР°РЅСЏРµС‚СЃСЏ РїСЂРµРґС‹РґСѓС‰РёР№ (Р±Р»РѕРє В«СЃРѕС…СЂР°РЅСЏСЋвЂ¦В» + pulse).
- **РџСЂР°РІРєРё РЅР° С…РѕРґСѓ** (РІРёРґРµРѕ РёРіСЂР°РµС‚, СЋР·РµСЂ РєР»РёРєР°РµС‚): Р’РЎР• РјСѓС‚Р°С†РёРё СЃСѓР±С‚РёС‚СЂРѕРІ (PATCH СЃС‚РёР»СЊ/
  С†РІРµС‚/Р°РЅРёРјР°С†РёСЏ/С‚РµРєСЃС‚ + apply-preset) вЂ” С‡РµСЂРµР· РµРґРёРЅСѓСЋ РѕС‡РµСЂРµРґСЊ РїСЂРѕРјРёСЃРѕРІ (editRef СЃРѕ
  СЃРІРµР¶РµР№ РІРµСЂСЃРёРµР№ РЅР° РјРѕРјРµРЅС‚ РёСЃРїРѕР»РЅРµРЅРёСЏ) в†’ Р±РѕР»СЊС€Рµ РЅРёРєР°РєРёС… 409 в†’ reload. PresetStrip
  РїРµСЂРµРІРµРґС‘РЅ РЅР° onApply-РїСЂРѕРї (СЃР°Рј РЅРµ Р·РѕРІС‘С‚ API). РЎС‚СЂРµСЃСЃ РїСЂРё РІРѕСЃРїСЂРѕРёР·РІРµРґРµРЅРёРё: 4 РїСЂРµСЃРµС‚Р°
  + 2 Р°РЅРёРјР°С†РёРё РїРѕРґСЂСЏРґ в†’ 0 РєРѕРЅС„Р»РёРєС‚РѕРІ, РІРµСЂСЃРёСЏ РјРѕРЅРѕС‚РѕРЅРЅР°.
- **В«Р”РµС„РѕР»С‚ Р¶С‘Р»С‚С‹Р№, Р° РЅРµ РѕСЂР°РЅР¶РµРІС‹Р№В»**: default_caption_track Р±СЂР°Р» HighlightStyle()
  (#FFE000) РІРјРµСЃС‚Рѕ РїСЂРµСЃРµС‚Р° A в†’ С‚РµРїРµСЂСЊ style+highlight РёР· seed preset_a (РєРѕСЂР°Р»Р»
  #FF5A3D, box). Р¤РѕР»Р±СЌРєРё С„СЂРѕРЅС‚Р° РїСЂРёРІРµРґРµРЅС‹. РЎС‚Р°СЂС‹Рµ Р¶С‘Р»С‚С‹Рµ edit-СЃС‚РµР№С‚С‹ comedy01
  СЃРјРёРіСЂРёСЂРѕРІР°РЅС‹ apply-preset'РѕРј (РЅРµС‚СЂРѕРЅСѓС‚С‹Рµ: clip_01 Hormozi, clip_04 СѓР¶Рµ РєРѕСЂР°Р»Р»).
- **РРЅРґРёРєР°С‚РѕСЂ В«РџСЂР°РІРєРё РЅРµ РІ СЂРµРЅРґРµСЂРµВ»**: dirty-СЃС‚РµР№С‚ РЅР° РІСЃРµС… РјСѓС‚Р°С†РёСЏС… в†’ Р¶С‘Р»С‚С‹Р№ С‡РёРї РІ
  С…РµРґРµСЂРµ + С‚РѕС‡РєР° РЅР° РєРЅРѕРїРєРµ Р РµРЅРґРµСЂ (С‚СѓР»С‚РёРї В«РїСЂРµРІСЊСЋ СѓР¶Рµ РїРѕРєР°Р·С‹РІР°РµС‚, С„Р°Р№Р» СЃС‚Р°СЂС‹Р№В»);
  СЃР±СЂР°СЃС‹РІР°РµС‚СЃСЏ РЅР° render done. LibassLayer rAF-СЃРёРЅРє Р·Р°С‚СЂРѕС‚С‚Р»РµРЅ РґРѕ 30Р“С† (targetFps 24).
- Р“РµР№С‚: 298 С‚РµСЃС‚РѕРІ, tsc/eslint Р·РµР»С‘РЅС‹Рµ. Р’РµС‚РєР° СЃРјРµСЂР¶РµРЅР° РІ main РїРѕ Р·Р°РїСЂРѕСЃСѓ С„Р°СѓРЅРґРµСЂР°.

### Р РµС€РµРЅРёРµ РїРѕ LLM (СЌС‚Р°Рї D): Gemini РІРјРµСЃС‚Рѕ Anthropic
- РЈ С„Р°СѓРЅРґРµСЂР° РќР•Рў Anthropic-РєР»СЋС‡Р° в†’ СЌС‚Р°Рї D РЅР° **Gemini** (РїР»Р°РЅ СЌС‚Рѕ СЂР°Р·СЂРµС€Р°РµС‚: LLM swappable).
- SDK: **`google-genai` 2.8.0** (`from google import genai`). РђРІС‚РѕСЂРёС‚РµС‚РЅРѕ (РёРЅС‚СЂРѕСЃРїРµРєС†РёСЏ,
  РќР• РІРµР±-РїРµСЂРµСЃРєР°Р· вЂ” РѕРЅ РїРµСЂРµРІСЂР°Р» С„РѕСЂРјСѓ):
  ```python
  from google import genai
  from google.genai import types
  client = genai.Client(api_key=GEMINI_API_KEY)
  resp = client.models.generate_content(
      model="gemini-2.5-pro",
      contents=user_prompt,
      config=types.GenerateContentConfig(
          system_instruction=SYSTEM_PROMPT,
          response_mime_type="application/json",
          response_schema=SEGMENTS_SCHEMA,            # dict JSON-schema РёР»Рё pydantic
          thinking_config=types.ThinkingConfig(thinking_level="high"),
      ),
  )
  raw = resp.text            # СЃС‹СЂРѕР№ JSON; resp.parsed вЂ” С‚РёРїРёР·РёСЂРѕРІР°РЅРѕ; resp.usage_metadata вЂ” С‚РѕРєРµРЅС‹
  ```
- РњРѕРґРµР»Рё 2026: gemini-3.1-pro-preview, gemini-3.5-flash, gemini-3.1-flash-lite,
  **gemini-2.5-pro** (РґРµС„РѕР»С‚, stable, deep reasoning), gemini-2.5-flash(-lite).
- score РќР• РѕРіСЂР°РЅРёС‡РёРІР°РµРј РІ СЃС…РµРјРµ (Gemini РјРѕР¶РµС‚ РёРіРЅРѕСЂРёС‚СЊ min/max) в†’ РєР»РёРїРїРёРј РІ РїРѕСЃС‚РѕР±СЂР°Р±РѕС‚РєРµ (D2).
- РљР»СЋС‡ РІ `.env`: `GEMINI_API_KEY`, `LLM_PROVIDER=gemini`, `LLM_MODEL=gemini-2.5-pro`.

### Editor Core (MVP) вЂ” РЎР”Р•Р›РђРќ 2026-06-09 (E0в†’E6)
РќРµ-РґРµСЃС‚СЂСѓРєС‚РёРІРЅС‹Р№ СЂРµРґР°РєС‚РѕСЂ РїРѕРІРµСЂС… batch-РїР°Р№РїР»Р°Р№РЅР°. ClipEdit = SourceInterval[] + CaptionTrack + CropOverride[].
РќРѕРІС‹Р№ РїР°РєРµС‚ `app/editor/`: timemap, replies, defaults, ops, reframe_cache, captions_v2, store, presets.
REST-СЌРЅРґРїРѕРёРЅС‚С‹: GET/PATCH /edit, trim/add-section/extend/crop/render/analysis, presets.
РњСѓР»СЊС‚Рё-РёРЅС‚РµСЂРІР°Р»СЊРЅС‹Р№ СЂРµРЅРґРµСЂ: `render_timeline` в†’ asplitв†’atrimв†’concat РІ filtergraph (РЅРµС‚ AAC priming).
Р›РµРЅРёРІРѕРµ СЃРѕР·РґР°РЅРёРµ edit-state РЅР° РїРµСЂРІС‹Р№ GET (РЅРµС‚ СЌР°РіРµСЂРЅРѕР№ СЃРІСЏР·Рё run.pyв†’Р‘Р”).
Optimistic-lock: version mismatch в†’ HTTP 409.
Р”РѕРєР°Р·Р°РЅРѕ E6: comedy01/clip_01 trimв†’2 РёРЅС‚РµСЂРІР°Р»Р°, expected=19.77s video=19.76s audio=19.78s render=9.88s.
РџСЂР°РІРєРё = $0 (РЅРµС‚ Deepgram/Gemini). 218 unit-С‚РµСЃС‚РѕРІ, just check Р·РµР»С‘РЅС‹Р№.

### Reframe v3 вЂ” РµРґРёРЅС‹Р№ ASD-РїСѓС‚СЊ + DoD О”=0, 2026-06-10 (РєРѕРјРјРёС‚С‹ `76e5132`вЂ¦`9a14660`)
**Р—Р°РґР°С‡Р°**: СѓР±СЂР°С‚СЊ С„Р»РµС€Рё РѕРєРѕРЅС‡Р°С‚РµР»СЊРЅРѕ + РІСЃРµРіРґР° СЃР»РµРґРёС‚СЊ Р·Р° Р“РћР’РћР РЇР©РРњ (РЅРµ largest-face).
РС‚РµСЂР°С†РёРё R1вЂ“R1d СѓР±СЂР°Р»Рё Р±РѕР»СЊС€РёРЅСЃС‚РІРѕ С„Р»РµС€РµР№, РЅРѕ РёСЃРїРѕР»СЊР·РѕРІР°Р»Рё ffmpeg scene-РїРѕСЂРѕРі (float, РЅРµ frame-
accurate) Рё С„РѕСЂРє `if reframe_speaker:` вЂ” РґРІР° РѕС‚РґРµР»СЊРЅС‹С… РїСѓС‚Рё СЃ СЂР°Р·РЅС‹РјРё Р±Р°РіР°РјРё.

**РђСЂС…РёС‚РµРєС‚СѓСЂРЅС‹Рµ РёР·РјРµРЅРµРЅРёСЏ:**
- **torch/ASD в†’ Р±Р°Р·РѕРІС‹Рµ Р·Р°РІРёСЃРёРјРѕСЃС‚Рё** (Р±С‹Р» `[project.optional-dependencies] asd` в†’ `uv sync` Р±РµР·
  С„Р»Р°РіР° СѓРґР°Р»СЏР» torch в†’ ASD РјРѕР»С‡Р° РЅРµ СЂР°Р±РѕС‚Р°Р»). РўРµРїРµСЂСЊ `uv sync` Р±РµР· С„Р»Р°РіРѕРІ = СЂР°Р±РѕС‡РёР№ ASD.
- **face_fps=25.0** (Р±С‹Р»Рѕ 5.0). LR-ASD РѕР±СѓС‡РµРЅР° РЅР° 4:1 audio/video (25fps РІРёРґРµРѕ). РџСЂРё 5fps РјРѕРґРµР»СЊ
  РґР°С‘С‚ СЃР»СѓС‡Р°Р№РЅС‹Рµ speak-score в†’ fallback РЅР° largest-face. Р¤РёРєСЃ РІ config.py.
- **SpeakerTrack** dataclass: f0/f1 (РєР°РґСЂС‹), cx (tuple С†РµРЅС‚СЂРѕРІ РїРѕ РєР°РґСЂР°Рј), width, speak (mean ASD).
  Р—Р°РјРµРЅСЏРµС‚ CropWindow вЂ” СЃРѕРґРµСЂР¶РёС‚ РІСЃСЋ РёРЅС„Сѓ РґР»СЏ РїР»Р°РЅРёСЂРѕРІС‰РёРєР°.
- **score_tracks_in_segment** (`asd_reframe.py`) в†’ `list[SpeakerTrack]` РІРјРµСЃС‚Рѕ `list[CropWindow]|None`.
- **build_shots_frames** (PURE) вЂ” РєР°РґСЂС‹-СЃРєР»РµР№РєРё РёР· PySceneDetect в†’ СЃРїРёСЃРѕРє РёРЅС‚РµСЂРІР°Р»РѕРІ `(f0, f1)`.
  Р¦РµР»С‹Рµ С‡РёСЃР»Р° РЅР° РІСЃС‘Рј РїСѓС‚Рё: PySceneDetect в†’ `trim=start_frame=` РІ ffmpeg вЂ” float-РѕРєСЂСѓРіР»РµРЅРёРµ РёСЃРєР»СЋС‡РµРЅРѕ.
- **plan_regions** (PURE) вЂ” РµРґРёРЅС‹Р№ РїР»Р°РЅРёСЂРѕРІС‰РёРє: ASD score в†’ РіРѕРІРѕСЂСЏС‰РёР№/largest-face; РіРµРѕРјРµС‚СЂРёСЏ в†’
  fill/fit; РіСЂР°РЅРёС†С‹ = СЂРµР°Р»СЊРЅС‹Рµ РєР°РґСЂС‹-СЃРєР»РµР№РєРё. РќРµС‚ С„РѕСЂРєР° `if reframe_speaker:`.
- **Р–С‘СЃС‚РєРёР№ cut** (stage5): xfade РјРµР¶РґСѓ fill/fit СѓРґР°Р»С‘РЅ (`build_smooth_filter`, `build_timeline_filter`).
  РљСЂРѕСЃСЃС„РµР№Рґ С‚Р°Р№С‚в†”С€РёСЂРѕРєРёР№ СЃР°Рј Р±С‹Р» zoom-РІСЃРїС‹С€РєРѕР№.
- **РњС‘СЂС‚РІС‹Р№ РєРѕРґ СѓРґР°Р»С‘РЅ**: ShotPlan, aggregate_center, build_trajectory, build_regions,
  shot_plan_to_regions, windows_to_shot_plan, pick_speaker_centers, apply_dead_zone.
- **Windows file-lock**: PySceneDetect РґРµСЂР¶РёС‚ lock РЅР° temp .mp4 в†’ `vid.capture.release()` РїРµСЂРµРґ
  РІС‹С…РѕРґРѕРј РёР· TemporaryDirectory.

**DoD вЂ” `tmp/dod_reframe_direct.py`** (Р±РµР· Deepgram/Gemini, РїСЂСЏРјРѕ РЅР° 3 СЃРµРіРјРµРЅС‚Р°С… dod01):
- seg_A (60вЂ“180СЃ): 30 СЃРєР»РµРµРє в†’ 28 СЂРµРіРёРѕРЅРѕРІ, 27 РіСЂР°РЅРёС† вЂ” РІСЃРµ О”=0 вњ…
- seg_B (300вЂ“420СЃ): 15 СЃРєР»РµРµРє в†’ 15 СЂРµРіРёРѕРЅРѕРІ, 14 РіСЂР°РЅРёС† вЂ” РІСЃРµ О”=0 вњ…
- seg_C (600вЂ“720СЃ): 26 СЃРєР»РµРµРє в†’ 24 СЂРµРіРёРѕРЅР°, 23 РіСЂР°РЅРёС†С‹ вЂ” РІСЃРµ О”=0 вњ…
- **РРўРћР“Рћ: 64 РіСЂР°РЅРёС†С‹ СЂРµР¶РёРјР°, max О” = 0 РєР°РґСЂРѕРІ** в†’ С„Р»РµС€ С„РёР·РёС‡РµСЃРєРё РЅРµРІРѕР·РјРѕР¶РµРЅ.

`just check` Р·РµР»С‘РЅС‹Р№ (РІСЃРµ unit-С‚РµСЃС‚С‹ + mypy + ruff + tsc + anti-drift).

вљ пёЏ Р“СЂР°Р±Р»Рё: Deepgram WriteTimeout РЅР° РґР»РёРЅРЅС‹С… РІРёРґРµРѕ (>30РјРёРЅ, WAV >80РњР‘).
`httpx.post()` СЃ РґРµС„РѕР»С‚РЅС‹Рј write_timeout=5СЃ РЅРµ СѓСЃРїРµРІР°РµС‚ Р·Р°РіСЂСѓР·РёС‚СЊ. РќСѓР¶РЅРѕ `write=None` (Р±РµР· С‚Р°Р№РјР°СѓС‚Р°)
РёР»Рё `httpx.Client(timeout=httpx.Timeout(connect=10, write=None, read=300, pool=10))` РІ stage1.
Р­С‚Рѕ С„РёРєСЃ РЅР° СЃР»РµРґСѓСЋС‰СѓСЋ СЃРµСЃСЃРёСЋ (DoD dod01 РѕР±РѕР№РґС‘РЅ РїСЂСЏРјС‹Рј reframe-С‚РµСЃС‚РѕРј Р±РµР· С‚СЂР°РЅСЃРєСЂРёРїС†РёРё).

### РќРѕС‡СЊ Р»Р°СѓРЅС‡-MVP (РІРµС‚РєР° `feat/mvp-launch`), 2026-06-13 вЂ” scope T1вЂ“T6 (LAUNCH_BRIEF)
РђРІС‚РѕРЅРѕРјРЅР°СЏ РЅРѕС‡СЊ: РґРѕРІРµСЃС‚Рё СЏРґСЂРѕ РґРѕ РїСЂРѕРґР°РІР°РµРјРѕРіРѕ MVP. РћС‚РІС‘Р» `feat/mvp-launch` РѕС‚ HEAD main.

- **T1/T2 вЂ” С…СѓРє (С‚РѕРї-С‚РµРєСЃС‚) + Р±РѕРіР°С‚С‹Р№ reasoning. РЎР”Р•Р›РђРќРћ** (РєРѕРјРјРёС‚С‹ `0aa94c6`, `c6a4368`).
  РћР±СЉСЏСЃРЅРёРјРѕСЃС‚СЊ = РЅР°С€ РѕС‚Р»РёС‡РёС‚РµР»СЊ vs Vizard. **Р РµС€РµРЅРёРµ С…СЂР°РЅРµРЅРёСЏ С…СѓРєР°: `CaptionTrack.hook:
  HookOverlay`** (Р±СЂРёС„ СЂР°Р·СЂРµС€Р°Р» top-overlay РІ CaptionTrack) вЂ” РґР°С‘С‚ РћР“Р РћРњРќРЈР® СЌРєРѕРЅРѕРјРёСЋ: С…СѓРє
  РєРѕРјРїРёР»РёС‚СЃСЏ РІ РўРћРў Р–Р• ASS, С‡С‚Рѕ СЃСѓР±С‚РёС‚СЂС‹ в†’ `compile_ass(track)` С‡РёС‚Р°РµС‚ `track.hook` в†’
  Р°РІС‚РѕРјР°С‚РѕРј РІ libass-РїСЂРµРІСЊСЋ (`/ass`) Р ffmpeg-СЌРєСЃРїРѕСЂС‚Рµ (`render_edit_to_file` в†’
  `write_caption_ass`), Р‘Р•Р— РЅРѕРІС‹С… СЌРЅРґРїРѕРёРЅС‚РѕРІ/threading; С„СЂРѕРЅС‚РѕРІС‹Р№ `patchCaptions` (PATCH
  РІСЃРµРіРѕ captions) СѓР¶Рµ РїРµСЂСЃРёСЃС‚РёС‚ С…СѓРє; `apply_preset` СЃРѕС…СЂР°РЅСЏРµС‚ hook (С‚СЂРѕРіР°РµС‚ С‚РѕР»СЊРєРѕ style/
  highlight). PURE `build_hook_event` (TDD) = ASS top-event (alignment 8, РѕРєРЅРѕ РІРµСЃСЊ РєР»РёРї|
  РїРµСЂРІС‹Рµ N СЃРµРє, Р±СЂРµРЅРґ-РїР»Р°С€РєР°). Gemini-СЃС…РµРјР° `_LlmSegment` + РїСЂРѕРјРїС‚ СЂР°СЃС€РёСЂРµРЅС‹ `hook`/
  `why_works`; `postprocess` РїСЂРѕР±СЂР°СЃС‹РІР°РµС‚ (СЃС‚Р°СЂС‹Р№ raw в†’ None, РѕР±СЂР°С‚РЅР°СЏ СЃРѕРІРјРµСЃС‚РёРјРѕСЃС‚СЊ).
  РњРѕРґРµР»СЊ: `HookOverlay` + `Segment/ClipOut.hook/why_works` (РѕРїС†. в†’ СЃС‚Р°СЂС‹Р№ РєСЌС€ РІР°Р»РёРґРµРЅ),
  `just types`. Р¤СЂРѕРЅС‚: С‚Р°Р± В«РҐСѓРєВ» (С‚РµРєСЃС‚/РІРєР»/РІРµСЃСЊ-РєР»РёРї|РїРµСЂРІС‹Рµ-N), `ClipCard` СЃС‚СЂСѓРєС‚СѓСЂРЅС‹Р№
  reasoning (С…СѓРє + В«РџРѕС‡РµРјСѓ СЃСЂР°Р±РѕС‚Р°РµС‚В» + СѓРІРµСЂРµРЅРЅРѕСЃС‚СЊ), РјРѕРє-СЂРѕСѓС‚ РґРµРјРѕРЅСЃС‚СЂРёСЂСѓРµС‚.
  **Р“СЂР°Р±Р»СЏ (РЅР°Р№РґРµРЅР° СЂРµР°Р»СЊРЅС‹Рј СЂРµРЅРґРµСЂРѕРј):** libass `BorderStyle=3` (opaque box) Р·Р°Р»РёРІР°РµС‚
  РїР»Р°С€РєСѓ С†РІРµС‚РѕРј **OutlineColour**, РќР• BackColour в†’ `box_color` РІ OutlineColour (СЃ Р°Р»СЊС„РѕР№).
  **DoD:** `tmp/dod_hook.py` вЂ” СЂРµР°Р»СЊРЅС‹Р№ ffmpeg-mp4: С…СѓРє В«Р’РћРў РџРћР§Р•РњРЈ Р’РЎР• РњРћР›Р§РђРўВ» РєРѕСЂР°Р»Р»-
  РїР»Р°С€РєР° СЃРІРµСЂС…Сѓ, СЃСѓР±С‚РёС‚СЂС‹ СЃРЅРёР·Сѓ, РЅРµ РїРµСЂРµСЃРµРєР°СЋС‚СЃСЏ (`tmp/hook_dod_frame.png`, РїРѕСЃР»Р°РЅ С„Р°СѓРЅРґРµСЂСѓ).
  `just check` Р·РµР»С‘РЅС‹Р№, +25 С‚РµСЃС‚РѕРІ (test_hook.py + postprocess passthrough).
  вљ пёЏ `clip_kind` РёР· Р±СЂРёС„Р° РќР• РґРѕР±Р°РІР»СЏР» РѕС‚РґРµР»СЊРЅС‹Рј РїРѕР»РµРј вЂ” Сѓ РЅР°СЃ СѓР¶Рµ `type: ClipType`
  (hook/emotional_peak/complete_thought/strong_quote) = clip_kind; РЅРµ РїР»РѕРґР»СЋ С‚Р°РєСЃРѕРЅРѕРјРёСЋ.
  вљ пёЏ Р›РѕРєР°Р»СЊРЅРѕ РќР•Рў РєСЌС€Р° comedy01/sample01 (data/ gitignored, РЅРµ СЃРёРЅС…СЂРѕРЅРёР·РёСЂРѕРІР°РЅ) в†’ DoD РЅР°
  СЃРёРЅС‚РµС‚РёС‡РµСЃРєРѕРј С‚С‘РјРЅРѕРј РёСЃС‚РѕС‡РЅРёРєРµ (РёР·РѕР»РёСЂСѓРµС‚ РёРјРµРЅРЅРѕ РїСЂРѕР¶РёРі С…СѓРєР°; С€СЂРёС„С‚/ASS/ffmpeg СЂРµР°Р»СЊРЅС‹Рµ).

- **T3 вЂ” СЃРѕС‡РЅС‹Рµ СЃСѓР±С‚РёС‚СЂС‹ (keyword-highlight). РЎР”Р•Р›РђРќРћ** (РєРѕРјРјРёС‚ `7da8cfb`). PURE
  `pick_keyword_positions` (С‡РёСЃР»Р° + РґР»РёРЅРЅС‹Рµ РєРѕРЅС‚РµРЅС‚РЅС‹Рµ в‰Ґ6 Р±СѓРєРІ, Р±РµР· СЃС‚РѕРї-СЃР»РѕРІ; РґРѕ 2/СЂРµРїР»РёРєСѓ вЂ”
  РёРЅР°С‡Рµ В«РїРѕРґСЃРІРµС‡РµРЅРѕ РІСЃС‘В»). compile_ass: СЏРІРЅС‹Рµ emphasis_refs > Р°РІС‚Рѕ-keyword (emphasis_color +
  emphasis_auto) > РїСѓСЃС‚Рѕ. РњРѕРґРµР»СЊ `CaptionStyle.emphasis_auto`. РџСЂРµСЃРµС‚ В«РџРѕРї-СЃР»РѕРІР°В» (preset_m,
  РєРѕСЂР°Р»Р»-emphasis Р±РµР· РєР°СЂР°РѕРєРµ) + РєРѕРЅС‚СЂРѕР» РІ StyleTab. DoD `tmp/dod_emphasis.py`: СЂРµР°Р»СЊРЅС‹Р№ mp4
  В«РЇ Р—РђР РђР‘РћРўРђР› 1000000 Р РЈР‘Р›Р•Р™В» вЂ” keyword'С‹ [1,2] РєРѕСЂР°Р»Р», РѕСЃС‚Р°Р»СЊРЅС‹Рµ Р±РµР»С‹Рµ (tmp/emph_dod_frame.png).
  **Р­РјРѕРґР·Рё descope:** libass color-emoji РЅРµРЅР°РґС‘Р¶РµРЅ РјРµР¶РґСѓ wasm-РїСЂРµРІСЊСЋ Рё ffmpeg в†’ СЃР»РѕРјР°Р» Р±С‹ WYSIWYG
  (hard-РєРѕРЅСЃС‚СЂРµР№РЅС‚). РќСѓР¶РµРЅ NotoColorEmoji РІ РѕР±Р° РјРµСЃС‚Р° + РєСЂРѕСЃСЃ-СЃС‚РµРє РІРµСЂРёС„РёРєР°С†РёСЏ вЂ” follow-up.
- **T4 вЂ” Р±Р°РіРё В§0.1. Р§РђРЎРўРР§РќРћ** (РєРѕРјРјРёС‚ `73113e3`). #4 scale: `highlight.scale` РІРµСЂС‚РёРєР°Р»СЊРЅС‹Рј
  \fscy-РїР°РїРѕРј Р°РєС‚РёРІРЅРѕРіРѕ СЃР»РѕРІР° (Р±РµР· \fscx в†’ Р±РµР· СЂРµРІСЂР°РїР°); вљ пёЏ per-word `box` РќР• СЂРµР°Р»РёР·СѓРµРј РІ
  libass (РЅРµС‚ РїСЂРёРјРёС‚РёРІР° С„РѕРЅР° РїРѕРґ СЃРїР°РЅ) вЂ” Р·Р°РґРѕРєСѓРјРµРЅС‚РёСЂРѕРІР°РЅРѕ. #9 retry РіР»Р°РІ: GET /chapters?retry=true
  + РєРЅРѕРїРєР° В«РџРѕРІС‚РѕСЂРёС‚СЊВ» (failedв†’pending). #8 РґРІРѕР№РЅС‹Рµ СЃСѓР±С‚РёС‚СЂС‹: `CaptionTrack.burn` (False в†’
  compile_ass Р±РµР· РЅРёР¶РЅРёС… СЂРµРїР»РёРє, С…СѓРє РѕСЃС‚Р°С‘С‚СЃСЏ) + С‚РѕРіР» РІ CaptionsTab вЂ” РќРђР”РЃР–РќР«Р™ СЂСѓС‡РЅРѕР№ С‚РѕРіР»
  РІРјРµСЃС‚Рѕ С…СЂСѓРїРєРѕРіРѕ CV-Р°РІС‚РѕРґРµС‚РµРєС‚Р°. #2 (РїСЂРµРІСЊСЋ-РєР°РґСЂ РїРѕСЃР»Рµ РґСЂР°РіР°) РџР РћРџРЈР©Р•Рќ вЂ” РєРѕСЃРјРµС‚РёРєР° (С„РёРЅР°Р»СЊРЅС‹Р№
  СЂРµРЅРґРµСЂ РєРѕСЂСЂРµРєС‚РµРЅ; РЅСѓР¶РµРЅ live-reframe СЌРЅРґРїРѕРёРЅС‚). +6 С‚РµСЃС‚РѕРІ.
- **T5 вЂ” СЃРѕРѕС‚РЅРѕС€РµРЅРёСЏ СЃС‚РѕСЂРѕРЅ 9:16/1:1/4:5/16:9. РЎР”Р•Р›РђРќРћ** (РєРѕРјРјРёС‚ `7d598a7`). в›” Р§РРЎРўРћ
  РїСЂРѕСЃС‚СЂР°РЅСЃС‚РІРµРЅРЅРѕ: temporal-СЃРµС‚РєР° (cuts/shots/regions/trim) РќР• РўР РћРќРЈРўРђ в†’ О”=0 РёРЅРІР°СЂРёР°РЅС‚ С†РµР»
  РїРѕ РїРѕСЃС‚СЂРѕРµРЅРёСЋ (С„Р»РµС€Рё РЅРµ РІРµСЂРЅСѓР»РёСЃСЊ). PURE `aspect_to_dims` + `fill_crop_dims` (height-limited
  РїРѕСЂС‚СЂРµС‚ = СЃР»РµР¶РµРЅРёРµ; width-limited Р»Р°РЅРґС€Р°С„С‚ = РїРѕР»РЅС‹Р№ РєР°РґСЂ). compile_ass(play_w,play_h): PlayRes
  ASS = СЂР°Р·РјРµСЂС‹ РІС‹С…РѕРґР° вЂ” РРќРђР§Р• libass Р°РЅР°РјРѕСЂС„РЅРѕ СЂР°СЃС‚СЏРЅРµС‚ СЃСѓР±С‚РёС‚СЂС‹. out_w/out_h С‡РµСЂРµР·
  render_clip/render_timeline; POST /edit/aspect; СЃРµР»РµРєС‚РѕСЂ РІ FrameTab + РґРёРЅР°РјРёС‡. Р°СЃРїРµРєС‚ РїСЂРµРІСЊСЋ.
  Р РµРіРёРѕРЅС‹ (cx) РїРµСЂРµРЅРѕСЃСЏС‚СЃСЏ вЂ” reframe РќР• РїРµСЂРµСЃС‡РёС‚С‹РІР°РµС‚СЃСЏ. DoD `tmp/dod_aspect.py`: ffprobe РІСЃРµС… 4
  РІРµСЂРЅС‹ (1080x1920/1080x1080/1080x1350/1920x1080), СЃСѓР±С‚РёС‚СЂС‹ РЅРµ СЂР°СЃС‚СЏРЅСѓС‚С‹ (tmp/aspect_1_1.png,
  aspect_16_9.png). +10 С‚РµСЃС‚РѕРІ. вљ пёЏ Engine B (РЅРµ РґРµС„РѕР»С‚) fill РѕСЃС‚Р°С‘С‚СЃСЏ 9:16; split+16:9 РІС‹СЂРѕР¶РґРµРЅ.
- **T6 вЂ” РїСЂР°Р№СЃРёРЅРі/Р»РёРјРёС‚С‹ + Supabase-ready. РЎР”Р•Р›РђРќРћ** (РєРѕРјРјРёС‚ `94c0f38`). Р‘Р•Р— СЃРµРєСЂРµС‚РѕРІ/Р°РєРєР°СѓРЅС‚РѕРІ.
  `app/billing.py` PURE: PLANS (free 2РІРёРґРµРѕ/20РјРёРЅ/watermark/720p; starter $12 20/200/1080;
  pro $29 100/1000/РїСЂРёРѕСЂРёС‚РµС‚), check_quota (РІРёРґРµРѕв†’РјРёРЅСѓС‚С‹, С‡РµСЃС‚РЅР°СЏ RU-РїСЂРёС‡РёРЅР°), resolve_plan
  (в†’free РґРµС„РѕР»С‚), current_month. Р›РёРјРёС‚С‹ РІ РљРћР”Р• (РЅРµ Р‘Р”). `db.py` usage-Р°РґР°РїС‚РµСЂ record_usage/
  get_monthly_usage (SQLite, С‚РѕС‚ Р¶Рµ РёРЅС‚РµСЂС„РµР№СЃ в†’ Postgres). `migrations/0001_init_billing.sql`:
  profiles/jobs/usage_events + RLS (TO authenticated + ownership; UPDATE USING+WITH CHECK;
  С‚СЂРёРіРіРµСЂ handle_new_user search_path=''; РїР»Р°РЅ/usage РїРёС€РµС‚ РўРћР›Р¬РљРћ СЃРµСЂРІРµСЂ). `docs/SUPABASE_SETUP.md`
  вЂ” С‡С‚Рѕ РІРїРёСЃР°С‚СЊ С„Р°СѓРЅРґРµСЂСѓ (РєР»СЋС‡Рё + РєСѓРґР°, рџ”ґ service_role РЅРµ РІ NEXT_PUBLIC, РіРµР№С‚ РєРІРѕС‚С‹, РІРµР±С…СѓРє
  Lemonв†’plan). +14 С‚РµСЃС‚РѕРІ. РџСЂРѕРІРѕРґ auth/РєРІРѕС‚С‹/РѕРїР»Р°С‚С‹ вЂ” follow-up (РЅСѓР¶РЅС‹ СЃРµРєСЂРµС‚С‹).

> вњ… **РРўРћР“ РќРћР§Р T1вЂ“T6:** РІСЃРµ С€РµСЃС‚СЊ Р·Р°РґР°С‡ Р·Р°РєСЂС‹С‚С‹ (T4 С‡Р°СЃС‚РёС‡РЅРѕ: #4 scale Р±РµР· box, #2 РїСЂРѕРїСѓС‰РµРЅ).
> just check Р·РµР»С‘РЅС‹Р№ (388 С‚РµСЃС‚РѕРІ). 7 РєРѕРјРјРёС‚РѕРІ РЅР° `feat/mvp-launch`. РћС‚С‡С‘С‚ вЂ” docs/OVERNIGHT_REPORT_2026-06-13.md.

### Р¤РёРєСЃС‹ РїРѕ Р¶РёРІРѕРјСѓ С„РёРґР±РµРєСѓ С„Р°СѓРЅРґРµСЂР° (2026-06-13, С‚Р° Р¶Рµ РІРµС‚РєР°, РєРѕРјРјРёС‚С‹ `3d41ca2`вЂ¦`9a4c41d`)
Р¤Р°СѓРЅРґРµСЂ С‚РµСЃС‚РёР» С‡РµСЂРµР· UI РЅР° **29.97fps** РІРёРґРµРѕ (3 РґР¶РѕР±Р° РІ data/, source.mp4 РµСЃС‚СЊ). 4 Р±Р°РіР°,
РЅР°Р№РґРµРЅС‹ systematic-debugging (РЅРµ СѓРіР°РґС‹РІР°Р»):
- **РљРѕСЂРµРЅСЊ В«РЅРёС‡РµРіРѕ РЅРµ СЂР°Р±РѕС‚Р°Р»РѕВ» (РґРѕ С„РёРєСЃРѕРІ):** РІРѕСЂРєРµСЂ РєСЂСѓС‚РёР» РЎРўРђР Р«Р™ РєРѕРґ (uvicorn Р±РµР· --reload,
  СЃС‚Р°СЂС‚ РґРѕ РєРѕРјРјРёС‚РѕРІ) в†’ СЃС‚Р°СЂС‹Р№ pydantic РјРѕР»С‡Р° РѕС‚Р±СЂР°СЃС‹РІР°Р» hook/burn/emphasis_auto, /edit/aspect=404.
  РџРµСЂРµР·Р°РїСѓСЃС‚РёР» РІРѕСЂРєРµСЂ+С„СЂРѕРЅС‚; РїСЂРѕРІРµСЂРёР» HTTP-СЂР°СѓРЅРґС‚СЂРёРїРѕРј (hook СЃРѕС…СЂР°РЅСЏРµС‚СЃСЏ, /ass РµРіРѕ РЅРµСЃС‘С‚). HANDOFF В§3.
- **#2 Р°СЃРїРµРєС‚ Р»РѕРјР°Р» СЃС‚СЂР°РЅРёС†Сѓ** (`3d41ca2`): PreviewPlayer Р–РЃРЎРўРљРћ Р·Р°С€РёРІР°Р» aspect-[9/16], T5-aspectClass
  РІРёСЃРµР» РЅР° РѕР±С‘СЂС‚РєРµ Р±РµР· РѕРіСЂР°РЅРёС‡РµРЅРёСЏ С€РёСЂРёРЅС‹ в†’ 16:9 = РІС‹СЃРѕС‚Р°Г—16/9 СЂР°СЃРїРёСЂР°Р»Р° РїРѕР»-СЃС‚СЂР°РЅРёС†С‹. Р¤РёРєСЃ:
  PreviewPlayer РїСЂРёРЅРёРјР°РµС‚ aspectClass Рё СЃР°Рј contain'РёС‚СЃСЏ (w-full + max-h-full + aspect).
- **#3 СЂС‹РІРєРё/С„Р»РµС€Рё РЅР°РІРµРґРµРЅРёСЏ Р’ Р Р•Р”РђРљРўРћР Р•** (`3d41ca2`, РіР»Р°РІРЅРѕРµ): editor-РїСѓС‚СЊ Р±С‹Р» РћРўР”Р•Р›Р¬РќР«Рњ
  РёРЅС„РµСЂРёРѕСЂРѕРј вЂ” detect_cuts РІ РЎР•РљРЈРќР”РђРҐ (РЅРµ frame-accurate) + sample_faces 5fps Р‘Р•Р— ASD + EMA-РїР°РЅ.
  РќР° в‰ 25fps РіСЂР°РЅРёС†С‹ СЂРµРіРёРѕРЅРѕРІ РјРёРјРѕ РєР°РґСЂР°-СЃРєР»РµР№РєРё в†’ С„Р»РµС€. REFRAME_FPS_GRID_INVARIANT В§В«РР·РІРµСЃС‚РЅРѕРµВ»
  СЌС‚Рѕ РїСЂРµРґСЃРєР°Р·С‹РІР°Р». Р¤РёРєСЃ: `resolve_regions_accurate` (reframe_cache) РїСЂРѕРІРѕРґРёС‚ editor С‡РµСЂРµР· Р•Р”РРќР«Р™
  batch `reframe_segment` (PySceneDetect frame-accurate + ASD + held-crop), РєСЌС€ РїРѕ РґРёР°РїР°Р·РѕРЅСѓ.
  DoD `tmp/dod_editor_reframe.py` РЅР° СЂРµР°Р»СЊРЅРѕРј 29.97fps: 18 РіСЂР°РЅРёС†, MAX О”=0.00000. РЈСЂРѕРє: editor Рё
  batch Р”РћР›Р–РќР« Р±С‹С‚СЊ РµРґРёРЅС‹Рј РїСѓС‚С‘Рј (РґРІР° РїСѓС‚Рё = РґРІР° Р±Р°РіР°).
- **#1 live-vs-СЂРµРЅРґРµСЂ** (`0f0c9bd`): dirty-С‡РёРї Р±С‹Р» hidden РЅР° СѓР·РєРёС… СЌРєСЂР°РЅР°С…. РџРµСЂСЃРёСЃС‚РµРЅС‚РЅС‹Р№ С…РёРЅС‚
  РЅР°Рґ С‚Р°Р±Р°РјРё + С‡РёРї В«РќР°Р¶РјРё Р РµРЅРґРµСЂВ» РІСЃРµРіРґР° РІРёРґРµРЅ.
- **#4 РїРѕРґСЃРІРµС‚РєР° СѓР±РѕРіР°СЏ** (`9a4c41d`): РїРѕ OSS-СЂРµСЃС‘СЂС‡Сѓ (clipify/captify/OpusClip) РІРёСЂСѓСЃРЅС‹Р№ СЃС‚Р°РЅРґР°СЂС‚ =
  РђРљРўРР’РќРћР• СЃР»РѕРІРѕ РІСЃРїС‹С…РёРІР°РµС‚ + pop, Р° РќР• СЃС‚Р°С‚РёС‡РЅРѕРµ СѓРіР°РґС‹РІР°РЅРёРµ keyword'РѕРІ (РјРѕСЏ T3). Р¤Р°СѓРЅРґРµСЂ РІС‹Р±СЂР°Р»
  В«СЃР»РѕРІРѕ РЅР° Р»РµС‚Сѓ + popВ». Р”РµС„РѕР»С‚ preset_a: karaoke_fill в†’ **pop** (Р°РєС‚РёРІРЅРѕРµ СЃР»РѕРІРѕ \fscy-РїРѕРґРїСЂС‹РіРёРІР°РµС‚ +
  РєРѕСЂР°Р»Р»-Р·Р°Р»РёРІРєР°), box=False. РЎС‚Р°С‚РёС‡РЅС‹Р№ keyword (T3) в†’ РѕРїС†РёСЏ, РЅРµ РґРµС„РѕР»С‚. DoD `tmp/dod_highlight.py`
  (РєР°РґСЂС‹ hl_dod_a/b.png). Р”РµРјРѕ clip_01 (job_9cae49a1103c) РѕС‡РёС‰РµРЅ apply-preset'РѕРј.
- **РЈСЂРѕРє РѕС‚ С„Р°СѓРЅРґРµСЂР° (Р·Р°С„РёРєСЃРёСЂРѕРІР°РЅ):** РЎРќРђР§РђР›Рђ РіСѓРіР»РёС‚СЊ РіРѕС‚РѕРІРѕРµ OSS, РїРѕС‚РѕРј РїРёСЃР°С‚СЊ СЃРІРѕС‘ (ASD РІР·СЏС‚ РёР·
  СЂРµРїРѕ Рё Р»СѓС‡С€Рµ СЃР°РјРѕРїРёСЃР°). just check Р·РµР»С‘РЅС‹Р№ (391 С‚РµСЃС‚), next build Р·РµР»С‘РЅС‹Р№.

### РџСЂРѕРґР°РєС€РЅ-РѕР±РѕР»РѕС‡РєР° Quip (РІРµС‚РєР° `feat/production-shell`, 2026-06-13) вЂ” РѕС‚С‡С‘С‚ `docs/PRODUCTION_REPORT_2026-06-13.md`
РђРІС‚РѕРЅРѕРјРЅР°СЏ СЃРµСЃСЃРёСЏ РїРѕ `docs/PRODUCTION_BRIEF`: РґРёР·Р°Р№РЅ-СЃРёСЃС‚РµРјР° + Р»РµРЅРґРёРЅРі + auth + РґР°С€Р±РѕСЂРґ + РѕРїР»Р°С‚Р°.
**Р‘СЂРµРЅРґ = Quip** (РїРѕРїСЂР°РІРєР° С„Р°СѓРЅРґРµСЂР°; ClipFlow вЂ” РІРЅСѓС‚СЂРµРЅРЅРµРµ РёРјСЏ СЂРµРїРѕ). **РћРїР»Р°С‚Р° = Polar.sh**
(РїРѕРїСЂР°РІРєР° С„Р°СѓРЅРґРµСЂР°, РЅРµ Lemon Squeezy РёР· Р±СЂРёС„Р°). 6 С„Р°Р·, `just check` Р·РµР»С‘РЅС‹Р№ (**409 С‚РµСЃС‚РѕРІ**).
- **D1 (`50a5ff7`)** Р”РёР·Р°Р№РЅ-Р·Р°РјРѕРє: fan-out Р°РіРµРЅС‚С‹ РїРѕ `design-md/` + **РІС‹С‚Р°С‰РёР» СЂРµР°Р»СЊРЅС‹Рµ computed-
  С‚РѕРєРµРЅС‹ quip.ink** (РѕРЅ РҐРћР›РћР”РќР«Р™ near-black + Onest 700, РЅРµ С‚С‘РїР»С‹Р№) в†’ 3 Р¶РёРІС‹С… HTML-РєРѕРЅС†РµРїС‚Р° РїРѕРєР°Р·Р°РЅС‹
  в†’ С„Р°СѓРЅРґРµСЂ РІС‹Р±СЂР°Р». `DESIGN.md` + `globals.css @theme` (Precision Dark РїРѕРґ quip.ink), Onest (РґСЂРѕРї
  Unbounded). РЎС‚Р°СЂС‹Рµ util-РёРјРµРЅР° СЃРѕС…СЂР°РЅРµРЅС‹ в†’ СЂРµРґР°РєС‚РѕСЂ РїРµСЂРµРєСЂР°СЃРёР»СЃСЏ Р±РµР· РїРѕР»РѕРјРѕРє.
- **D2** Р›РµРЅРґРёРЅРі: route-groups `(marketing)/(app)/(auth)` (С‚СѓР» РїРµСЂРµРµС…Р°Р» `/`в†’`/dashboard`);
  РїСЂРёРјРёС‚РёРІС‹ `components/ui`; 8 СЃРµРєС†РёР№ `components/marketing`; SEO (metadata/JSON-LD/sitemap/robots/
  OG `opengraph-image.tsx`). вљ пёЏ Next 16: **middlewareв†’proxy**, `cookies()` async, OG satori С‚СЂРµР±СѓРµС‚
  `display:flex` РЅР° multi-child. scroll-reveal РїРѕРґ `.js`+no-reduced-motion (РІРёРґРёРј Р±РµР· JS).
- **A1** Supabase auth **dual-mode**: `@supabase/ssr` (client/server/`proxy.ts`), РіРµР№С‚ `(app)/layout`
  С‡РµСЂРµР· `getUser()`; login/signup/callback; **СЂР°Р±РѕС‚Р°РµС‚ РѕС‚РєСЂС‹С‚Рѕ Р±РµР· РєР»СЋС‡РµР№** (dev), Р°РєС‚РёРІРёСЂСѓРµС‚СЃСЏ
  РІРїРёСЃС‹РІР°РЅРёРµРј РєР»СЋС‡РµР№. РЈРґР°Р»РёР» middleware.ts + РґРµРјРѕ /api/auth.
- **D3 (`04d67bb`)** Р”Р°С€Р±РѕСЂРґ: AppHeader+UsageMeter+RecentProjects (localStorage С‡РµСЂРµР·
  `useSyncExternalStore` вЂ” С„РёРєСЃ lint `set-state-in-effect`); РёРЅС‚РµРіСЂР°С†РёСЏ С‚СѓР»Р°+СЂРµРґР°РєС‚РѕСЂР°.
- **P1** РџСЂР°Р№СЃРёРЅРі + **Polar.sh**: `/pricing`; `app/polar.py` (Standard Webhooks РїРѕРґРїРёСЃСЊ РїРёРЅРЅСѓС‚Р° Рє
  РћР¤РР¦РРђР›Р¬РќРћРњРЈ С‚РµСЃС‚-РІРµРєС‚РѕСЂСѓ в†’ СЃРїРµРєР°-РєРѕСЂСЂРµРєС‚РЅР°; productв†’РїР»Р°РЅ; РїР°СЂСЃ); `POST /webhooks/polar`; РіРµР№С‚
  РєРІРѕС‚С‹ РІ create_job (402, **РёРЅРµСЂС‚РµРЅ Р±РµР· `BILLING_ENABLED`**); `db` profiles. +18 TDD-С‚РµСЃС‚РѕРІ.
- **POLISH (`698fdb7`)** chrome-devtools Lighthouse: a11y 88в†’**100**. Р‘РµР»С‹Р№ primary-CTA (coral-white
  С„РµР№Р»РёР» AA в†’ near-white/С‚С‘РјРЅС‹Р№, Р—РђРћР”РќРћ СЃРѕРІРїР°Р»Рѕ СЃ Р±РµР»С‹Рј CTA quip.ink), faint-РєРѕРЅС‚СЂР°СЃС‚, dlв†’div,
  badge dark-on-coral. **Lighthouse 100/100/100/100, LCP 173ms, CLS 0.00.**
- вљ пёЏ **Р¤Р°СѓРЅРґРµСЂ РІРїРёСЃС‹РІР°РµС‚ (СЃРµРєСЂРµС‚С‹ вЂ” РЅРµ Р°РіРµРЅС‚):** Supabase (РєР»СЋС‡Рёв†’auth Р°РєС‚РёРІРёСЂСѓРµС‚СЃСЏ),
  Polar (РїСЂРѕРґСѓРєС‚С‹+РІРµР±С…СѓРє+`BILLING_ENABLED`), рџ”ґ Р·Р°РјРµРЅРёС‚СЊ РїР»РµР№СЃС…РѕР»РґРµСЂ `X-User-Id` РЅР° РІР°Р»РёРґР°С†РёСЋ
  Supabase-JWT РїРµСЂРµРґ РїСЂРѕРґРѕРј, РґРµРїР»РѕР№ Vercel+Modal, РґРѕРјРµРЅ. Р›РµРЅРґРёРЅРі РќР• РЅР° quip.ink РґРѕ РїСЂРѕРІРµСЂРєРё auth.
- вљ пёЏ **i18n:** РЅРѕРІС‹Рµ РїРѕРІРµСЂС…РЅРѕСЃС‚Рё (Р»РµРЅРґРёРЅРі/auth/РґР°С€Р±РѕСЂРґ) вЂ” РђРќР“Р›РР™РЎРљРР•; СЏРґСЂРѕ СЂРµРґР°РєС‚РѕСЂР°/SourceForm вЂ”
  Р РЈРЎРЎРљРћР• (РЅРµ Р»РѕРјР°Р»). English-ify СЏРґСЂР° вЂ” follow-up.

### Р¤РёРґР±РµРє-С„РёРєСЃС‹ С„Р°СѓРЅРґРµСЂР° (С‚Р° Р¶Рµ РІРµС‚РєР° `feat/production-shell`, 2026-06-13, РІРµС‡РµСЂ) вЂ” РїРѕРґС‚РІРµСЂР¶РґРµРЅРѕ С„Р°СѓРЅРґРµСЂРѕРј
Р’РµСЂРЅСѓР»СЃСЏ СЃ 3 РїСЂРѕР±Р»РµРјР°РјРё, СЂР°Р·РѕР±СЂР°РЅС‹ systematic-debugging (РЅРµ СѓРіР°РґС‹РІР°Р»):
- **Reframe В«СЂРµР·РєРѕ РґРІРёРіР°РµС‚ РєР°РјРµСЂСѓ/С„Р»РµС€РёВ» (`ebfc3dc`):** РґРёР°РіРЅРѕР· вЂ” РќР• СЃР»РѕРјР°РЅРЅС‹Р№ РєРѕРґ (frame-accurate +
  РЅР°СЃС‚РѕСЏС‰РёР№ ASD), Р° РРќРҐР•Р Р•РќРўРќР«Р™ РґРёР·Р°Р№РЅ: Р¶С‘СЃС‚РєРёР№ СЃР±СЂРѕСЃ С†РµРЅС‚СЂР° РєСЂРѕРїР° РЅР° РљРђР–Р”РћР™ СЃРєР»РµР№РєРµ в†’ С‚РµР»РµРїРѕСЂС‚ РЅР°
  РјРѕРЅС‚Р°Р¶РЅРѕРј РІРёРґРµРѕ (СЃРІРµСЂРёР» СЃ SamurAIGPT вЂ” Сѓ РЅРёС… РЅРµРїСЂРµСЂС‹РІРЅС‹Р№ EMA Р±РµР· СЃРєР»РµРµРє). Р¤РёРєСЃ **РёРЅРІР°СЂРёР°РЅС‚-Р±РµР·РѕРїР°СЃРЅС‹Р№**
  (REFRAME_FPS_GRID С†РµР»): С†РµРЅС‚СЂ РµРґРµС‚ РќР•РџР Р•Р Р«Р’РќРћ РїРѕРїРµСЂС‘Рє РїРѕРґСЂСЏРґ РёРґСѓС‰РёС… fill-С€РѕС‚РѕРІ вЂ”
  `_track_trajectory(init_cx=prev_fill_end_cx)`; `plan_regions` С‚СЏРЅРµС‚ `prev_fill_end_cx` (СЃР±СЂРѕСЃ РЅР°
  fit/split). Р“СЂР°РЅРёС†С‹ СЂРµР¶РёРјР° fill/fit РќР• С‚СЂРѕРЅСѓС‚С‹ в†’ С„Р»РµС€Рё РЅРµРІРѕР·РјРѕР¶РЅС‹. +1 continuity-С‚РµСЃС‚ (84 reframe).
- **Р РµРґР°РєС‚РѕСЂ: РїСЂРµРІСЊСЋ РєР°РґСЂР° РїСЂС‹РіР°РµС‚, РЅР° РіР»Р°РІРЅРѕР№ РЅРµС‚ (`b571b55`):** РџРћР§Р•РњРЈ вЂ” Р”Р’Рђ Р РђР—РќР«РҐ РїР»РµРµСЂР°: РіР»Р°РІРЅР°СЏ
  РёРіСЂР°РµС‚ Р“РћРўРћР’Р«Р™ mp4 (reframe РІРїРµС‡С‘РЅ ffmpeg'РѕРј); СЂРµРґР°РєС‚РѕСЂ РёРіСЂР°РµС‚ РРЎРҐРћР”РќРРљ + РєСЂРѕРїРёС‚ РќРђ Р›Р•РўРЈ РІ Р±СЂР°СѓР·РµСЂРµ
  (РіСЂСѓР±РѕРµ РїСЂРёР±Р»РёР¶РµРЅРёРµ). Р”РІРµ РїСЂРёС‡РёРЅС‹, РѕР±Рµ РїРѕС„РёРєС€РµРЅС‹: (1) `cxAt` Р±С‹Р»Р° РЎРўРЈРџР•РќР¬РљРћР™ в†’ Р»РёРЅРµР№РЅР°СЏ РёРЅС‚РµСЂРїРѕР»СЏС†РёСЏ;
  (2) РєСЂРѕРї РґРІРёРіР°Р»СЃСЏ С‚РѕР»СЊРєРѕ РЅР° `timeupdate` ~4Р“С† в†’ CSS-transition object-position 300ms (fill+split) в†’
  РїР»Р°РІРЅС‹Р№ РіР»Р°Р№Рґ. РџСЂРµРІСЊСЋ = live (re-render РЅРµ РЅСѓР¶РµРЅ РґР»СЏ РіР»Р°РґРєРѕСЃС‚Рё; continuity-СЂРµРіРёРѕРЅС‹ Р±Р°РєР°СЋС‚СЃСЏ re-render'РѕРј).
  вљ пёЏ **РќР°С…РѕРґРєР°:** `build_fill_crop_expr` РІ Р Р•РќР”Р•Р Р• С‚РѕР¶Рµ piecewise-CONST (СЃС‚СѓРїРµРЅСЊРєР° ~3% С€Р°РіРё). Р¤Р°СѓРЅРґРµСЂ
  РїСЂРёРЅСЏР» (РјРµР»РєРѕ). РСЃС‚РёРЅРЅРѕ Р»РёРЅРµР№РЅС‹Р№ РїР°РЅ РІ СЃРєР°С‡Р°РЅРЅРѕРј С„Р°Р№Р»Рµ в†’ СЃРґРµР»Р°С‚СЊ expr piecewise-LINEAR (РёРЅРІР°СЂРёР°РЅС‚ РЅРµ
  С‚СЂРѕРіР°РµС‚, С‚РѕР»СЊРєРѕ cx РІРЅСѓС‚СЂРё fill-СЂРµРіРёРѕРЅР°) вЂ” **follow-up РїРѕ Р·Р°РїСЂРѕСЃСѓ С„Р°СѓРЅРґРµСЂР°.**
- **Editor В«РїРµСЂРІР°СЏ Р·Р°РіСЂСѓР·РєР° РѕС€РёР±РєР°, РїРѕС‚РѕРј retry СЂР°Р±РѕС‚Р°РµС‚В» + 404 /terms /privacy:** 404 = СѓСЃС‚Р°СЂРµРІС€РёР№
  prod-Р±РёР»Рґ (РІ РєРѕРґРµ СЃС‚СЂР°РЅРёС†С‹ Р•РЎРўР¬). CORS/ERR_FAILED = РІРѕСЂРєРµСЂ РЅРµ СѓСЃРїРµР» РїРѕРґРЅСЏС‚СЊСЃСЏ (torch/MediaPipe ~СЃРµРє).
  Р¤РёРєСЃ: `ClipEditorScreen` Р°РІС‚Рѕ-СЂРµС‚СЂР°РёС‚ Р·Р°РіСЂСѓР·РєСѓ (4 СЂР°Р·Р°, backoff) РІРјРµСЃС‚Рѕ РјРіРЅРѕРІРµРЅРЅРѕР№ РѕС€РёР±РєРё.
- **Р”РёР·Р°Р№РЅ (`2aef9f6`):** Р°РіРµРЅС‚ СЃ РґРёР·Р°Р№РЅ-СЃРєРёР»Р»Р°РјРё (frontend-design/ui-ux-pro-max/taste/design-review)
  СЃРѕР±СЂР°Р» РґРѕСЃС‚СѓРїРЅС‹Рµ РїСЂРёРјРёС‚РёРІС‹ **Checkbox/Switch/Select/IconButton** + РїСЂРёРјРµРЅРёР» РїРѕ РіСЂРёРґСѓ/РєР°СЂС‚РѕС‡РєР°Рј/С‚Р°Р±Р°Рј
  (РіРѕР»С‹Рµ С‡РµРєР±РѕРєСЃС‹ в†’ СЃС‚РёР»РёР·РѕРІР°РЅРЅС‹Рµ, РєРЅРѕРїРєРё-СЃСЃС‹Р»РєРё в†’ РЅР°СЃС‚РѕСЏС‰РёРµ РєРЅРѕРїРєРё; Button +`accent` РєРѕСЂР°Р»Р»-РІР°СЂРёР°РЅС‚).
  Р”РѕРґРµР»Р°Р» HookTab + РїРѕС‡РёРЅРёР» SSR-РІР°СЂРЅРёРЅРі `recent.ts` (getServerSnapshot СЃС‚Р°Р±РёР»СЊРЅС‹Р№ `[]`). Lighthouse
  Р»РµРЅРґРёРЅРіР° 100Г—4 С†РµР».
- вљ пёЏ **Р’РѕСЂРєРµСЂ РїРµСЂРµР·Р°РїСѓС‰РµРЅ РјРЅРѕР№** (РЅРѕРІС‹Р№ reframe-РєРѕРґ, :8000). РљСЌС€ `data/<job>/analysis/acc_*.json` РґР»СЏ
  `job_9cae49a1103c` РїРѕС‡РёС‰РµРЅ в†’ re-render РїРѕРєР°Р·С‹РІР°РµС‚ reframe-С„РёРєСЃ Р·Р° $0 (С‚СЂР°РЅСЃРєСЂРёРїС‚/СЃРµРіРјРµРЅС‚С‹ РєСЌС€РёСЂРѕРІР°РЅС‹).
- вљ пёЏ РћС‚РєСЂС‹С‚Рѕ РґР»СЏ СЃР»РµРґ. СЃРµСЃСЃРёРё: Р»РёРЅРµР№РЅС‹Р№ СЂРµРЅРґРµСЂ-expr (РїРѕ Р·Р°РїСЂРѕСЃСѓ), Р¶РёРІРѕР№ auth+РѕРїР»Р°С‚Р° (Р¶РґС‘Рј РєР»СЋС‡Рё Supabase/
  Polar), JWT-РІР°Р»РёРґР°С†РёСЏ РіРµР№С‚Р° (Р·Р°РјРµРЅР° X-User-Id), Р·Р°РїРёСЃСЊ usage РІ РїР°Р№РїР»Р°Р№РЅРµ, i18n СЏРґСЂР°.

### Р”РёР·Р°Р№РЅ-С‡РёСЃС‚РєР° РІРёРґРµРѕ-С„Р»РѕСѓ + С„РёРЅР°Р»СЊРЅС‹Р№ РїСЂР°Р№СЃРёРЅРі (РІРµС‚РєР° `feat/production-shell`, 2026-06-13)
Р—Р°РїСЂРѕСЃ С„Р°СѓРЅРґРµСЂР°: В«С„Р»РѕСѓ СЂР°Р±РѕС‚С‹ СЃ РІРёРґРµРѕ РІС‹РіР»СЏРґСЏС‚ СѓР±Р»СЋРґСЃРєРё вЂ” РіР»РѕР±Р°Р»СЊРЅС‹Р№ СЂРµС„Р°РєС‚РѕСЂ РґРёР·Р°Р№РЅР°В», РґРёР·Р°Р№РЅ-СЃРєРёР»Р»Р°РјРё.
Р—Р°С‚РµРј вЂ” РІРЅРµРґСЂРёС‚СЊ С„РёРЅР°Р»СЊРЅС‹Р№ РїСЂР°Р№СЃРёРЅРі (РєСЂРµРґРёС‚-РјРѕРґРµР»СЊ). 3 РєРѕРјРјРёС‚Р°.
- **Р”РёР·Р°Р№РЅ (`5b8db44`)**: Р°СѓРґРёС‚ СЂРµРґР°РєС‚РѕСЂР°/РґР°С€Р±РѕСЂРґР° С‡РµСЂРµР· Playwright + СЃРєРёР»Р»С‹ ui-ux-pro-max/frontend-design.
  РљРћР Р•РќР¬ В«СѓР±Р»СЋРґСЃРєРѕСЃС‚РёВ» = СЃРёСЃС‚РµРјРЅС‹Р№ Р°РЅС‚Рё-РїР°С‚С‚РµСЂРЅ `bg-accent/10..25` РґР»СЏ active/selected: РєРѕСЂР°Р»Р» #ff5a3d
  РЅР° 10-25% Р°Р»СЊС„С‹ РїРѕРІРµСЂС… near-black = РіСЂСЏР·РЅРѕ-Р±РѕСЂРґРѕРІРѕРµ РїСЏС‚РЅРѕ (РЅР°СЂСѓС€Р°РµС‚ DESIGN.md В«РєРѕСЂР°Р»Р» СЃРєСѓРї, СЌР»РµРІР°С†РёСЏ =
  РїРѕРІРµСЂС…РЅРѕСЃС‚Рё+С…Р°Р№СЂР»Р°Р№РЅС‹В»). Р›РµС‡РµРЅРёРµ: РЅРµР№С‚СЂР°Р»СЊРЅР°СЏ РїСЂРёРїРѕРґРЅСЏС‚Р°СЏ РїРѕРІРµСЂС…РЅРѕСЃС‚СЊ (`surface-3`) + С‡С‘С‚РєРёР№ РєРѕСЂР°Р»Р» РІ
  С‚РµРєСЃС‚Рµ/СЂР°РјРєРµ/СЂРµР»СЊСЃРµ (РєР°Рє CapCut/Descript), РќР• РїРѕР»СѓРїСЂРѕР·СЂР°С‡РЅР°СЏ Р·Р°Р»РёРІРєР°. Р—Р°С‚СЂРѕРЅСѓС‚Рѕ 17 С„СЂРѕРЅС‚-С„Р°Р№Р»РѕРІ:
  С‚Р°Р±-Р±Р°СЂ СЂРµРґР°РєС‚РѕСЂР°, Р°РєС‚РёРІРЅР°СЏ СЂРµРїР»РёРєР° (РєРѕСЂР°Р»Р»-СЂРµР»СЊСЃ), FrameTab/HookTab/PresetStrip/EditorHeader
  (ad-hoc РєРѕСЂР°Р»Р»-РєРЅРѕРїРєРё в†’ `Button`), JobProgress/StatusBadge/ErrorPanel (РѕС€РёР±РєР° РєРѕСЂР°Р»Р»в†’`bad`), Button
  (disabled accent в†’ РЅРµР№С‚СЂ. РїРѕРІРµСЂС…РЅРѕСЃС‚СЊ, Р±С‹Р» РјСѓС‚РЅС‹Р№ В«СЃР»РѕРјР°РЅРЅС‹Р№В» CTA В«РќР°СЂРµР·Р°С‚СЊВ»). Р Р°РґРёСѓСЃС‹ СЂРµРґР°РєС‚РѕСЂР° xlв†’lg.
  РЇР·С‹Рє: РґР°С€Р±РѕСЂРґ-С€РµР»Р» Р±С‹Р» EN РїРѕРІРµСЂС… СЂСѓСЃСЃРєРѕРіРѕ РёРЅСЃС‚СЂСѓРјРµРЅС‚Р° (РјРµС€Р°РЅРёРЅР°) в†’ СЂСѓСЃРёС„РёС†РёСЂРѕРІР°РЅ (Р»РµРЅРґРёРЅРі РЅРµ С‚СЂРѕРіР°Р»).
  РЈСЂРѕРє: РїСЂРёРјРёС‚РёРІС‹ (Checkbox/Switch/Button) Р±С‹Р»Рё РџР РђР’РР›Р¬РќР«Р• (solid coral); Р±РѕР»РµР·РЅСЊ вЂ” ad-hoc РєР»Р°СЃСЃС‹ РІ РѕР±С…РѕРґ.
- **РџСЂР°Р№СЃРёРЅРі Р±СЌРєРµРЅРґ (`616e895`, TDD)**: РєСЂРµРґРёС‚-РјРѕРґРµР»СЊ РІ `billing.py` (РёСЃС‚РѕС‡РЅРёРє РїСЂР°РІРґС‹). 1 РєСЂРµРґРёС‚ = 1 РІРёРґРµРѕ
  в‰¤60 РјРёРЅ; РґР»РёРЅРЅРµРµ в†’ `credits=max(1,ceil(РјРёРЅ/60))`. Free $0/2РєСЂ/в‰¤30РјРёРЅ/wm/720; Starter $10/10РєСЂ/1080;
  Pro $25/30РєСЂ/РїСЂРёРѕСЂРёС‚РµС‚; PAYG $2/РєСЂРµРґРёС‚ (РЅРµ СЃРіРѕСЂР°РµС‚). `check_quota` РІРѕР·РІСЂР°С‰Р°РµС‚ СЂРµС€РµРЅРёРµ + split СЃРїРёСЃР°РЅРёСЏ
  (from_monthly/from_payg вЂ” С‚СЏРЅРµС‚ РјРµСЃСЏС‡РЅС‹Р№, Р·Р°С‚РµРј PAYG). `db.py`: profiles.payg_credits + usage_events.credits
  (+ALTER-РјРёРіСЂР°С†РёСЏ СЃС‚Р°СЂС‹С… SQLite) + get_profile/add_payg_credits. `polar.py`: parse_payg_order (СЂР°Р·РѕРІС‹Р№
  Р·Р°РєР°Р·в†’РєСЂРµРґРёС‚С‹) + metadata.plan-С„РѕР»Р±СЌРє. `main.py`: РіРµР№С‚ РЅР° РєСЂРµРґРёС‚С‹+PAYG, РІРµР±С…СѓРє РѕР±СЂР°Р±Р°С‚С‹РІР°РµС‚ PAYG.
  migrations/0002_credits.sql. **421 С‚РµСЃС‚ Р·РµР»С‘РЅС‹Р№.**
- **РџСЂР°Р№СЃРёРЅРі С„СЂРѕРЅС‚ (`616e895`+`85b572e`)**: `lib/plans.ts` Р·РµСЂРєР°Р»РёС‚ billing; `lib/polar.ts` PAYG-checkout +
  Polar product IDs Р·Р°РґРѕРєСѓРјРµРЅС‚РёСЂРѕРІР°РЅС‹ (dual-modeв†’/signup). `PricingCards` СЂРµРґРёР·Р°Р№РЅ (СЃРєРёР»Р»С‹ taste/emil):
  hairline-РєР°СЂС‚РѕС‡РєРё, Pro=RECOMMENDED (Р±РµР№РґР¶+СЂРёРЅРі), PAYG-РїРѕР»РѕСЃР°. РљРѕРїРёСЂР°Р№С‚/FAQ/Comparison РїРѕРґ РєСЂРµРґРёС‚С‹,
  em-dash РІС‹С‡РёС‰РµРЅ. **Lighthouse /pricing desktop a11y/BP/SEO/agentic = 100/100/100/100.**
  вљ пёЏ Р“СЂР°Р±Р»СЏ: DESIGN.md РІСЂР°Р» В«white-on-coral РїСЂРѕС…РѕРґРёС‚ AAВ» вЂ” #fff РЅР° #ff5a3d = 3.09:1 (С„РµР№Р» <18px). Р¤РёРєСЃ:
  СЂРµРєРѕРјРµРЅРґРѕРІР°РЅРЅС‹Р№ CTA в†’ `primary` (near-white), Р±РµР№РґР¶ в†’ near-black РЅР° РєРѕСЂР°Р»Р»Рµ. Р“Р»РѕР±Р°Р»СЊРЅС‹Р№ accent-Button
  (white-on-coral, РІ СЂРµРґР°РєС‚РѕСЂРµ) РќР• С‚СЂРѕРіР°Р» вЂ” РЅРµ РЅР° Р°СѓРґРёСЂСѓРµРјС‹С… СЃС‚СЂР°РЅРёС†Р°С… + Р±СЂРµРЅРґРѕРІРѕРµ СЂРµС€РµРЅРёРµ С„Р°СѓРЅРґРµСЂР°;
  РЅРѕ СЌС‚Рѕ Р Р•РђР›Р¬РќР«Р™ app-wide a11y-РґРѕР»Рі (Р РµРЅРґРµСЂ/РџСЂРёРјРµРЅРёС‚СЊ/РќР°СЂРµР·Р°С‚СЊ) вЂ” С„РёРєСЃРёС‚СЊ РµСЃР»Рё РІР°Р¶РЅР° СЃС‚СЂРѕРіР°СЏ AA РІ РїСЂРѕРґСѓРєС‚Рµ.
- вљ пёЏ Р¤Р°СѓРЅРґРµСЂСѓ: (1) Founding Pass $5 вЂ” СЂРµС€РёС‚СЊ Р§РўРћ РґР°С‘С‚ (TODO РІ billing.py; РІ UI РЅРµ РїРѕРєР°Р·Р°РЅ); (2) Polar
  hosted-checkout СЃСЃС‹Р»РєРё РІ `NEXT_PUBLIC_POLAR_CHECKOUT_*` + `POLAR_PRODUCT_PAYG`; (3) С‡РёСЃР»Р° РЅР° СЃР°Р№С‚Рµ
  Р·РµСЂРєР°Р»СЏС‚ `billing.py` вЂ” РјРµРЅСЏС‚СЊ РІ РћР‘РћРРҐ РјРµСЃС‚Р°С….

### Р‘РѕРµРІРѕР№ РІРѕСЂРєРµСЂ Modal + i18n С„СЂРѕРЅС‚Р° (РІРµС‚РєР° `feat/modal-boevoy` в†’ main, 2026-06-14) вЂ” РѕС‚С‡С‘С‚ `docs/OVERNIGHT_MODAL_REPORT_2026-06-14.md`
РђРІС‚РѕРЅРѕРјРЅР°СЏ РЅРѕС‡СЊ: (1) Р±РѕРµРІРѕР№ РІРѕСЂРєРµСЂ РЅР° Modal, (2) i18n СЏРґСЂР° + РїРѕР»РёСЂРѕРІРєР° С„СЂРѕРЅС‚Р°. `just check` Р·РµР»С‘РЅС‹Р№
(459 С‚РµСЃС‚РѕРІ), `next build` Р·РµР»С‘РЅС‹Р№, СЃРјРµСЂР¶РµРЅРѕ РІ main Рё Р·Р°РїСѓС€РµРЅРѕ.
- **РЎС‚РµР№С‚-РјРёРіСЂР°С†РёСЏ dual-mode (disk-first, cloud-fallback):** Р»РѕРєР°Р»СЊРЅРѕ SQLite+РґРёСЃРє (Phase 0 С†РµР»);
  РЅР° Modal вЂ” Supabase Postgres (`app/cloud_state.py`, PostgREST/service_role, СЃС…РµРјР° РІ РїСЂРѕРґРµ ref
  `qiagetbnsssvbiowuxpp`) + Cloudflare R2 (`app/storage.py`, public-РёР»Рё-presigned URL). РќРѕРІС‹Рµ РјРѕРґСѓР»Рё:
  `cloud_state`/`storage`/`artifacts`/`dispatch`; `db`/`store`/`run`/`tasks`/`main` СЃРґРµР»Р°РЅС‹ dual-mode.
  Р“РµР№С‚ РѕР±Р»Р°РєР° = `STORAGE_BACKEND=r2`+Supabase-РєР»СЋС‡Рё. row_to_wire: http-URL РєР°Рє РµСЃС‚СЊ, РѕС‚РЅРѕСЃРёС‚РµР»СЊРЅС‹Р№в†’`media/`.
- **Modal split (0 GPU, BENCHMARKS В§7):** `deploy/modal/worker.py` = App `quip-worker` (web asgi
  scale-to-zero + `run_job` + `render_job`). `POST /jobs` в†’ `run_job.spawn` (РќР• BackgroundTask вЂ”
  scale-to-zero СѓР±РёР» Р±С‹ РЅР°СЂРµР·РєСѓ). РЎРўРђРўРРљ-ffmpeg 7.0.2 (John Van Sickle, РќР• apt вЂ” debian-ffmpeg РєСЂР°С€РёС‚ crop).
- **рџ”‘ Р”РћРљРђР—РђРќРћ РЅР° Modal Р±РµР· СЃРµРєСЂРµС‚РѕРІ:** `deploy/modal/proof_ffmpeg.py` (run `ap-vM71RIwLjviyC0R3kniQ3U`) вЂ”
  СЃС‚Р°С‚РёРє-ffmpeg СЂРµРЅРґРµСЂРёС‚ РЅР°С€ crop-РіСЂР°С„ РІ РІР°Р»РёРґРЅС‹Р№ mp4 (h264 1080Г—1920 5.04s). Р РёСЃРє в„–1 РґРµРїР»РѕСЏ РїРѕР±РµР¶РґС‘РЅ.
- **вљ пёЏ Live-РґРµРїР»РѕР№ Р¤РђРЈРќР”Р•Р РЈ (1 С€Р°Рі):** Р°РіРµРЅС‚ РќР• СЃРѕР·РґР°С‘С‚ С‡СѓР¶РёРµ РєСЂРµРґС‹ (РїСЂР°РІРёР»СЊРЅРѕ вЂ” security boundary).
  `modal secret create quip-worker --from-dotenv .env STORAGE_BACKEND=r2 BILLING_ENABLED=true LLM_PROVIDER=gemini TRANSCRIPTION_PROVIDER=deepgram --force`
  в†’ `modal deploy deploy/modal/worker.py` в†’ РІС‹РґР°СЃС‚ web-URL. e2e Р¶РґС‘С‚ СЌС‚РѕРіРѕ.
- **i18n:** СЏРґСЂРѕ СЂРµРґР°РєС‚РѕСЂР°/РіСЂРёРґ/С€РµР»Р» РїРµСЂРµРІРµРґРµРЅС‹ EN (22 С„Р°Р№Р»Р°; Р»РѕРіРёРєР°/WYSIWYG С†РµР»С‹; РєРѕРјРјРµРЅС‚С‹ РєРѕРґР° EN РЅРµ РґРµР»Р°Р»).
- **Р¤РёРєСЃ /pricing:** `prefetch={false}` РЅР° Polar-СЃСЃС‹Р»РєР°С… (СѓС€Р»Рё 6 CORS-РѕС€РёР±РѕРє RSC-prefetch).
- **вљ пёЏ Vercel-РЅР°С…РѕРґРєР°:** РІРёРґРёРјС‹Р№ Vercel-РїСЂРѕРµРєС‚ `quip` СЃРѕР±РёСЂР°РµС‚СЃСЏ РёР· Р›Р•РќР”РРќР“-СЂРµРїРѕ `Shorts-Automatizator`
  (РїСЂР°РІРёР»Рѕ #10!), Р° РќР• РёР· `clipflow/apps/web`. РџСѓС€ РІ clipflow СЃР°Рј РїРѕ СЃРµР±Рµ app.quip.ink РќР• РґРµРїР»РѕРёС‚;
  РїСѓС‚СЊ РґРµРїР»РѕСЏ РёРЅСЃС‚СЂСѓРјРµРЅС‚Р° РѕС‚РґРµР»СЊРЅС‹Р№/РЅРµРІРёРґРёРј С‚РѕРєРµРЅСѓ. Vercel-env РќР• С‚СЂРѕРіР°Р»; `NEXT_PUBLIC_WORKER_URL`
  СЃС‚Р°РІРёС‚ С„Р°СѓРЅРґРµСЂ РЅР° РїСЂР°РІРёР»СЊРЅРѕРј РїСЂРѕРµРєС‚Рµ РїРѕСЃР»Рµ Modal-РґРµРїР»РѕСЏ.

### Стилизация хука + лаги/баги редактора (ветка feat/hook-styling-editor-lag, 2026-06-15)
Запрос фаундера: паритет стиля ХУКА с субтитрами + починить лаги/баги редактора (systematic-debugging,
баги непостоянные → инструментировать). OSS-ресёрч (Submagic/OpusClip/libass-wasm) перед кодом. Спека:
`docs/superpowers/specs/2026-06-15-hook-styling-and-editor-lag-design.md`. Коммит `98ffa63`.
- **A — хук как субтитры:** `HookOverlay.animation` (none/pop/fade/bounce, `just types`) + вход-анимация
  в `build_hook_event`; `HookTab` — галерея хук-пресетов (`lib/hookPresets.ts`, отдельная от caption —
  как Submagic hookTitle) + контролы стиля (цвет/плашка/контур/шрифт/размер/позиция/UPPERCASE) + драг на
  видео; общие `ColorField`/`DebouncedSlider` → `StyleControls.tsx` (DRY со StyleTab).
- **B instant preview (#4/#3):** `lib/assStyle.ts` локально переписывает ASS `Style:`-строки (мгновенный
  libass), PATCH дебаунсится ~300мс в фоне, сервер реконсилит ASS. Инвариант превью==экспорт цел (экспорт
  всегда из Python-ASS; Style-строки кросс-чекнуты байт-в-байт с Python). Драг субтитров/хука едет живьём.
- **B libass (#1):** форс `setCurrentTime` после `setTrack` (фикс stale-кадра на ПАУЗЕ — правка стиля не
  обновлялась) + пропуск пустого ASS. Корень: rAF-троттл на паузе не двигал время → нет редроу.
- **B пресет (#2):** `apply_preset` сохраняет ручную позицию (`margin_v`/`alignment`) — пресет больше не
  «прыгает» вверх.
- **B долговечность (#5, страх фаундера «всё снеслось»):** flush pending-правок ПЕРЕД навигацией/trim/
  aspect/preset + `pagehide`/`visibilitychange`/unmount (keepalive-PATCH переживает unload) + индикатор
  «Сохраняю…». Уход на «Все клипы»/reload после долгой сессии больше НЕ теряет правки.
- **B навигация (#6):** «Все клипы» открывает грид джоба напрямую (фикс флеша idle-«Создать клипы» при
  `?job=` до `start()`; reset чистит `?job=`).
- DoD: `just check` зелёный (550 pytest), `next build` зелёный. ⚠️ Визуал (libass рисует хук-анимацию/
  стиль, драг, instant) — судит фаундер глазами (libass автоматом не верифицируется).

### Сессия 2026-06-15 (вечер): video-speedup + ПЕРЕПИСАН upload (direct→R2) + правки
Продолжение той же сессии (hook styling + editor lag — запись выше). Всё на main, задеплоено
(worker на Modal: `modal deploy deploy/modal/worker.py`; frontend на Vercel: push в main).

**Editor video-load ускорен (коммит `b8d4d4c`):** редактор грузил ВЕСЬ source.mp4 (50-160МБ, иногда
AV1 = софт-декод в браузере) ради 30с-окна; на проде source шёл presigned-origin БЕЗ CDN.
- preview-прокси: `build_preview_proxy`/`build_preview_cmd` (stage0) → ≤720p H.264 faststart;
  генерится в `run_pipeline` (кэш по наличию `preview.mp4`), льётся в R2 (`storage.upload_preview`).
  Рендер клипов — из ПОЛНОГО source (качество не падает). Замер: AV1 58МБ→H.264 29МБ, H.264 99МБ→28МБ,
  faststart=True. Главный выигрыш — AV1→H.264 (hw-декод) + faststart + меньше размер.
- CDN для source/preview: `source_read_url`/`preview_read_url`/`_r2_read_url` отдают cdn.quip.ink
  (R2_PUBLIC_URL) вместо presigned-origin (кэш на краю, без протухания). `preview_read_url`
  head_object → нет прокси (старый джоб) фолбэк на source.
- Эндпоинты: `GET /jobs/{job}/preview.mp4` (фолбэк на source); `GET .../source.mp4` теперь тоже CDN.
- Фронт: редактор грузит `jobs/<job>/preview.mp4`. config: `preview_height=720`, `preview_crf=30`.

**Vercel Analytics (коммит `5056621`):** `<Analytics/>` (`@vercel/analytics/next`) в root layout —
НИЧЕГО не рисует, шлёт pageview/события в Vercel. ⚠️ ФАУНДЕРУ: ВКЛЮЧИТЬ Analytics в дашборде проекта
Vercel (вкладка Analytics → Enable), иначе данные не собираются. В dev — no-op.

**Upload ПЕРЕПИСАН на direct browser→R2 (коммит `d12a06c`) — ГЛАВНОЕ изменение архитектуры:**
- Проблема: большие видео через ОДИН долгий POST на Modal web-функцию РВАЛИСЬ. Эволюция диагноза:
  (1) 900s-таймаут web-функции (стрял на 100%+500) → стрим `upload_source` + web timeout 3600
  (коммит `abe450f`); (2) всё равно рвалось — оборванный (truncated) multipart → сервер 400, браузер
  показывал как CORS «No ACAO header»/ERR_FAILED. ДОКАЗАНО тестами: оборванный POST→400; presigned
  PUT→R2 200+readback; CORS-конфиг корректен (401 несёт ACAO); Modal-лимит=4GiB (не размер).
  КОРЕНЬ — фрагильность ОДНОГО долгого запроса через Modal web на больших файлах.
- Фикс: браузер грузит файл ПРЯМО в R2 (Cloudflare edge, надёжно), МИНУЯ Modal web-функцию:
  - `storage.presigned_put_url` (SigV4 path-style как `_r2_client`) + `storage.set_upload_cors`.
  - `POST /jobs/upload-url` → {id, put_url} в cloud | {local:true} в dev (→ старый multipart-путь).
  - `POST /jobs/{id}/upload-complete` → `db.insert_job` + spawn `upload_job` (качает source из R2 —
    путь не изменился). Джоб создаётся ТУТ (после успешного PUT) → отменённая загрузка не оставляет
    «queued»-сироту. Квота `_enforce_quota` гейтится в upload-url И в upload-complete (security review).
  - Фронт `createUploadJob`: upload-url → PUT в R2 (XHR ради progress+abort) → upload-complete;
    local-фолбэк (multipart POST /jobs/upload) сохранён для dev.
  - `deploy/modal/r2_setup.py` — one-off: проверка presigned PUT + симуляция браузерного CORS-флоу.
- ⚠️⚠️ ТРЕБУЕТ CORS-правило на R2-бакете (токен воркера БЕЗ bucket-admin → ставит ФАУНДЕР в дашборде
  Cloudflare R2 → bucket `quip` → Settings → CORS Policy). **СДЕЛАНО фаундером 2026-06-15.** JSON
  правила — в `deploy/modal/r2_setup.py` (AllowedOrigins app.quip.ink + *.vercel.app + localhost,
  Methods PUT/GET/HEAD). Без CORS браузерный PUT блокируется. Проверено: preflight 204+ACAO, PUT 200+ACAO.

**Security review (коммит `4a07518`):** `/upload-complete` теперь тоже `_enforce_quota` (не только в
upload-url) — спавн платной джобы без гейта недопустим. IDOR по job_id закрыт дизайном (серверный
случайный uuid + per-job presigned PUT → чужой id не угадать).

**Прочие фиксы:**
- Заброшенные загрузки (коммит `706051a`): `createUploadJob` принимает `AbortSignal`; dashboard абортит
  на reset/unmount/новый-сабмит + double-submit guard. Уход во время загрузки не плодит сирот/гонок.
- Vercel build break (коммит `ee31a12`): я реверетнул root `package.json` (от analytics) БЕЗ ресинка
  lockfile → `--frozen-lockfile` на Vercel падал. УРОК: после `pnpm add` НЕ ревертить package.json
  без `pnpm install` (lockfile рассинхронится). Фикс — `pnpm install` (analytics только в apps/web).
- Видео БЕЗ аудио (коммит `6ee49a5`): `has_audio_stream` (ffprobe `-select_streams a`) → ЧЁТКАЯ ошибка
  до ffmpeg вместо «Output file does not contain any stream / код 234». Quip режет по РЕЧИ → звук
  обязателен. Проверено на РЕАЛЬНОМ 159МБ файле фаундера (75мин AV1, БЕЗ звуковой дорожки).

**⚠️ Открытое / ручное на следующую сессию:**
- ВКЛЮЧИТЬ Vercel Analytics в дашборде (код готов, ждёт тогла).
- Editor-визуал (libass рисует hook/анимацию/стиль, instant-превью, драг) — судит фаундер ГЛАЗАМИ
  (libass автотестами не верифицируется).
- Direct-upload работает ТОЛЬКО в cloud; local dev = старый multipart (это ок).
- R2 CORS выставлен; если бакет пересоздадут — повторить (JSON в `deploy/modal/r2_setup.py`).
- Воркер deployed с этим кодом; frontend на main (Vercel auto-deploy). just check / next build зелёные.

---

## 2026-06-15 (сессия 2) — SEO-фундамент: программатик `/use-case/*` + двуязычность + план миграции на `quip.ink`

**Контекст / решения фаундера:** цель — топ выдачи по русским запросам («создание шортсов»,
«создание рилсов», «вертикальные видео» и т.д.). Два решения: (1) **двуязычно RU + EN** (EN на `/`,
RU-first программатик-страницы); (2) **переезд апекс `quip.ink` → проект `quip-app`** (сейчас апекс =
старый лендинг `Shorts-Automatizator`/проект `quip`), `app.quip.ink` → 301. Ключевая находка ресёрча:
**в рунете Яндекс ≈ 73% / Google ≈ 27%** — настоящее поле боя Яндекс, нужны Вебмастер + Метрика
(сейчас только Vercel Analytics) — это P0-блокер.

**Сделано (технический слой, код — `apps/web`):**
- Новый программатик-роут `app/(marketing)/use-case/[slug]/page.tsx` + данные `lib/useCases.ts`
  (8 RU-страниц, latin-слаги: `make-shorts`, `youtube-to-shorts`, `podcast-to-shorts`, `make-reels`,
  `horizontal-to-vertical`, `webinar-to-shorts`, `auto-subtitles`, `video-to-clips`). Каждая —
  уникальный H1/intro/шаги/выгоды/FAQ (НЕ doorway-клон), `generateStaticParams` + `generateMetadata`,
  FAQPage + BreadcrumbList JSON-LD, sibling-перелинковка. UI лендинга НЕ тронут.
- `sitemap.ts` тянет use-case страницы из `USE_CASES`; `lib/jsonld.ts` — `inLanguage:[en,ru]` на home
  + `buildUseCaseJsonLd`; `layout.tsx` — `og:locale en_US`+`alternateLocale ru_RU`, `verification`
  (google + yandex из env `NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION` / `NEXT_PUBLIC_YANDEX_VERIFICATION`).
- Стратегия целиком → `docs/SEO_STRATEGY.md` (семантическое ядро 18 use-case + 7 blog, 6 слоёв,
  рунбук миграции домена, чек-лист Вебмастер/Метрика/GSC, KPI, риски). Статус запуска синхронизирован
  с кодом в §2.2.1.
- Проверено на запущенном dev: `/use-case/make-shorts` → 200, RU title/H1, canonical `quip.ink`,
  `og:locale ru_RU`, FAQ+Breadcrumb JSON-LD, sitemap = 8 use-case. `just check` зелёный (553 теста).
  (Грабли: Turbopack dev не подхватывал новый route-сегмент до файл-тача → ложный 404; не код-баг.)

**⚠️ Открытое / ручное (НЕ код — действия фаундера, детали в `docs/SEO_STRATEGY.md`):**
- Миграция домена в Vercel/DNS (снять `quip.ink` с проекта `quip`, добавить в `quip-app`, 301 с
  `app.quip.ink`, env `NEXT_PUBLIC_SITE_URL=https://quip.ink`, Supabase/Polar redirect URLs).
- Завести Google Search Console + **Яндекс.Вебмастер** + **Яндекс.Метрика (Вебвизор)**, проставить
  токены верификации в env, отправить sitemap, «переезд сайта» в Вебмастере.
- Следующие фазы: i18n-рефактор лендинга на `/ru` (hreflang-пары), волны P1/P2 use-case, `/blog/*`.

### 2026-06-15 — Адаптивность фронта (mobile pass) + редактор на телефоне
Сквозной проход по адаптивности `apps/web` саб-агентами (домены не пересекались по файлам;
оркестратор собрал + прогнал гейт). Принцип: **десктоп не трогаем** — все мобильные правки за
responsive-префиксами (база = мобайл, `sm:`/`lg:` восстанавливают текущий десктоп).
- **Маркетинг:** таблица сравнения (`Comparison.tsx`) на ≤sm стекается в карточки с подписями
  колонок (на десктопе — та же 3-колоночная таблица); `MobileMenu` бургер 36→44px + меню
  `max-w-[calc(100vw-2rem)]` (не вылезает за край).
- **App-shell:** `FeedbackWidget`-модалка кламп по вьюпорту; `AppHeader`-дропдаун `max-w`;
  `AccountBilling`/`UsageMeter`/`RecentProjects` — `min-w-0`/`truncate`/touch-цели; `SourceForm`
  степперы крупнее на тач; `ClipPreview` контролы видимы на тач (паттерн `[@media(hover:hover)]`).
- **Редактор (главное):** на телефоне `h-dvh` больше не давит всё в один экран — `main` стал
  скролл-областью, **превью `sticky top-0`** (видно всегда), контролы скроллятся, таймлайн закреплён
  снизу (паттерн CapCut). Шапка редактора ужата под 375px (иконки + `N/M` вместо `Clip N of M`,
  ничего важного не прячем). `EditorHeader`/`ClipEditorScreen` — только layout, логика не тронута.
- **Тач-контролы:** ручки таймлайна 3→16px хит-зона; контролы превью видимы при проигрывании на
  тач (раньше `group-hover` → невидимы); слайдеры — общий `.range-touch` (палец-thumb 20px);
  hover-only кнопки (вырезать/undo реплики, тулбар субтитров) показываются на тач; галереи пресетов
  `no-scrollbar`+snap; узкие 2-кол сетки → 1-кол на мобайле; `ExportMenu` дропдаун с `max-w` вьюпорта.
- Центральные утилиты добавлены в `globals.css`: `.no-scrollbar`, `.range-touch` (опт-ин).
- Гейт: `tsc --noEmit` ✓, `eslint` ✓ (web). Живой прогон браузером (375px): лендинг/прайсинг —
  0 горизонтального оверфлоу, без console-ошибок; таблица сравнения стекается на мобайле и остаётся
  таблицей на 1280px. (Открыто: live-QA самого редактора на тач — нужен реальный job/clip за auth.)

### 2026-06-16 — Прод-фиксы: домен/CORS, аплоад без потолка, скорость, ретеншн, шрифты, пан, download
Большая сессия фиксов ЖИВОГО прода (всё задеплоено Modal + запушено Vercel). Саб-агенты (opus):
ресёрч стоимости R2, аудит скорости пайплайна, дизайн stop/cancel, диагностика download/шрифта,
расследование рывков рефрейма. Источники истины правлены в синхроне.
- **Домен/CORS:** апекс `quip.ink` переехал на проект `quip-app` → воркер по CORS пускал только
  `app.quip.ink` → `/usage` и аплоады с `quip.ink` резались (UsageMeter МОЛЧА падал в Free). Расширил
  `allow_origin_regex` (`main.py`) + R2 `AllowedOrigins` (`storage.set_upload_cors`/`r2_setup`) на
  `quip.ink`/`www.quip.ink`. Фаундер добавил origin в R2-CORS дашборда + Supabase Redirect URLs.
- **UsageMeter/UsagePill:** убран тихий `catch`→Free (правило №8); явные loading(скелет)/error
  (саппорт+ретрай) состояния (`lib/useUsage.ts`).
- **Аплоад без 5 ГБ-потолка:** multipart browser→R2 (presigned-URL на каждую часть, параллельно 3,
  abort при сбое; pure `plan_part_count`+тест). Кэп 500 МБ → 10 ГБ (guard; реальный предел — 3 ч,
  `MAX_VIDEO_MINUTES`). Presigned PUT 1 ч → 6 ч.
- **Скорость (из аудита):** Modal `cpu=4/memory=4096` на run_job/upload_job/render_job (дефолтный ~1/8
  ядра душил ffmpeg-транскод); boto3 `TransferConfig` 64 МБ/20 потоков на source upload+download;
  `_ensure_mp4` умный remux (видео-copy+аудио-aac до full re-encode, лог пути); Deepgram read 300→600;
  `upload_clip` стрим (`upload_file`) вместо `read_bytes`.
- **Пайплайн-таймаут** run_job/upload_job 1 ч → 3 ч (полный preview-транскод 3-часовика на 1 ч умирал).
- **Ретеншн R2:** Modal Cron `cleanup_stale_sources` (04:00 UTC) удаляет source/preview старше 60 дней
  (клипы — вечны). source = 70-90% хранилища; разовая оплата → иначе безлимитный рост. R2: egress free,
  $0.015/ГБ-мес сверх 10 ГБ; маржу почти не ест (~1 п.п.), проблема — накопление. Инертен ~2 мес.
- **Клипы:** до 30 (было 12/10) + режим **Auto** («сколько найдётся, до 30»); `resolve_max_clips hi=30`,
  Field `le=30`. Фронт: сегмент-контрол Auto/Custom.
- **Рефрейм-пан:** `build_fill_crop_expr` piecewise-CONST → piecewise-LINEAR (рампим cx) → ПЛАВНЫЙ пан.
  Регрессия видимости от `6d0d7d6` (dead-zone keyframing) поверх ступенчатого рендера. ⛔ ИНВАРИАНТ ЦЕЛ:
  trim-кадры и fit-чейн ИДЕНТИЧНЫ (доказано диффом фильтрграфа на реальном 29.97fps клипе) — меняется
  ТОЛЬКО cx внутри fill-региона. Док явно благословляет (`REFRAME_FPS_GRID_INVARIANT.md §«Что МОЖНО»`).
- **Шрифт хук==субтитры:** `Unbounded.ttf` без bold-начертания, а ASS просил `Bold=-1` → libass на
  воркере (debian_slim без системных шрифтов) подменял СЕМЕЙСТВО на Montserrat. Фикс: `Bold=0` для
  Unbounded (worker `captions_v2` + фронт `assStyle`, WYSIWYG). Жирное вернуть = завезти Unbounded-Bold.ttf.
- **Download:** клип на `cdn.quip.ink` (cross-origin) с HTML download-атрибутом открывался в табе →
  `Content-Disposition: attachment` на R2-загрузке (новые клипы); `getRenderStatus`→`fetchWithTimeout`.
  **Моков в пути скачивания НЕТ** (`NEXT_PUBLIC_WORKER_URL` → реальный воркер).
- **Опер:** ротация `GEMINI_API_KEY` в Modal-секрете `quip-worker` (квота кончилась; пересоздан с прод-
  значениями из `.env` + `STORAGE_BACKEND=r2`, billing-секрет не тронут).
- **Спроектировано, НЕ реализовано:** ~~**stop/cancel**~~ (ОТГРУЖЕНО, см. ниже). **async-export**
  (латентность download — sync-рендер на web-контейнере).
- **Stop-кнопка (cancel джоба) ОТГРУЖЕНА:** `POST /jobs/{id}/cancel` отменяет джоб во FREE-фазе
  (download/probe, до транскрипции) → `$0` заряда. Инвариант: заряд только в `_meter` ПОСЛЕ `set_done`;
  Modal `FunctionCall.cancel(terminate_containers=False)`→`InputCancellation` (подкласс **BaseException**)
  минует `except JobError`/`except Exception` → функция выходит ДО `set_done`/`_meter`. `dispatch.spawn`
  теперь возвращает `function_call_id` (сохраняется в `jobs.function_call_id`); воргер гасит
  `cancellable=False` ПЕРЕД транскрипцией (`run.on_cancellable`); `set_cancelled` с guard
  `status NOT IN (done,failed)`. Новый `JobStatus.cancelled` + `Job.cancellable` (default False).
  Фронт: Stop в `JobProgress` (только при `cancellable`), `cancelJob` (409→friendly), `useJob` стопит
  поллинг на `cancelled`, нейтральная панель «This project was stopped». Миграция `0006_job_cancel.sql`
  применена в проде. Закрытие вкладки НЕ отменяет (Modal spawn живёт отдельно).

### 2026-06-17 — W1 (стабильность выбора клипа) + W2 (живые хуки); W4/W5/W6 — ревизия
Ветка `feat/w1-w2-select-quality`. Сначала **передеплой воркера** (Stop-кнопка не садилась прошлую
сессию): корень — НЕСКОЛЬКО зависших `modal deploy` процессов от прошлых сессий конфликтовали за
деплой; убил все → чистый деплой. (`POST /jobs/{id}/cancel` — проверка см. reality.)

- **W1 — резкий конец клипа + длина + токены** (`pipeline/stage2_select.py`, TDD):
  - `snap_end_index`: окно `.?!` расширено 5→8; НЕТ `.?!` → снап к НАИБОЛЬШЕЙ паузе ≥0.35с по
    word-таймингам (чистый вдох, не середина фразы); сплошная речь → без изменений.
  - `pad_clip_end` (NEW): хвостовой паддинг `clip_tail_pad_sec=0.3`с в тишину для чистого лупа
    (вертикальный шортс зацикливается мгновенно). Кламп по старту следующего слова и длительности.
    **Баг, пойманный на реальном 1ч-видео:** Deepgram иногда отдаёт ПЕРЕКРЫВАЮЩИЕСЯ тайминги
    (`next.start < word.end`) → кламп уходил РАНЬШЕ конца слова и резал его → `max(end_sec, …)`.
  - `postprocess`: длительность-гейт по РЕЧИ (до паддинга) — клип на границе max_sec не дропается.
  - **Реальный max в промпт** (`build_user_prompt` принимает min/max → жёсткий лимит «clip > Xs
    будет отклонён, обрежь до сильнейшего окна»); хардкод «15-60s» в системном промпте смягчён.
    **Решение дроп vs усечь:** промпт — первичный контроль; `postprocess`-дроп = safety-net (НЕ
    усекаем — усечение вернуло бы резкий обрыв, ровно баг W1).
  - **Токены (реальный 1ч-прогон, `tmp/bench_select.py`):** 8928 слов → input **22.5k**, output
    ~1.2-1.4k, thoughts 0, **~$0.01/прогон** (Flash). 3ч-проекция ~67.5k input / ~$0.03. input ≈
    2.52 ток/слово; видео в Gemini НЕ шлём. `llm_max_output_tokens=16000` с 4× запасом → не трогаем.
    → `runs.jsonl` (`select_tokens_w1`) + `docs/BENCHMARKS.md`.
- **W2 — живые хуки** (`prompts/select_moments.v2.txt`, NEW): двухступенчатая генерация в structured
  CoT — `tone` (эмоция) → `hook_style` (pov/relatable/informative/shock/curiosity) → `hook` в стиле +
  bilingual few-shot. `_PROMPT_PATH` → v2 (версионируем без передеплоя). `hook_style` — **свободная
  строка** на `Segment`/`ClipOut` (НЕ enum: словарь стилей живёт в промпт-файле, крутится без
  codegen/релиза); проброшен в `run.py`→ClipOut; `just types` прогнан. Реальный прогон: хуки —
  вопросы-петли/шок/инфо на языке транскрипта (ru), а не описания.
- **W5 — хук стилизуется как субтитры: УЖЕ ОТГРУЖЕН** (бриф устарел). `HookTab.tsx` имеет полный
  паритет со Style-tab (галерея пресетов `HOOK_PRESETS`, цвет/шрифт/плашка/контур/размер/позиция+драг/
  анимация входа/UPPERCASE; reuse `ColorField`/`DebouncedSlider`/`CAPTION_FONTS`). Не трогал.
- **W6 — лаги/баги редактора: УЖЕ ПОЧИНЕНЫ** (фиксы 2026-06-15, founder: «вроде норм»). Проверено
  read-only: (1) задвоение/stale → `LibassLayer` (`setTrack`+форс-редроу, B-#1); (2) пресет сбрасывал
  позицию → `apply_preset` сохраняет `margin_v`+`alignment` (B-#2); (3/4) лаги → оптимистичный
  client-side `patchAssStyles` без раунд-трипа + локальный драг. Открытое (не баг): live-QA за auth.
- **W4 — СДЕЛАН:** (а) ремап субтитров при сдвиге УЖЕ корректен — все ops (`set_interval`/trim/extend/
  add_section) идут через `_with_intervals`→`rebuild_replies`; залочил регресс-тестом
  (`test_set_interval_shift_remaps_captions_to_new_window`). (б) **Хук-реген под новый интервал**
  (фаундер выбрал «сделать»): `POST /jobs/{id}/clips/{cid}/hook/regenerate` — узкий Gemini-вызов (НЕ
  чат), транскрипт ТОЛЬКО этого клипа (`clip_words`, вынесен из `rebuild_replies` — DRY) + длина →
  `regenerate_hook` (стиль W2, промпт `prompts/regenerate_hook.v1.txt`, схема `_LlmHook`); меняет лишь
  `hook.text` (стиль/позиция W5 не тронуты), optimistic-lock. Фронт: кнопка «Regenerate for current
  clip» в `HookTab` + хинт «хук не обновляется сам при сдвиге» (явный opt-in, не перетираем молча).
  Цена ~$0.0003/реген (706/38 ток на реальном клипе) → НЕ метрим (как прочие правки редактора).
  Реальный прогон: клип→хук «Почему Бог оставляет нас в живых» (curiosity, ru). TDD: clip_words +
  parse_hook_response + build_hook_regen_prompt + API-тест (мок Gemini, версия+409).
- **W3 (агентный чат-редактор)** — спроектирован и СДЕЛАН в эту же ночь (см. отдельную запись ниже).

### 2026-06-17 — Денежный инвариант: ошибка с нашей стороны → НЕ списываем минуты
Ветка `fix/no-charge-on-error`. Запрос фаундера: «при любом раскладе наша ошибка не должна списывать
минуты». Аудит метеринга (`tasks.py`): инвариант УЖЕ соблюдён структурно — `_meter` зовётся ТОЛЬКО
после `db.set_done`, а порядок `try(run_pipeline→set_done→_meter)/except(set_failed)` делает `_meter`
недостижимым при исключении ЛЮБОЙ стадии (download/transcribe/select/reframe/render) → ошибка =
`set_failed`, ноль заряда. Падение одного клипа в render-цикле тоже пробрасывается → весь джоб failed.
- **Добавлен 2-й слой (defense-in-depth):** гард `if not job.clips: return` в `_meter` — не заряжаем,
  если НЕ отдали ни одного клипа (0 клипов = юзер получил пусто; и страховка от вырожденного «успеха»).
- **Залочено тестами** (раньше денежный «error→no charge» на уровне джоба НЕ был покрыт):
  `test_run_pipeline_job_failure_does_not_meter` (JobError → set_failed, _meter не вызван),
  `test_meter_skips_charge_when_no_clips_delivered`. Хелпер `_job_with_minutes` теперь даёт клип.
- Editor-рендеры (`render_edit_to_file`/`render_clip_edit_job`) и отмена (Stop) заряд НЕ трогают —
  подтверждено (метеринг только в 2 pipeline-тасках). `just check` зелёный.

### 2026-06-17 (ночь) — W3: агентный чат-редактор клипа (ОТГРУЖЕН)
Дизайн ДО кода → `docs/superpowers/specs/2026-06-17-w3-agent-clip-editor-design.md` (воркфлоу, UX,
20 сценариев, инварианты, план). Реализация на ветке `feat/w3-agent-editor` (смержена в main).
- **Что это:** в редакторе клипа вкладка **Agent** — чат, где агент правит ИНТЕРВАЛ и ХУК
  естественным языком, тулзами, показывая мысли/действия. НЕ трогает субтитры и кадр (жёсткие
  границы), не чат-бот (офф-топик → вежливый отказ). Фон + Stop (reuse spawn/cancel), **$0 минут**.
- **Архитектура:** `app/agent/loop.py` (чистый control-flow, инъекция зависимостей → детерм. тесты;
  hard-cap шагов; ошибка тула → модели, не падаем) · `tools.py` (set_interval/nudge/regenerate_hook/
  set_hook_text/request_render/get_clip_state над edit-state, optimistic-lock+ретрай; pure
  `compute_nudge`) · `clip_agent.py` (Gemini **function-calling**; `parse_model_response` pure) ·
  `runs_store.py` (agent_runs dual-mode SQLite/Supabase, лента событий) · `tasks.agent_edit_job` +
  Modal-функция `agent_edit_job` (отменяемый джоб) · `main.py` эндпоинты start/active/{id}/cancel
  (start идемпотентен — один run на клип). Контракт: `AgentRunStatus/AgentEvent/AgentRun` (codegen).
  Миграция `0007_agent_runs.sql` применена в проде.
- **Грабли (поймано реальным прогоном):** Gemini 2.5+ требует ECHO'ить нативный Content модели с
  `function_call` (несёт `thought_signature`) в следующем ходе — реконструкция из имени/аргументов →
  400 INVALID_ARGUMENT на 2-м тул-вызове. Фикс: `model_turn` держит нативные Content между ходами.
- **Фронт:** `AgentTab.tsx` (лента user/thinking/action/agent/error + ввод + Stop + поллинг +
  реконнект `key={clipId}`); `api.ts` (start/get/active/cancel); таб Agent в `ClipEditorScreen`
  (`handleAgentEdited` перечитывает edit+ASS после правок агента).
- **DRY:** `editor/hook_ops.regenerate_hook_for_clip` — общий для W4-эндпоинта и агент-тула; W4
  `regenerate_hook` получил `style_hint` (агент передаёт «шок»/«pov»/«покороче»).
- **Тесты:** 33 unit (loop/tools/runs_store/clip_agent/api) + **реальный E2E на 1ч-видео**: «сдвинь
  начало на 5с раньше + цепляющий хук» → интервал 25→20с, хук «Террористы никогда не чувствуют
  раскаяния», рендер — всё применилось. `just check` зелёный. Воркер задеплоен (функция
  `agent_edit_job` создана; эндпоинты живые).
- **НЕ в v1 (кандидаты v2):** видео в Gemini (дорого — шлём только транскрипт), reframe/субтитры-тулзы,
  undo-тул, full chat-history list (есть реконнект к активному прогону).

### Reframe — фикс остаточного флеша на склейках (2026-06-17)
- **Симптом (фидбек фаундера):** на сгенерённых клипах на склейке 1 кадр держался СТАРЫЙ кроп
  («сначала кадр, потом переход, не ровно попадает»). Гибрид (speaker-fill вместо fit на диалоге)
  убрал флеш fit→диалог, но остаточный 1-кадровый флеш на fill→fill (смена спикера) ОСТАЛСЯ.
- **Корень (systematic-debugging, не угадал):** НЕ инвариант сетки (Δ=0 доказан) и НЕ регрессия
  (git diff 377493a..HEAD = 0 строк по reframe/render). Покадрово на реальном источнике: контент-
  переход на кадре N, а `detect_scene_cuts` возвращал границу N+1 → кадр N (новый шот) держал старый
  кроп = флеш. PySceneDetect помечает склейку на 1 кадр позже относительно сетки рендера.
- **Фикс:** `detect_scene_cuts` → `max(1, s[0].get_frames() - 1)`. Инвариант цел: граница остаётся
  ЦЕЛЫМ кадром → `round(t0*fps)=cut-1`, Δ=0 (REFRAME_FPS_GRID_INVARIANT). Чинит оба пути (batch +
  editor reframe_cache, оба зовут detect_scene_cuts).
- **Верификация:** перерендерил источник (job_060aaf70f05c), покадрово 2 независимые fill→fill
  склейки: 261 (man→woman) и 949 (woman→man) — контент и кроп меняются на ОДНОМ кадре, флеша нет.
  `just check` зелёный (628 unit), воркер задеплоен.

### 2026-06-17 — Perf: параллельный рендер клипов + preview вне критического пути
- **Проблема (по реальным логам Modal, job_7653abda6258):** stages 3–5 шли последовательным
  Python-циклом на ОДНОМ run_job-контейнере. Соседние клипы стартовали ~57-60с друг от друга,
  при этом `render=` всего ~8с → доминанта = reframe-анализ (MediaPipe+ASD) ~50с/клип. Wall-time
  линеен по числу клипов (30 клипов ≈ 30 мин). Плюс `build_preview_proxy` (полный транскод
  source→720p, до 30-60 мин для 3ч) сидел на критическом пути ДО set_done.
- **#1 фан-аут:** per-clip тело (reframe→render→upload) вынесено в ОДНУ shared-функцию
  `run.render_one_clip` (DRY). На Modal — новая функция `reframe_render_clip` (контейнер на клип,
  `dispatch.map_render_clips` → `starmap`), клипы рендерятся ПАРАЛЛЕЛЬНО; локально — тот же
  последовательный цикл (поведение идентично). Каждый клип-контейнер качает source из R2 через
  `artifacts.ensure_source` (тот же путь, что editor-render). source грузится в R2 ДО фан-аута.
- **#3 preview:** вынесен в отдельную `preview_job` (Modal), run_job спавнит её ПАРАЛЛЕЛЬНО с
  клипами — не держит set_done. Редактор фолбэчит на source, пока прокси не готов
  (`storage.preview_read_url`). Локально preview строится inline ПОСЛЕ клипов (dev).
- **#2 пропуск ASD на одно-спикерных клипах:** ASD speak-скор нужен ТОЛЬКО чтобы выбрать
  говорящего среди 2+ дорожек (`_pick_target`/`_is_wide_shot`/`wide_speak_min` все требуют ≥2
  active). При РОВНО одной дорожке говорящий однозначен → дорогой `_crop_faces`+torch-форвард
  `score_track` не влияет на регионы (доказано: и max-speak, и fallback-by-width вернут ту же
  единственную дорожку). Новый pure-предикат `stage3_speaker.should_score_asd(n_tracks)` (≥2);
  `asd_reframe.score_tracks_in_segment` пропускает crop+ASD при одной дорожке (speak=`_SILENT`,
  аудио не читаем зря). На talking-head подкастах (доминирующий кейс) режет ~половину времени
  reframe. ВЫХОД для таких сегментов идентичен (не меняет регионы/границы — инвариант цел).
  **Kill-switch:** `REFRAME_SKIP_ASD_SINGLE_TRACK=false` в секрете `quip-worker` → всегда считать
  ASD (мгновенный откат без передеплоя кода; Modal подхватит env на следующем контейнере).
- **Инвариант цел:** НЕ трогали `stage3_reframe.py`/`stage5_render.py`/`reframe_cache.py`. #2
  правит `asd_reframe.py` (I/O-обёртка ASD) + `stage3_speaker.py` (pure-предикат) — НЕ геометрию
  склеек/шотов/границ. Кадровая сетка (REFRAME_FPS_GRID_INVARIANT, фикс 9e57981) не затронута.
  Без `models.py` → без codegen. `just check` зелёный (635 unit). Ветка `perf/parallel-clip-render`.
- План: `docs/superpowers/plans/2026-06-17-parallel-clip-render.md`.

### 2026-06-17 — Фиксы редактора/агента/выбора клипов (3 бага по фидбеку фаундера)
- **#1 Агент-чат «грузится» после завершения.** `AgentTab` рендерил спиннер (`Loader2 animate-spin`)
  на КАЖДОЙ строке-мысли `thinking` безусловно → после done/failed мысли-история продолжали
  крутиться = ложное «всё ещё работает». Фикс: спиннер только пока прогон живой (`live={running}`),
  иначе статичная точка. Корень найден чтением (systematic-debugging), не угадан.
- **#2 Горизонтальный вид (fit) есть в гриде, нет в превью редактора.** Эндпоинт `/reframe`
  (`get_clip_reframe`) звал `resolve_regions_accurate` БЕЗ `wide_speak_min` → брался дефолт 0.3,
  а батч-рендер и `render_edit_to_file` передают `s.reframe_wide_speak_min`. Гибрид-порог решает
  «широкий план → кроп спикера (fill) vs горизонталь (fit/split)»: при настройке ≠0.3 превью
  расходилось с гридом/рендером. Фикс: эндпоинт теперь передаёт `s.reframe_wide_speak_min` (его
  же docstring обещает «превью-план == рендер-план»). НЕ трогает кадровую сетку/инвариант.
- **#3 Выбор/переключение клипов.** (a) Грид (`ClipGrid`) и редактор (`ClipEditorScreen`) сортировали
  клипы по `score ↓` БЕЗ тай-брейка → при равных score (частое у подкастов) порядок зависел от
  очерёдности фетча и расходился → «открыл первый, попал в третий», скачет ‹ ›. Фикс: детермин.
  тай-брейк `|| a.id.localeCompare(b.id)` в ОБОИХ местах. (b) Не было ни одной error-boundary →
  любое исключение при рендере «выкидывало» юзера. Добавлен `app/(app)/error.tsx` (reset + «All
  clips»). `just check` зелёный (635 unit). Ветка `fix/editor-ux-stability`.

### 2026-06-17 — Ручной контроль кадра + auto-fit + агент-контекст + анти-флеш (4 фичи/фикса)
Спека: `docs/superpowers/specs/2026-06-17-framing-control-and-agent-fixes.md`. Сделано 3 параллельными
саб-агентами (непересекающиеся файлы) + интеграция оркестратором. Ветка `feat/framing-and-agent-fixes`.
- **#1 Ручной «горизонтальный вид» (мини-таймлайн).** Новый `apps/web/components/editor/FitTimeline.tsx`:
  полоса под превью, блок на reframe-регион (шот между склейками); драг выбирает СМЕЖНЫЙ диапазон
  шотов (снап к границам, не посреди кадра), `[Wide|Tight|Auto]` форсирует кадр. Маппит клип-время →
  source (обратный `regions_to_clip_time`) и зовёт существующий `POST /edit/crop` (mode `auto` чистит
  override). Интеграция в `ClipEditorScreen` (`handleApplyRange`, зеркало `handleFrameApply`).
- **#2 «Любая непонятная ситуация → горизонталь».** `plan_regions`: fill выбираем ТОЛЬКО на уверенном
  субъекте (явный говорящий `speak≥threshold` ИЛИ лицо `width≥_MIN_FACE_FRAC=0.08`), иначе fit. Мелкое
  молчащее лицо больше не даёт кривой кроп. Split не трогали (отдельно потом). Инвариант кадровой сетки
  цел (меняется только выбор режима, не границы шотов).
- **#3 Агент «анализирует вокруг клипа».** Был фейл с именами тулзов на просьбе «обрежь нормально» —
  агенту нечем было посмотреть транскрипт ВНЕ клипа. Новый тул `get_surrounding_transcript` (окно ±сек
  с source-таймстемпами, pure-хелпер `words_in_window`) + декларация в `_FN_DECLS` + правка промпта →
  агент выбирает чистые точки реза на границах предложений.
- **#4 Флеш в превью на reframe.** `PreviewPlayer`: блюр-фон монтировался лениво только в fit → на
  переходе fill→fit свежий `<video>` ещё не декодирован = чёрные полосы кадр-другой (в готовом клипе
  флеша нет). Держим фон тёплым во всех режимах кроме split (в fill скрыт opacity-0 + перекрыт
  мастером; в split не нужен — D3 бюджет декодеров). Дёшево на preview-прокси.
- `just check` зелёный (**645 unit**, +10). `models.py` не трогали → без codegen. Кадровая сетка цела.

### 2026-06-17 — Per-shot override, история чата агента, стабильный флоу агента (3 бага)
По фидбеку фаундера. Саб-агент сделал #5 (reframe), оркестратор — #1/#2 (агент) + интеграция.
- **#5 (КРИТ, регрессия #1):** force-framing одного шота превращал ВЕСЬ клип в этот режим и стирал
  сегменты («больше ничего сделать нельзя»). Корень: `reframe_cache._override_for`+`_manual_region`
  применяли override НА ВЕСЬ интервал. Фикс «перекрась, не перерезай»: `resolve_regions_accurate`
  сперва считает авто-шоты, затем `apply_overrides_to_regions` перекрашивает ТОЛЬКО покрытые шоты
  (midpoint+last-wins), СОХРАНЯЯ t0/t1 (инвариант цел — новых границ нет). Чинит и превью, и рендер.
  **Follow-up (повторный фидбек «всё равно весь видос fit, нет сегментов»):** убрал fast-path
  «override во весь интервал» — он схлопывал /reframe в ОДИН регион, когда был whole-clip override
  (таб «Кадр» Wide), и мини-таймлайн показывал один блок → пошотовый контроль не вернуть. Теперь
  ВСЕГДА считаем авто-шоты + перекрас → сегменты всегда видны и whole-clip-fit обратим пошотово. +тесты.
- **#1 история чата:** каждый `agent/start` создавал пустой run → агент без памяти, тред пропадал из
  UI. Фикс: `latest_run` + `agent_start` засевает ленту нового рана прошлой беседой (кап 40 событий)
  → UI = непрерывный тред; `run_clip_agent` берёт текущий запрос как ПОСЛЕДНЕЕ user-событие и
  `_prior_turns` (user/agent, кап 16) сеет память модели (только текст → thought_signature не ломаем).
- **#2 стабильный флоу:** модель могла выдать случайную «мысль» за ответ. Фикс: Gemini
  function-calling `mode=ANY` (всегда тул) + явный финиш-тул `respond_to_user` (единственный путь
  ответа; `loop.FINISH_TOOL`); `parse_model_response` отделяет thought-части (`part.thought`) → в
  rationale, НИКОГДА в ответ. Пустой TextReply → нейтральное «Готово.», не пузырь-мысль. +тесты.
- `just check` зелёный (**657 unit**, +12). `models.py` не трогали → без codegen. Только worker
  (нужен `modal deploy`). Кадровая сетка/инвариант целы.

### 2026-06-18 — Объяснимость + Карта видео + умная нарезка (ветка feat/explainability-video-map)
Дифференциатор «Quip понимает всё видео и объясняет, почему момент стоит клипа». 5 доменов,
14 коммитов, овернайт через саб-агентов (исполнитель+ревью на задачу, финальный whole-branch ревью —
READY). Все коммиты с зелёным `just check` (692 unit-теста).
- **D0 — мин. длина клипа 20с** (было 15): `config.clip_min_sec`, select-промпт, `clamp_interval`,
  слайдер TimelineV2 (+подсказка), агент, клик-обрезка. Единый источник.
- **D1 — бэкенд VideoMap**: модель `VideoMap/VideoChapter/VideoMoment` (контракт → codegen);
  pure `parse_video_map` (клампинг, привязка clip_ids по пересечению глав с клипами, kind, битый
  вход → failed) + `moment_to_interval` (снап к словам из stage2_select + расширение до 20с) — TDD;
  `generate_video_map` (Gemini structured по индексам слов → секунды, переиспуёт `call_gemini_structured`)
  + промпт `video_map.v1.txt`; фон-джоб `generate_video_map_job` + `GET /jobs/{id}/video-map` (?retry,
  spawn на Modal / bg локально) + триггер в run.py после select. **Хранение кросс-контейнерно**: новая
  jsonb-колонка `job_artifacts.video_map` (миграция **0008**, single-key merge-upsert — НЕ затирает
  meta/segments/transcript), disk-fallback для dev.
- **D2 — умный агент**: фикс клампа границ у конца видео (`clamp_interval` max-арм + слайд start),
  тул `get_video_map` (компактная сводка), хук с учётом всего видео (`video_summary`), промпт —
  честно сообщать о клампе/упоре в конец.
- **D3 — карта на странице результатов** (`VideoMap.tsx`): нарратив с кликабельными `[mm:ss]`/
  `[[clip:NN]]`, аккордеон глав, цветные моменты (5 видов + легенда), pending/failed/empty; на мобиле
  свёрнута по умолчанию (useSyncExternalStore). Проверено визуально (десктоп+мобила, скриншоты).
- **D4 — обогащённая строка тем в редакторе** (`TopicStrip.tsx`): главы/моменты, «Подвинуть клип
  сюда» (→ handleSetInterval, расширение до 20с), маркер «текущий», отличие от FitTimeline (иконка
  BookOpen). Цвета вынесены в `lib/momentKinds.ts` (DRY). Проверено визуально (изолированный харнесс).
  **«Новый клип» отложен** — нет endpoint create-clip (согласовано с фаундером: только «подвинуть»).

**Перед деплоем (фаундер):** применить миграцию 0008 (`ALTER TABLE job_artifacts ADD COLUMN
video_map jsonb`) ДО `modal deploy`, иначе cloud `save_video_map` упадёт ЯВНО (правило №8). Боевые
тесты (реальное видео RU/EN на задеплоенном воркере) + финальный визуальный прогон в редакторе на
реальном джобе — за фаундером. НЕ смержено, push не делался.

### 2026-06-18 — Чат-агент: фолбэк на несколько моделей Gemini + языковая политика хука
Две правки по фидбеку («чат падает, когда primary перегружен» + «хук на видео должен быть на языке
видео, а не на языке промпта»). `just check` зелёный (700 unit-тестов).
- **Фолбэк-цепочка моделей в чате** (`clip_agent._gemini_turn`): раньше агент ретраил ТОЛЬКО
  `s.llm_model` и при устойчивой перегрузке падал. Теперь перебираем цепочку
  `_AGENT_FALLBACK_MODELS = (gemini-flash-latest, gemini-2.5-flash, gemini-2.5-flash-lite)` —
  цель «хоть кто-то ответит». Pure `_model_chain(primary, fallbacks, prefer=)` (TDD): primary
  первым, без дублей, прилипаем к сработавшей модели (`chosen_model`) → меньше скачков между ходами
  (меньше риск рассинхрона thought_signature). 429/503/таймаут → ретрай+бэкофф→следующая модель;
  404 «модели нет» → сразу следующая; 400/401/403/422 (ключ/доступ/схема) глобальны → роняем сразу
  (правило №8, не маскируем). Зеркалит давний фолбэк `call_gemini_structured` в stage2_select, но
  шире (тот всё ещё `-flash-lite` только — селект не трогали, без скоупа сверх задачи).
- **Языковая политика (два разных языка)**: ЧАТ — на языке юзера; ON-SCREEN хук — ВСЕГДА на языке
  ТРАНСКРИПЦИИ клипа (`ctx['language']`), даже если юзер пишет на другом. `regenerate_hook` уже так
  работал (узкий вызов хардкодит `language=tr.language`); дыра была в `set_hook_text` — модель
  ставила продиктованные юзером слова дословно. Фикс — промпт-уровень (модель сама и генерит args):
  раздел LANGUAGE POLICY в `prompts/agent_clip_editor.v1.txt` + `DEFAULT_AGENT_PROMPT` + описание
  тула `set_hook_text` («translate into the transcription language before passing»).

### 2026-06-18 — Perf: медленная загрузка = холодный старт web-функции (systematic-debugging)
Фидбек фаундера: «загрузка файла стала мега-долгой, особенно после захода ~40 друзей; даже один на
сайте — тормозит». Расследование по systematic-debugging (корень ДО фикса, замером, не угадывал).
- **Корень (с доказательством):** байты идут НАПРЯМУЮ браузер→R2 (api.ts `createUploadJob`), Modal их
  не трогает. Тормозит фронтовая функция `web` (отдаёт `/jobs/upload-url` — БЛОКИРУЕТ старт загрузки —
  + `/upload-complete` + опрос статуса). Замер латентности: **cold 4.92s vs warm 0.36s**. Причины:
  (1) `web` был `min_containers=0` (scale-to-zero) → после простоя каждый заход ловит ~5с холодного
  старта ПЕРЕД началом загрузки; (2) НЕТ `@modal.concurrent` → один контейнер = ~1 запрос за раз, под
  нагрузкой (40 юзеров) Modal плодит по холодному контейнеру на запрос → рой cold-start + очередь.
  Образ со временем растолстел (torch/mediapipe/genai) → cold-start дороже. «Раньше быстро» = контейнер
  оставался тёплым при активном тыканье.
- **Фикс (`deploy/modal/worker.py`, функция `web`):** `min_containers=1` (всегда тёплая дверь) +
  `@modal.concurrent(max_inputs=100)` (web I/O-bound: Supabase/R2/спавн — один контейнер тянет сотни
  параллельных запросов). Pipeline-функции НЕ трогал (warm на тяжёлом образе дорого; жалоба была про
  загрузку, не обработку). **Верификация после деплоя:** латентность 4.92s→0.35s стабильно, cold-start
  устранён структурно. Цена: 1 лёгкий web-контейнер 24/7 (отход от чистого scale-to-zero — осознанно).


## 2026-06-18 — Free-watermark + кап разрешения (server-side enforcement)

**Проблема (business-critical):** `PlanLimits.watermark`/`max_resolution` были в `billing.py`, но
НИКТО в рендере их не читал → free-юзеры получали чистые клипы без вотермарки. Утечка выручки.

**Фикс:** Чистая decision-функция `billing.resolve_render_policy(plan_id, *, local_dev) -> RenderPolicy`
(TDD, тесты в `test_billing.py::TestResolveRenderPolicy`). План резолвится СЕРВЕРНО из владельца
джоба (`jobs.user_id` → `profiles.plan` → `db.get_user_plan`), НИКОГДА с клиента → обойти нельзя.
- Батч-путь: `user_id` проброшен через фан-аут (`run.clip_spawn_args`/`_render_all_clips`/`run_pipeline`
  → `reframe_render_clip` в `deploy/modal/worker.py` получил 5-й арг `user_id`). `render_one_clip`
  резолвит политику и зовёт `render_clip(watermark=, out_w/out_h=clamped)`.
- Редактор-путь: `tasks.render_edit_to_file` резолвит owner из `jobs.user_id` (закрывает bypass
  через `/export/clean.mp4`, `/export/captioned.mp4`, re-render).
- Вотермарка = ffmpeg `drawtext` «Made with Quip» (полупрозрачный белый, нижний-правый угол, шрифт
  проекта Montserrat) — `stage5_render.build_watermark_drawtext`. АДДИТИВНЫЙ оверлей ПОСЛЕ субтитров
  на финальном энкоде → кадровую сетку reframe (Δ=0) НЕ трогает (REFRAME_FPS_GRID_INVARIANT цел).
- Кап 720p: `stage5_render.clamp_output_dims` (масштаб по меньшей стороне, чётные размеры; trim по
  SOURCE-кадрам от out_w/out_h не зависит → Δ=0 цел).
- Local dev (нет owner) → без вотермарки/капа; в облаке у джоба ВСЕГДА есть user_id.
**Верификация:** 721 unit зелёные; ruff+mypy clean; реальный ffmpeg smoke (drawtext отрисовал кадр).

## 2026-06-18 — Анти-абьюз free-плана: verified email + блок одноразовых доменов

**Проблема:** Free = 2 видео абьюзят пачками аккаунтов; `handle_new_user` (миграция 0001) сеет
free-профиль КАЖДОЙ строке `auth.users` без верификации личности → бесплатные кредиты на конвейере.

**Фикс (серверно авторитетно, фронт — UX):**
- **Verified-email гейт** `main._enforce_free_identity(authorization, user_id)` (в `create_job`/
  `create_upload_job`/`create_upload_url`/`complete_upload`, ПЕРЕД квотой): план владельца = `free`
  и email НЕ подтверждён → **403** «Verify your email…». Платные — мимо. Verified резолвит
  `auth.email_is_verified(claims)`: Google-провайдер → verified (Google-входы НЕ блокируем);
  `user_metadata.email_verified` → verified; иначе авторитетный админ-lookup `email_confirmed_at`
  через service-role Auth Admin API (`supa.auth_user_email_confirmed`). JWT Supabase НЕ несёт
  `email_confirmed_at` (только `email`/`app_metadata`/`user_metadata`) — отсюда lookup. Сбой
  lookup → 502 (видимо, без тихого пропуска).
- **Блок одноразовых доменов** `billing.is_disposable_email(email)` (PURE, TDD; денилист
  `DISPOSABLE_EMAIL_DOMAINS` ~40 сервисов; матч по суффиксу домена, не ложно-похожие) → free-job
  с temp-mail = **403** «use a real email». Зеркало на фронте `apps/web/lib/disposableEmail.ts` +
  валидация до сабмита в `AuthForm` (OTP- и password-signup пути); UX-нотис «check inbox to verify».
- `auth.resolve_claims` — отдаёт ВСЕ проверенные claims (нужны email/metadata гейту), не только sub.

**🔴 Действие фаундера:** включить **Supabase → Auth → Email → «Confirm email» = ON** (иначе
email/password-аккаунты создаются сразу confirmed → гейт пропускает всех). Детали → `docs/SUPABASE_SETUP.md` §6.

**Верификация:** 756 unit зелёные (новые `test_disposable_email.py`, `test_email_verification.py`);
ruff+mypy clean (worker); tsc+eslint clean (web).

## 2026-06-19 — CapCut-рамка от РЕАЛЬНОГО rect libass (а не DOM-зеркало)

**Проблема:** `OverlaySelectionBox` мерил скрытое DOM-«зеркало текста» чтобы задать размер рамки, но
DOM-движок НЕ воспроизводит box-model libass (BorderStyle=3 плашка-паддинг, leading, balanced
WrapStyle=0) → рамка мис-сайз/мис-позиция относительно реального текста (1 строка получала рамку в 2
строки высотой).

**Фикс — гнать рамку от СОБСТВЕННОГО отрендеренного прямоугольника libass:**
- Воркер libass-wasm (`subtitles-octopus-worker.js`) в дефолтном `wasm-blend` каждый кадр постит
  `{target:"canvas", op:"renderCanvas", canvases:[{x,y,w,h,buffer}]}` (device px) = union-bbox всего
  нарисованного. Главный поток (`subtitles-octopus.js`) это РИСУЕТ; мы лишь ДОБАВЛЯЕМ слушатель на
  `instance.worker` — рендер не трогаем (read-only x/y/w/h, buffer не касаемся).
- **Hook vs caption раздельно:** хук (\an8 сверху) и субтитры (\an2 снизу) рисуем ДВУМЯ инстансами,
  по одному ASS на каждый (`splitHookCaptionAss` режет Dialogue по полю Style: `Hook` vs `Default`) →
  fused-rect каждого инстанса = ТОЧНЫЙ bbox своего элемента (без дробления union'а). Два канваса
  `absolute inset-0`, пиксели идентичны единому ASS (элементы не пересекаются).
- `LibassLayer` отдаёт `onSubRects({hook,caption})` в долях рендер-бокса, троттл на rAF.
  `OverlaySelectionBox` переписан: презентационный прямоугольник на реальном rect, удалены
  `useTextBox`/`measureBox`/FontFace/мирор-математика и props text/font/marginLR/uppercase.
  `overlayBox.ts` — только `rectToFractions` + `splitHookCaptionAss`.
- **Grab-offset фикс (#3):** на pointerdown `grabOffset = cursorFrac − anchoredEdgeFrac`; на move
  `edge = cursorFrac − grabOffset` → рамка едет за курсором 1:1, не выпрыгивает.

**Верификация:** tsc+eslint clean (web) + **визуально через харнесс с РЕАЛЬНЫМ LibassLayer**
(playwright-скрин: рамка плотно облегает хук+субтитры по настоящему bbox libass). Прошлые подходы
(DOM-зеркало) проваливались именно на визуале — теперь верифицируем глазами на реальном libass.

## 2026-06-19 — Perf: загрузка стартует сразу (identity-гейт убран с горячего пути upload-url)

Фидбек: «нажимаю загрузить — стартует не сразу». Корень: `POST /jobs/upload-url` (зовётся при клике,
ДО старта байтов) делал 1–2 синхронных раунд-трипа в Supabase ПЕРЕД выдачей presigned-URL —
`_enforce_quota` + `_enforce_free_identity` (анти-абьюз: профиль + для free ещё Admin API
`email_confirmed_at`). Сама presigned-ссылка локальна (мгновенна). Фикс: убрал identity-гейт с
upload-url (`main.py`) — он отрабатывает в `upload-complete` ДО spawn'а платной джобы (защита НЕ
ослаблена: без verified email обработка не стартует; одноразовые домены ловит и клиент). Квоту
оставил на upload-url (fail-fast). Воркер задеплоен; 756 тестов зелёные.

## 2026-06-19 — Клипы стримятся по готовности (incremental delivery)

Фидбек: «не хочу ждать все клипы разом — пусть появляются по одному и сразу редактируются». Раньше
`run_pipeline` фанил per-clip рендер через `map_render_clips` (starmap, БЛОКИРУЕТСЯ до конца), писал
все клипы и ставил `done` → фронт ждал всё, потом ронял грид.
- **Воркер:** после Select персистим ВСЕ клипы с метаданными (хук/причина/скор), но ПУСТЫМ
  `video_url`, статус `rendering` (`db.set_clips_pending` после `put_job_artifacts` в `run.py`).
  Каждый фан-аут-контейнер после `upload_clip` атомарно вписывает СВОЙ `video_url`
  (`db.set_clip_ready` → cloud RPC `set_clip_video_url` = server-side `jsonb_set`, **миграция 0010**;
  Postgres сериализует UPDATE строки → параллельные контейнеры пишут РАЗНЫЕ индексы без потери).
  `set_done` в конце пишет финальный полный список (как раньше). Биллинг/метеринг не тронут;
  кадровая сетка не тронута. Контракт БЕЗ изменений: пустой `video_url` = «ещё рендерится».
- **Фронт:** как только `job.clips` непуст (даже при `status!=="done"`) — `ClipGrid` рисует все
  карточки: готовые (`video_url` непуст) сразу играбельны + Edit/Download; рендерящиеся —
  скелетон-спиннер «Rendering…», Edit скрыт. Шапка «N of M clips ready · still rendering…».
  Грид монтируется тем же `key={job.id}` для done- и rendering-веток → переход без ремаунта/мигания.
- **Верификация:** `just check` зелёный (762 unit-теста, +6 TDD на set_clips_pending/set_clip_ready);
  прогрессивная сетка проверена **визуально** (playwright-харнесс с rendering-джобом «1 из 2 готов» —
  готовая карточка + скелетон + «1 of 2 ready»). Миграция 0010 применена в прод Supabase.

## 2026-06-19 — Трендовые субтитры: +6 открытых шрифтов, +8 пресетов, +5 анимаций

Фидбек: «больше трендовых стилей субтитров/хуков как у OpusClip/Vizard». Реализовано на ОТКРЫТЫХ
лицензионных шрифтах (OFL/Apache, Google Fonts) + наши параметры — техники индустриально-стандартные,
рендерятся одинаково в превью (libass) и экспорте (ffmpeg, тот же движок).
- **6 шрифтов** (TTF в `services/worker/fonts/` И `apps/web/public/libass/fonts/`, зарегистрированы в
  `LibassLayer.fonts[]` + `StyleTab.CAPTION_FONTS`): Anton, Archivo Black, Bebas Neue, Poppins (Black),
  Russo One, Luckiest Guy. Family-имена сверены fontTools (libass матчит по family, не по файлу).
  Только Russo One (+ существующие Montserrat/Rubik/Unbounded) имеет кириллицу; остальные Latin-only.
- **Bold=0 для одновесных** (`SINGLE_WEIGHT_FONTS`/`_ass_bold_flag`, зеркало в `assStyle.ts`) — иначе
  libass фейк-болдит/подменяет семейство. **Кириллический фолбэк** (`resolve_font_for_text`, PURE+TDD):
  Latin-only шрифт + кириллица в тексте → Montserrat (рендер-решение, не тихий фолбэк ошибки).
- **8 пресетов** `preset_n..preset_u` (Anton Bold, Beasty Yellow, Bold Pop White, Bebas Condensed,
  Karaoke Fill, Highlight Box, Sticker Round, Gamer Tech) — server-driven через `GET /presets`
  (`seed_presets()`), фронт-зеркала нет. **5 анимаций** слова (`drop_in/glow_pulse/shake/slide_up/flash`,
  layout-neutral: только `\fscy`/`\alpha`/`\blur`/`\frz`/`\1c`) в `word_animation_tags` + пикер `StyleTab`.
- **Верификация:** `just check` зелёный (773 unit-теста); 6 шрифтов проверены **визуально** на реальном
  LibassLayer (playwright — каждый своим начертанием, без подмены; кириллица Russo One видна). Контракт
  обновлён codegen (`HighlightStyle.animation` +5 значений). Воркер задеплоен (шрифты в образе рендера).
