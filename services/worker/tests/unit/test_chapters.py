"""AI-карта видео: PURE-постобработка глав (сортировка/кламп/непрерывность)."""

from app.editor.chapters import postprocess_chapters
from app.models import Chapter


def _ch(s: float, e: float, t: str = "t", m: str = "m") -> Chapter:
    return Chapter(start=s, end=e, title=t, summary=m)


def test_postprocess_sorts_and_clamps() -> None:
    out = postprocess_chapters([_ch(50, 999), _ch(-5, 20)], duration=100)
    assert [c.start for c in out] == [0.0, 50.0]
    assert out[-1].end == 100.0


def test_postprocess_fills_gaps_to_contiguous() -> None:
    # Главы покрывают видео непрерывно: дыра 30..40 поглощается предыдущей главой.
    out = postprocess_chapters([_ch(0, 30), _ch(40, 100)], duration=100)
    assert out[0].end == 40.0
    assert out[1].start == 40.0


def test_postprocess_overlap_cut() -> None:
    # Перекрытие: текущая глава режется от конца предыдущей.
    out = postprocess_chapters([_ch(0, 50), _ch(30, 100)], duration=100)
    assert out[0].end == 50.0
    assert out[1].start == 50.0


def test_postprocess_drops_tiny_and_invalid() -> None:
    out = postprocess_chapters([_ch(0, 0.5), _ch(20, 10), _ch(0, 100)], duration=100)
    assert len(out) == 1
    assert out[0].start == 0.0 and out[0].end == 100.0


def test_postprocess_empty() -> None:
    assert postprocess_chapters([], duration=100) == []


def test_postprocess_strips_whitespace() -> None:
    out = postprocess_chapters([_ch(0, 100, t="  Интро  ", m=" суть ")], duration=100)
    assert out[0].title == "Интро" and out[0].summary == "суть"
