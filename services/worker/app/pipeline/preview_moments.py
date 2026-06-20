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

from app.models import PreviewMoment, Word

_BEAT_MIN_GAP_S = 0.6  # пауза (сек) перед словом, чтобы считать её «затактом»
_BEAT_FULL_GAP_S = 2.0  # пауза, дающая intensity=1.0 (линейно от _BEAT_MIN_GAP_S)


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
    cand.sort(key=lambda m: m.t)
    # разрежение по времени: идём по возрастанию t, держим маркер только если он дальше min_gap_s
    # от последнего удержанного ЛИБО сильнее его (тогда заменяем — сильный момент важнее).
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
