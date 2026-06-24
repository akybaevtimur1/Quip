# BE-C (Reframe ⚠️INVARIANT) — отчёт агента

## Сводка
- Файлов проверено: 5 (`pipeline/stage3_reframe.py`, `pipeline/stage3_speaker.py`,
  `pipeline/asd_reframe.py`, `asd/scorer.py` + `asd/_vendor/*`, `editor/reframe_cache.py`)
- Багов найдено: 1 (crit 0 / high 1 / med 0 / low 0)
- Багов починено: 1
- **Кадровая сетка (frame-grid) НЕ ТРОНУТА** — фикс чисто в release-ресурса (finally),
  никакой math по cuts/shots/regions/trim не менялась. Δ=0 инвариант цел по построению.
- Тесты добавлены: 2 (release-on-failure + release-on-success).
  Прогон: `uv run python -m pytest tests/unit/test_stage3_reframe.py
  tests/unit/test_stage3_speaker.py tests/unit/test_reframe_resolve.py -q`
  → **87 passed in 0.42s** (было 85). ruff + mypy на правленых файлах: чисто.

## Баги

### [HIGH] Незакрытый VideoCapture на ошибке detect_scenes → Windows file-lock маскирует ошибку — stage3_reframe.py:559-572
**Симптом:** Если `PySceneDetect.detect_scenes(vid)` падает в середине (битый кадр /
проблема декода), `detect_scene_cuts` ловит исключение и поднимает `JobError` —
но `vid.capture.release()` стоял ТОЛЬКО на success-пути (последней строкой `try`).
На Windows незакрытый `cv2.VideoCapture` держит файл-лок на temp `seg.mp4`. При выходе
из `with tempfile.TemporaryDirectory()` cleanup пытается удалить залоченный файл →
бросает вторичный `PermissionError`, который **МАСКИРУЕТ исходную JobError** (юзер
видит «WinError 32», а не реальную причину сбоя reframe) и оставляет мусорный temp.
Это именно тот класс Windows-лока, о котором предупреждает HANDOFF §9 / комментарий
в коде — но релиз срабатывал только когда всё прошло хорошо, т.е. там, где лок и так
не страшен.
**Корень:** `vid.capture.release()` был внутри `try` после `get_scene_list()`, а не в
`finally`. На любой exception до этой строки release не вызывался.
**Фикс:** `vid = None` перед `try`; `release()` перенесён в `finally` с guard'ом
`vid is not None and hasattr(...)`. Контракт возврата (`scenes[1:]` → start-кадр сцены)
не тронут — это та же frame-grid семантика, что и раньше.
**Тест:** `TestDetectSceneCutsResourceRelease` — мокает `subprocess.run` (ffmpeg ok) +
символы `scenedetect`; `test_release_called_on_detect_failure` (detect_scenes бросает →
release всё равно вызван 1 раз, JobError проброшена) и `test_release_called_on_success`
(нормальный путь: cuts == [50], release 1 раз — frame-grid контракт зафиксирован тестом).

## Передать оркестратору (чужие/общие файлы)
- Нет правок в чужих/общих файлах. `models.py`, `stage5_render.py` не трогал.

## Не успел / открыто (задокументировано, НЕ чинил — осознанно консервативно)
- **fps==0 div-by-zero в pure-функциях** (`plan_regions`/`_split_pair`: `t0,t1 = f0/fps,...`;
  `resample_track`: `track.f0/src_fps`). НЕ достижимо в продукте: единственный вызыватель
  `reframe_segment` всегда передаёт нативный `meta.fps > 0`. Добавление guard'а изменило бы
  поведение pure-функций без реального триггера → оставил как есть (документирую).
- **`asd/_vendor/*` (loss.py, Model.py) и `asd/scorer.py` форвард** — вендоренный LR-ASD
  (MIT), логика 1:1 с проверенным спайком; `*25`/`*100` — контракт модели
  (REFRAME_FPS_GRID_INVARIANT §«Почему ASD нельзя…»). Не трогал. Частичная загрузка
  state_dict (пропуск несовпадающих ключей в `_load_net`) — НАМЕРЕННАЯ (разное имя модулей
  `module.` префикс), не silent-failure нашего кода.
- **`resolve_regions` / `analyze_source_range`** (editor LEGACY/benchmark-only путь, D4):
  cuts в секундах + 5fps без ASD → на ≠25fps дал бы флеши, но уже зафенсен в docstring и
  НЕ вызывается из продуктового кода (продукт идёт через `resolve_regions_accurate`). Багов
  внутри (как изолированной pure-логики) не нашёл; флеш-риск — это его документированный
  дизайн, не баг для починки.
- **`score_tracks_in_segment` audio-slice / `_crop_faces` frame-index** — проверил границы:
  `build_tracks` интерполирует только между существующими кадрами (≤ len(frames)-1), numpy
  slice клампит → IndexError/crash не достижим. Чисто.
