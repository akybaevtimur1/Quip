# ClipFlow heavy worker on Modal — спайк-scaffold

Перенос ТЯЖЁЛОЙ части пайплайна (reframe-анализ лиц/склеек + рендер 9:16, ~6 мин компьюта/видео
на CPU) на **Modal** (serverless GPU, auto-scale, scale-to-zero) + замер реальной стоимости/времени.

> Это ТОЛЬКО scaffold тяжёлого воркера. Лёгкие API/БД/фронт остаются на Vercel/Supabase.
> Полная миграция storage/БД — отдельная сессия.

## Что гоняется

Точно та же тройка функций, что и REST-путь редактора (`services/worker/app/tasks.py::render_edit_to_file`),
без дублирования логики — импортируется наш реальный код:

| Функция | Модуль | Что делает (тяжёлое) |
|---|---|---|
| `analyze_source_range` | `app.editor.reframe_cache` | ffmpeg (кадры+scene-detect) + MediaPipe FaceDetector + PySceneDetect |
| `resolve_regions` | `app.editor.reframe_cache` | PURE cut-aligned планировщик (мгновенно) |
| `render_timeline` | `app.pipeline.stage5_render` | ffmpeg crop/scale/concat → mp4 9:16 |

Сэмпл-клип = первый сегмент (~55с) реального прогона `data/job_17bb726bc1ec` (1920×1080).
Рендерим **без субтитров** (`ass_name=None`): весь тяжёлый компьют сохранён (детект лиц +
scene-detect + ffmpeg-кодировка), но не тянем на Modal транскрипт/ASS — замер репрезентативен.

## Команды (для фаундера)

```bash
# 1) Поставить Modal CLI в ЛЮБОЙ venv (НЕ в pyproject воркера — это отдельный dev-инструмент).
pip install modal
#   либо изолированно, как делал агент:
#   python -m venv deploy/modal/.venv-modal && deploy/modal/.venv-modal/Scripts/python -m pip install modal

# 2) ОДИН раз — авторизация (откроет браузер; агент это сделать НЕ может).
modal setup
#   эквивалент: modal token new

# 3) Деплой образа + удалённый прогон на GPU + печать замера/стоимости.
modal run deploy/modal/app.py
#   эквивалентно явно:
modal run deploy/modal/app.py::measure
#   либо через тонкую обёртку:
modal run deploy/modal/measure.py
```

Первый `modal run` соберёт GPU-образ (torch CUDA + mediapipe + scenedetect + ffmpeg) —
это занимает несколько минут ОДИН раз; далее образ кэшируется.

### Вывод замера

`measure()` печатает таблицу: GPU-тип, доступность CUDA, длительность клипа, время каждой
фазы (analyze / resolve / render), размер mp4, чистый компьют, wall-время (с cold-start) и
**оценку стоимости за клип** (по wall и по компьюту, на основе per-second GPU-прайса Modal).

GPU по умолчанию — **A10G** (`_GPU` в `app.py`). Сменить на T4/L4/A100 → поменять одну строку.

## Что провалидировано БЕЗ авторизации

Агент не может пройти браузерную `modal setup`, поэтому валидировано всё до auth-границы:

- ✅ `app.py` импортируется под Modal 1.5.0, App/Image-граф собирается, GPU-функция
  `reframe_and_render_sample` зарегистрирована (проверено import-чеком).
- ✅ Реальная цепочка импортов пайплайна (`analyze_source_range`/`resolve_regions`/
  `render_timeline` + модели + построение `ClipEdit`) исполняется в venv воркера — логика
  рантайм-функции корректна.
- ✅ `modal run deploy/modal/app.py` И `...::measure` И `measure.py` доходят до
  **«Token missing. Could not authenticate client.»** — т.е. локальный граф и спецификация
  образа валидны, CLI упирается ТОЛЬКО в отсутствие токена. Это ожидаемо.
- ✅ Сэмпл-данные на месте: `source.mp4` (56 МБ), `meta.json`, `segments.json`; шрифты.

## Требует `modal setup` (founder)

- Реальная сборка GPU-образа на стороне Modal (скачивание torch-cu124, mediapipe и т.д.).
- Сам GPU-прогон и **фактические** цифры времени/стоимости.

## Образ / зависимости (рантайм)

Заданы в `app.py` через `Image.apt_install/.pip_install` (НЕ в pyproject воркера):

- apt: `ffmpeg`, `libgl1`, `libglib2.0-0` (рантайм opencv).
- pip: `torch>=2.2` + `torchaudio` с `--extra-index-url https://download.pytorch.org/whl/cu124`
  (CUDA-колесо — на Linux+GPU), `mediapipe`, `scenedetect`, `numpy`, `scipy`, `pydantic`,
  `pydantic-settings`, `httpx`, `python_speech_features`.
- Зеркало `services/worker/pyproject.toml`, обрезанное до reframe+render: БЕЗ yt-dlp/bgutil
  (скачивание = лёгкий путь), БЕЗ anthropic/google-genai/deepgram (LLM/транскрипция = лёгкий путь),
  БЕЗ dev/линтеров.
- Пакет `app` + `fonts` + сэмпл-джоб монтируются `add_local_dir(..., copy=True)` (в слой образа).

## Грабли (важно)

- **`include_source=False` на `App`** — обязательно. Иначе Modal авто-монтирует директорию
  энтрипоинта и делает сам `app.py` модулем `app`, что коллизирует с пакетом `app/`
  (смонтирован в `/root/app`). Отключено → пакет берётся только из `add_local_dir`.
- **API-ключи НЕ нужны.** Тяжёлый путь не импортирует `app.config` (проверено grep'ом по
  цепочке) → Deepgram/Gemini-ключи на Modal не требуются.
- **torch CUDA-колесо** ставится отдельным `.pip_install(..., extra_index_url=cu124)`, иначе
  тянется CPU-вариант (как в воркере на Windows) и GPU простаивает.
- **MediaPipe на Linux** требует `libgl1`+`libglib2.0-0` (apt) — иначе ImportError на opencv.
- **ASD active-speaker путь сейчас НЕ задействован** этим замером (analyze-путь использует
  MediaPipe+PySceneDetect, не torch). torch в образе — на будущее (speaker-reframe). ⚠️ Сам
  ASD-скорер (`app/asd/scorer.py`) ЗАХАРДКОЖЕН на CPU (`map_location="cpu"`, тензоры без `.cuda()`):
  чтобы ASD реально ускорился на GPU, его надо сделать device-aware (отдельная задача).
- **GPU-выигрыш этого замера** идёт в основном от ffmpeg-кодировки (можно перевести на NVENC:
  `-c:v h264_nvenc` в `build_single_pass_cmd` [путь 1 интервала, наш сэмпл] и `build_timeline_cmd`
  [мульти-интервал] — сейчас `libx264` на CPU) и быстрее CPU инстанса Modal. Для большого
  ускорения reframe — NVENC + device-aware ASD (следующий шаг).
- **Cold start**: первый вызов тянет импорт torch/mediapipe (десятки секунд) → wall-стоимость
  выше «по-компьюту». На прогретом инстансе (scale-to-zero с keep_warm/буфером) ≈ по компьюту.
- **Размер образа** большой (torch CUDA ~3-4 ГБ + mediapipe) — нормально для Modal (кэшируется),
  влияет только на первую сборку.

## Файлы

- `app.py` — Modal App + GPU-образ + функция `reframe_and_render_sample` + энтрипоинт `measure`.
- `measure.py` — тонкая обёртка (реэкспорт), чтобы `modal run measure.py` читалось как «замер».
- `.venv-modal/` — изолированный venv с Modal CLI (создан агентом; игнорится `deploy/modal/.gitignore`).
- `.gitignore` — исключает локальный venv замера из коммита.
