"""Косметический детектор «моментов» для co-watch-превью во время обработки (Part 4). PURE.

⚠️ ИНВАРИАНТ КАЧЕСТВА: результат ПОКАЗЫВАЕТСЯ юзеру (маркеры на скраббере, пока идёт обработка),
но НИКОГДА не передаётся в `select_segments`/LLM. Отбор клипов — единственный источник правды —
от этих маркеров НЕ зависит → качество AI-нарезки не меняется (founder-гейт: «magic in the eyes»).

Сигналы языко-нейтральны (пунктуация/цифры/паузы), чтобы работать и на RU, и на EN без словарей:
  • question  — слово оканчивается на «?»  (вопрос — крючок).
  • emphasis  — слово оканчивается на «!»  (восклицание/нажим).
  • stat      — в слове есть цифра          (число/статистика).
  • beat      — большая пауза ПЕРЕД словом  (затакт/панчлайн), intensity растёт с длиной паузы.
Маркеры разрежаются (min_gap_s) и обрезаются до max_moments (держим самые сильные), порядок по t.
"""

from __future__ import annotations

import statistics
import subprocess

from app.models import PreviewMoment, Word

_BEAT_MIN_GAP_S = 0.6  # пауза (сек) перед словом, чтобы считать её «затактом»
_BEAT_FULL_GAP_S = 2.0  # пауза, дающая intensity=1.0 (линейно от _BEAT_MIN_GAP_S)


def _space_and_cap(
    cand: list[PreviewMoment], max_moments: int, min_gap_s: float
) -> list[PreviewMoment]:
    """Отсортировать по t, разредить (не ближе min_gap_s — держим сильнейший в окне), обрезать до
    max_moments (оставляя самые сильные), вернуть по возрастанию t. PURE."""
    cand = sorted(cand, key=lambda m: m.t)
    spaced: list[PreviewMoment] = []
    for m in cand:
        if spaced and m.t - spaced[-1].t < min_gap_s:
            if m.intensity > spaced[-1].intensity:
                spaced[-1] = m
            continue
        spaced.append(m)
    if len(spaced) > max_moments:
        spaced = sorted(spaced, key=lambda m: m.intensity, reverse=True)[:max_moments]
        spaced.sort(key=lambda m: m.t)
    return spaced


def _classify(word: Word, prev_end: float | None) -> PreviewMoment | None:
    """Одно слово (+ конец предыдущего) → PreviewMoment или None. PURE."""
    text = word.text.strip()
    if not text:
        return None
    # Сначала контент-сигналы (информативнее), beat (пауза) — фолбэк для «пустых» слов.
    if text.endswith("?"):
        return PreviewMoment(t=round(word.start, 2), kind="question", intensity=0.75)
    if text.endswith("!"):
        return PreviewMoment(t=round(word.start, 2), kind="emphasis", intensity=0.85)
    if any(ch.isdigit() for ch in text):
        return PreviewMoment(t=round(word.start, 2), kind="stat", intensity=0.6)
    # пауза перед (обычным) словом → beat (язык-нейтрально, часто предшествует панчлайну)
    if prev_end is not None:
        gap = word.start - prev_end
        if gap >= _BEAT_MIN_GAP_S:
            span = _BEAT_FULL_GAP_S - _BEAT_MIN_GAP_S
            intensity = 0.5 + 0.5 * min(1.0, (gap - _BEAT_MIN_GAP_S) / span) if span > 0 else 1.0
            return PreviewMoment(t=round(word.start, 2), kind="beat", intensity=round(intensity, 2))
    return None


def detect_preview_moments(
    words: list[Word], *, max_moments: int = 14, min_gap_s: float = 1.5
) -> list[PreviewMoment]:
    """Слова транскрипта → косметические маркеры-моменты (НЕ для LLM-отбора). PURE.

    1) классифицируем каждое слово; 2) разрежаем (не ближе min_gap_s — держим сильнейший в окне);
    3) если осталось > max_moments — оставляем самые сильные; 4) сортируем по t.
    """
    cand: list[PreviewMoment] = []
    prev_end: float | None = None
    for w in words:
        m = _classify(w, prev_end)
        if m is not None:
            cand.append(m)
        prev_end = w.end
    return _space_and_cap(cand, max_moments, min_gap_s)


def detect_energy_moments(
    rms_db: list[float], hop_s: float = 0.5, *, max_moments: int = 10, min_gap_s: float = 2.5
) -> list[PreviewMoment]:
    """Кривая громкости (RMS в dB, по окнам hop_s сек) → маркеры «emphasis» на ПИКАХ. PURE.

    Доступны РАНО (сразу после download, ещё ДО transcribe), поэтому покрывают самый длинный
    кусок ожидания. Пик = локальный максимум заметно выше медианы. intensity = насколько пик
    выше медианы (нормировано на размах). Язык-нейтрально, не зависит от транскрипта/LLM.
    """
    n = len(rms_db)
    if n < 3:
        return []
    med = statistics.median(rms_db)
    hi = max(rms_db)
    if hi - med < 1.0:  # ровная громкость → нет выраженных пиков
        return []
    thr = med + 0.4 * (hi - med)  # порог: заметно выше медианы
    cand: list[PreviewMoment] = []
    for i in range(1, n - 1):
        v = rms_db[i]
        if v >= thr and v >= rms_db[i - 1] and v >= rms_db[i + 1]:
            intensity = round(min(1.0, max(0.0, (v - med) / (hi - med))), 2)
            cand.append(PreviewMoment(t=round(i * hop_s, 2), kind="emphasis", intensity=intensity))
    return _space_and_cap(cand, max_moments, min_gap_s)


def merge_moments(
    *groups: list[PreviewMoment], max_moments: int = 16, min_gap_s: float = 1.5
) -> list[PreviewMoment]:
    """Объединить наборы маркеров (энергия + транскрипт) в один разрежённый список. PURE."""
    flat: list[PreviewMoment] = [m for g in groups for m in g]
    return _space_and_cap(flat, max_moments, min_gap_s)


def extract_loudness(audio_path: str, *, hop_s: float = 0.5) -> list[float]:
    """RMS-громкость (dB) аудио по окнам hop_s сек через ffmpeg→numpy. БЕСТ-ЭФФОРТ (косметика).

    Декодируем mono 8 kHz s16le в память, RMS по непересекающимся окнам → dBFS. Любой сбой
    (нет ffmpeg/numpy/битый файл) → [] (вызывающий не покажет энергетические маркеры; пайплайн
    НЕ падает — фича визуальная). Не PURE (I/O); пик-пик — в detect_energy_moments.
    """
    sr = 8000
    try:
        import numpy as np

        proc = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", audio_path, "-ac", "1", "-ar", str(sr),
             "-f", "s16le", "-"],
            capture_output=True, timeout=120,
        )  # fmt: skip
        if proc.returncode != 0 or not proc.stdout:
            return []
        samples = np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0
        win = max(1, int(sr * hop_s))
        usable = (len(samples) // win) * win
        if usable < win:
            return []
        frames = samples[:usable].reshape(-1, win)
        rms = np.sqrt(np.mean(frames * frames, axis=1) + 1e-9)
        db = 20.0 * np.log10(rms + 1e-9)
        return [float(x) for x in db]
    except Exception as e:  # noqa: BLE001 — косметика: любой сбой → без энергетических маркеров
        print(f"[extract_loudness] WARN {audio_path}: {e}")
        return []
