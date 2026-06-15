# Hook styling parity + editor lag/bug fixes — design

> Статус: УТВЕРЖДЁН фаундером 2026-06-15 (AskUserQuestion: «Full parity» + «Instant client preview + bg persist»).
> Источник правды реальности — `docs/README.md`. Инвариант — `docs/REFRAME_FPS_GRID_INVARIANT.md` (НЕ трогаем reframe/render).
> OSS-ресёрч (Submagic/OpusClip/libass-wasm) — см. §6.

## 1. Цель

Две задачи, одна сессия:

- **A — Стилизация ХУКА как субтитров.** Сейчас у субтитров есть таб «Стиль» (пресеты, цвет/шрифт/
  размер/позиция/анимация), а у хука — только текст/вкл/окно. Дать паритет, **переиспользуя систему
  стилей**, при этом хук компилится в ТОТ ЖЕ ASS (`build_hook_event` → `compile_ass`) → превью = экспорт.
- **B — Лаги и баги редактора.** Через `systematic-debugging` (баги непостоянные → инструментировать,
  не угадывать): задвоение субтитров, прыжок позиции при смене пресета, тормоза драга, лаги на КАЖДОЙ правке.

**Инвариант (held):** превью libass == экспорт ffmpeg (один и тот же ASS). Любой client-side ASS —
ТРАНЗИЕНТ; авторитетный ASS компилит сервер (он же идёт в ffmpeg).

## 2. Реальность кода (что уже есть)

- `HookOverlay` (`models.py:216`) УЖЕ несёт стиль-поля: `font, size, color, outline_color, outline_w,
  shadow, box_color, box_opacity, margin_v, uppercase`. `build_hook_event` (`captions_v2.py:63`) УЖЕ
  жжёт их в общий ASS. → Задача A в основном «прокинуть в UI» + одно поле контракта (`animation`).
- `apply_preset` (`presets.py:13`) делает `update={"style": preset.style, ...}` — **заменяет ВЕСЬ
  CaptionStyle, включая `margin_v`**. Пресеты несут свой `margin_v` (260 деф., 1100 подкаст, 120
  нижняя-треть) → применение пресета СТИРАЕТ ручную позицию. ← корень B-#2.
- `LibassLayer.tsx`: один инстанс (mount-effect, dep `[videoRef]`), `setTrack(assText)` на смену ASS.
  rAF гонит `setCurrentTime`. Нет `freeTrack`/принудительного редроу после setTrack.
- `ClipEditorScreen.tsx`: очередь мутаций `patchChain` (по одной, свежая версия). Каждая правка =
  PATCH → сервер рекомпил ASS → `refreshAss()` (refetch `/ass`) → `setTrack`. ← корень B-#4 лагов.

## 3. Задача A — дизайн (Full parity)

### A1. Контракт (одно поле)
`HookOverlay.animation: Literal["none","pop","fade","bounce"] = "none"` в `models.py` → `just types`.
(Хук — одиночный заголовок, не караоке: анимация = ВХОД всего блока, не пословно. Все три —
`\fscy`/`\alpha`-теги БЕЗ абсолютных координат; `slide_up`/`\move` отложен — нужны coords.)

### A2. Бэкенд: `build_hook_event` — вход-анимация
Один layout-нейтральный `\t`-тег в начало текста хука (как анимации субтитров — НЕ меняем ширину):
- `pop` — `\fscy`-флеш (60→105→100);
- `fade` — `\alpha&HFF&\t(0,200,\alpha&H00&)`;
- `bounce` — `\fscy` подскок (115→96→100).
`\t` отсчёт от старта события (= старт окна хука). Тот же ASS → libass-превью и ffmpeg-экспорт
идентичны. +unit-тесты (есть `\t`, нет `\fscx`).

### A3. Бэкенд: хук-пресеты (отдельная галерея)
Хук-пресет = именованный набор значений `HookOverlay` (НЕ caption-пресет: те про пословное караоке —
к одиночному заголовку не мапятся; так же делают Submagic/OpusClip — §6). Сиды (копируем индустрию):
`Коралл-плашка`, `Жирный контур` (Hormozi-стиль, без плашки), `Чистый` (контур+тень), `Жёлтый поп`,
`Минимал`. **Решение: статический фронт-мир** `apps/web/lib/hookPresets.ts` (массив `Partial<HookOverlay>`)
— применяется через существующий `handleHookChange` (PATCH captions.hook), БЕЗ нового эндпоинта/версии.
Хук-пресет — чистые value-sets `HookOverlay`; backend-apply не нужен (в отличие от caption-пресетов,
которые версионируются через `/apply-preset`). PURE-данные.

### A4. Фронт: `HookTab` — секция «Стиль» + галерея + анимация + драг
- Переиспользуем примитивы из `StyleTab` (`ColorField`/`DebouncedSlider`/`Select`/`Checkbox`): цвет
  текста, плашка (цвет+непрозрачность / «без плашки»), контур, шрифт (`CAPTION_FONTS`), размер,
  позиция-от-ВЕРХА, UPPERCASE.
- Мини-галерея хук-пресетов (как `PresetStrip`, но значения хука) → один клик применяет look.
- Селектор анимации входа.
- Драг хука по видео (паритет с субтитрами; хук — верхний якорь, frac→margin_v от верха).
Все правки → существующий `handleHookChange` (та же очередь мутаций, без 409) + instant-превью (§4).

## 4. Задача B — дизайн (systematic-debugging)

### B-#2 — пресет стирает позицию (корень найден, фикс детерминирован)
`apply_preset` сохраняет ТЕКУЩИЙ `margin_v` (и `alignment`) клипа поверх пресета. Аналогично — для
хук-пресетов (не двигаем позицию хука). +unit-тест: применили пресет с margin_v=1100 на edit с
margin_v=400 → итог 400.

### B-#1 — задвоение/наложение субтитров (инструментировать → фикс по §6)
`setTrack` ЗАМЕНЯЕТ трек (не аппендит) → задвоение от (а) ДВУХ инстансов (StrictMode double-mount /
инстанс не `dispose()` при смене клипа/интервала) или (б) stale-кадра (нет редроу после setTrack).
Фикс в `LibassLayer`: гарантировать ОДИН инстанс; на смену ASS — `freeTrack()` затем `setTrack()` +
принудительный `setCurrentTime(video.currentTime − sourceStart)`; пустой ASS не сетим (issue #166).
Инструментируем (лог числа инстансов/вызовов setTrack), воспроизводим, проверяем глазами.

### B-#4 + B-#3 — лаги везде / драг (instant client preview)
**Решение — таргетный патч `Style:`-строк (НЕ полный TS-порт `compile_ass`).** Дрейфа на караоке/
анимации нет by-design (логику Dialogue не дублируем), ~40 строк вместо 350.
- **`apps/web/lib/assStyle.ts` (PURE):** берёт ПОСЛЕДНИЙ серверный ASS-текст и переписывает ТОЛЬКО
  строки `Style: Default,...` / `Style: Hook,...` (+ тогл хук-Dialogue) из текущих `style`/`hook` —
  формат точно зеркалит Python (`compile_ass`/`build_hook_event` style-строка). `setTrack` НЕМЕДЛЕННО.
  Покрывает доминанту фиддлинга: цвет/размер/шрифт/контур/тень/плашка/позиция(margin_v)/alignment/UPPERCASE.
- **Правки, меняющие Dialogue-теги** (highlight-цвет, анимация субтитров, emphasis) — РЕДКИЕ (выбор раз,
  не драг) → идут дебаунс-PATCH'ем на сервер (один roundtrip, не спамятся → не лагают).
- **Сервер — авторитетный:** PATCH дебаунсится (~300мс, коалесинг) в фоне; на ответ — refetch `/ass`
  и `setTrack` (реконсиляция). Экспорт ВСЕГДА из Python-ASS → дрейфа на экспорте нет.
- **Анти-дрейф (guard):** во фронте НЕТ TS-тест-раннера (`just check` = ruff+mypy+tsc+eslint+pytest), так что
  гард не CI-тест, а: (1) формат точно зеркалит Python (строки рядом в `assStyle.ts`); (2) РАЗОВЫЙ кросс-чек —
  `uv run` Python `compile_ass`/`build_hook_event` на эталонном style и `node` на `assStyle` → Style-строки
  байт-совпадают (verify-скрипт в tmp); (3) реконсиляция (серверный ASS перетирает за ~300мс → дрейф = макс.
  суб-секундный флик, НИКОГДА не неверный экспорт). Вводить vitest ради одного файла — скоуп-крип (не делаем).
- **Драг субтитров:** позиция едет ЖИВЬЁМ (локальный патч margin_v → `setTrack`, троттл rAF), PATCH — на
  отпускании. Сейчас двигался только гайд, субтитр стоял → «тормоза».

### B-#5 — ДОЛГОВЕЧНОСТЬ правок (no data loss) — жёсткое требование фаундера
Страх фаундера: «долго едитал клип → вышел на „все клипы“ → всё снеслось». Instant-preview +
дебаунс УВЕЛИЧИВАЕТ окно потери (правка показана локально, PATCH ещё не ушёл). Гарантии:
- Правки персистятся PATCH'ем в store (`store.save_edit`; на облаке Postgres) → reload грузит
  сохранённый edit-state (`getClipEdit`). База долговечности уже есть — НЕЛЬЗЯ терять «хвост» дебаунса.
- **Flush pending PATCH перед любым уходом:** навигация (‹ ›/«Все клипы»/смена таба), `pagehide`/
  `beforeunload` (через `navigator.sendBeacon`, т.к. fetch на unload режется), `visibilitychange→hidden`.
- Навигация «Все клипы»/клип-нав ЖДЁТ flush очереди мутаций (await `patchChain` + слив дебаунс-таймера)
  ДО `router.push`.
- Явный индикатор сохранения: `saving…` → `saved` (а не только dirty-чип «не в рендере»). Юзер видит,
  что состояние записано. dirty (не в рендере) и unsaved (PATCH в полёте) — РАЗНЫЕ вещи.

### B-#6 — «Все клипы» ведёт на дашборд, а не на грид клипов (фикс фаундера)
`EditorHeader` линк = `/dashboard?job=<id>` (deep-link ВЕРНЫЙ). Баг — **флеш «idle»**: на первом
рендере `jobParam` есть, но `start()` ещё не вызван → `phase==="idle"` рисует форму «Создать клипы»
(= «дашборд», что видит фаундер), потом effect → tracking → грид. На Modal cold-start флеш заметен →
кажется «выкинуло на дашборд, надо кликать ещё раз». Фикс в `dashboard/page.tsx`: если `?job=` есть —
НАЧАЛЬНАЯ фаза НЕ idle (loading-скелетон грида), пока джоб грузится; idle-форма только без `?job=`.

## 5. Границы / что НЕ трогаем
- ffmpeg-рендер (`stage5_render`), reframe-инвариант (`stage3_reframe`/`reframe_cache`). Пайплайн
  (download/transcribe/select). Таймлайн drag/resize. Деньги/биллинг.
- `models.py`/`packages/shared` правит ТОЛЬКО оркестратор (`just types`). Агенты — read-only на shared.

## 6. OSS-ресёрч (выжимка, источники в журнале)
- **Хук = отдельная пресет-галерея** (Submagic `hookTitle`: text/template/position/size; OpusClip
  «bold statement» пресеты, анимации динамичнее субтитров). Looks для копирования: Coral pill, Hormozi
  (контур, без плашки), Bold statement (fade-up), Typewriter brand.
- **libass-wasm API:** `setTrack(content)` (замена), `setTrackByUrl`, `freeTrack()` (удаляет),
  `setCurrentTime(t)`, `dispose()`. setTrack сам НЕ задваивает; источник — 2 инстанса / stale-кадр /
  пустой ASS (#166). Фикс: 1 инстанс + `dispose` на смену клипа + `setCurrentTime` после setTrack.
- **Instant-превью:** компилить ASS в браузере, `setTrack` напрямую (убирает PATCH→recompile→refetch).
  Сервер — source of truth для ffmpeg; идентичный алгоритм = нет дрейфа. Либы-референсы:
  `padraigfl/subtitle-ssa-styler`, `weizhenye/ASS`.

## 7. DoD
- A: HookTab показывает стиль-секцию + галерею + анимацию + драг; правки видны мгновенно в libass и
  совпадают с рендером; `just types` чистый; unit на `build_hook_event` анимации.
- B-#2: тест preset сохраняет margin_v; глазами — пресет не двигает позицию.
- B-#1: один инстанс libass, задвоение не воспроизводится (лог + глаза).
- B-#4/#3: правка цвета/размера/шрифта/контура/плашки/позиции — мгновенный превью (локальный патч
  `Style:`-строки); анимация/highlight — дебаунс-PATCH; `patchStyleLine`-тест зеркалит Python; драг живьём.
- B-#5: правки не теряются — reload/уход на «Все клипы» после долгой сессии сохраняет всё (flush на
  навигацию + `pagehide`/`beforeunload` через sendBeacon); индикатор `saving…/saved`.
- B-#6: «Все клипы» из редактора открывает грид клипов джоба напрямую (без флеша idle-дашборда).
- `just check` зелёный; `next build` зелёный; доки синхронны (README/JOURNAL/этот спек).
- Reframe-инвариант и ffmpeg-экспорт не тронуты.
