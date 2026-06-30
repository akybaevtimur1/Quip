"""Composite-ASS fast download path: pure gate + ffmpeg command builder.

Готовый чистый клип ``clips/<id>.mp4`` — это УЖЕ reframe+watermark+clip-time база (1080×1920,
та же, что показывает грид/превью), БЕЗ субтитров. Когда правка клипа caption/hook-only (один
дефолтный интервал, без кропа/аспекта/трима — геометрия НЕ меняется), «download с субтитрами»
можно сделать ОДНИМ коротким энкодом: прожечь ASS поверх baked-клипа. Это пропускает дорогой
полный путь (скачать весь source → CV reframe → reframe-фильтрграф) ради секунд вместо минут.

Здесь — ТОЛЬКО pure-логика (предикат гейта + сборка команды), под unit-тестами. I/O (скачать
baked-клип, запустить ffmpeg) живёт в ``tasks.render_edit_to_file`` (оркестратор).
"""

from __future__ import annotations

from app.models import ClipEdit

# Baked-клип всегда рендерится в 9:16 (run.render_one_clip: clamp_output_dims(1080,1920,...)).
# Любой другой аспект edit'а → геометрия не совпадает с baked → fast-path НЕЛЬЗЯ.
_BAKED_ASPECT = "9:16"


def edit_matches_baked(
    edit: ClipEdit, *, seg_start: float, seg_end: float, tol: float = 0.05
) -> bool:
    """PURE. True ⇔ edit — нетронутая-по-геометрии caption/hook-only правка, чьи кадры совпадают
    с baked-клипом ``clips/<id>.mp4`` (можно прожечь субтитры поверх него, без пересчёта reframe).

    Условия (ВСЕ обязательны — иначе геометрия baked-клипа уже не та):
      • ``aspect == "9:16"`` — baked всегда 9:16; другой аспект = другой кадр.
      • нет ``reframe_overrides`` — ручной кроп меняет регионы → нужен пересчёт.
      • РОВНО один source-интервал — мульти-интервал = пере-монтаж (concat), не один клип.
      • границы интервала совпадают с сегментом (в пределах ``tol``) — клип не тримили/не сдвигали
        (baked рендерился именно из [seg_start, seg_end]; default_clip_edit сидит этот интервал).
    Субтитры/хук НЕ влияют на геометрию — их и накладываем поверх baked. Любое НЕсовпадение →
    False → вызыватель идёт полным путём (корректность важнее скорости).
    """
    if edit.aspect != _BAKED_ASPECT:
        return False
    if edit.reframe_overrides:
        return False
    if len(edit.source_intervals) != 1:
        return False
    iv = edit.source_intervals[0]
    return abs(iv.source_start - seg_start) <= tol and abs(iv.source_end - seg_end) <= tol


def can_composite_captions(
    edit: ClipEdit,
    *,
    seg_start: float,
    seg_end: float,
    baked_clip_exists: bool,
    tol: float = 0.05,
) -> bool:
    """PURE. Полный гейт fast-vs-full: baked-клип ЕСТЬ И edit совпадает по геометрии (см.
    ``edit_matches_baked``). True → composite-ASS fast-path; False → полный render_timeline.

    Существование baked-клипа — отдельный аргумент (его проверяет/скачивает I/O-слой), чтобы
    решение целиком оставалось чистым и тестируемым.
    """
    if not baked_clip_exists:
        return False
    return edit_matches_baked(edit, seg_start=seg_start, seg_end=seg_end, tol=tol)


def build_composite_ass_cmd(
    clip_in: str, ass_filter: str, out_name: str, *, crf: int = 20, preset: str = "veryfast"
) -> list[str]:
    """PURE. ffmpeg-команда composite-ASS: прожечь субтитры поверх baked-клипа, аудио — копией.

    ``clip_in`` (baked ``clips/<id>.mp4``), ``ass_filter`` (готовый ``subtitles=...:fontsdir=...``
    — тот же, что у полного рендера, см. stage5_render._subtitles_filter) и ``out_name`` —
    ОТНОСИТЕЛЬНЫЕ пути от cwd ffmpeg (= job_dir), как в полном пути. Видео ре-энкодим (прожиг
    субтитров требует энкода) с crf/preset из RenderPolicy владельца; аудио ``-c:a copy`` (в
    baked уже aac — НЕ ре-энкодим зря). ``+faststart`` — moov вперёд (мгновенный старт в браузере).
    """
    return [
        "ffmpeg", "-y", "-i", clip_in,
        "-vf", ass_filter,
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p",
        "-c:a", "copy", "-movflags", "+faststart",
        out_name,
    ]  # fmt: skip
