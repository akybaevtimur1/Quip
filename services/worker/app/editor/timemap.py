"""Clip-time ↔ source-time mapping (спека §4). ЕДИНАЯ точка таймингов клипа.

Все ошибки «±длина клипа / съехавшие субтитры» живут только здесь. PURE, под тестами.
"""

from __future__ import annotations

from app.errors import JobError
from app.models import SourceInterval

_STAGE = "editor"


class ClipTimeMap:
    """Кусочно-линейное отображение по интервалам (упорядочены по CLIP-порядку).

    clip-полоса k: [C_k, C_k + L_k), где C_k = сумма длин предыдущих, L_k = длина интервала.
    """

    def __init__(self, intervals: list[SourceInterval]) -> None:
        if not intervals:
            raise JobError(_STAGE, "ClipTimeMap: empty interval list")
        self.intervals = list(intervals)
        self.lengths = [max(0.0, iv.source_end - iv.source_start) for iv in intervals]
        self.band_starts: list[float] = []
        acc = 0.0
        for length in self.lengths:
            self.band_starts.append(round(acc, 3))
            acc += length
        self.clip_duration = round(acc, 3)

    def source_to_clip(self, t_src: float) -> float | None:
        """source-время → clip-время; None если t_src в дырке (вне всех интервалов)."""
        for k, iv in enumerate(self.intervals):
            if iv.source_start <= t_src < iv.source_end:
                return round(self.band_starts[k] + (t_src - iv.source_start), 3)
        return None

    def clip_to_source(self, t_clip: float) -> tuple[int, float]:
        """clip-время → (индекс интервала, source-время). Клипуется в [0, clip_duration]."""
        for k, length in enumerate(self.lengths):
            c0 = self.band_starts[k]
            last = k == len(self.lengths) - 1
            if c0 <= t_clip < c0 + length or (last and t_clip <= c0 + length + 1e-6):
                off = min(max(0.0, t_clip - c0), length)
                return k, round(self.intervals[k].source_start + off, 3)
        return 0, round(self.intervals[0].source_start, 3)

    def interval_clip_band(self, k: int) -> tuple[float, float]:
        """(C_k, C_k + L_k) — clip-полоса интервала k (для рендера/субтитров)."""
        return self.band_starts[k], round(self.band_starts[k] + self.lengths[k], 3)
