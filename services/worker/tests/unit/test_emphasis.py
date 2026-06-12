"""T3 — сочные субтитры: авто-подсветка ключевых слов. Pure-логика, тест-первым.

pick_keyword_positions выбирает «ударные» слова реплики (числа + длинные контентные,
без коротких/служебных) → compile_ass красит их emphasis_color в ТОМ ЖЕ ASS, что
рендерит ffmpeg → keyword-pop в ЭКСПОРТЕ, не только в CSS-превью (WYSIWYG цел).
"""

from app.editor.captions_v2 import compile_ass, pick_keyword_positions
from app.editor.timemap import ClipTimeMap
from app.models import CaptionReply, CaptionStyle, CaptionTrack, SourceInterval, Word


def _w(text, start, end):
    return Word(text=text, start=start, end=end)


def _cmap(dur=4.0):
    return ClipTimeMap([SourceInterval(source_start=0.0, source_end=dur)])


class TestPickKeywordPositions:
    def test_picks_longest_content_words(self) -> None:
        texts = ["Это", "был", "феноменальный", "результат"]
        # "феноменальный"(13) + "результат"(9) — два длиннейших контентных
        assert pick_keyword_positions(texts) == [2, 3]

    def test_number_is_keyword(self) -> None:
        # числа — главные keyword'ы (статистика останавливает скролл)
        texts = ["я", "заработал", "1000", "рублей"]
        got = pick_keyword_positions(texts)
        assert 2 in got  # "1000"

    def test_caps_at_max_emph(self) -> None:
        texts = ["огромный", "невероятный", "потрясающий", "результат", "проекта"]
        assert len(pick_keyword_positions(texts, max_emph=2)) == 2

    def test_excludes_short_and_stopwords(self) -> None:
        # "это"(3)/"был"(3) коротки; "которые"(7) и "просто"(6) — служебные стоп-слова
        texts = ["просто", "это", "которые", "иногда"]
        assert pick_keyword_positions(texts) == [3]  # только "иногда" (6, не стоп-слово)

    def test_strips_punctuation_for_length(self) -> None:
        texts = ["Невероятно!", "правда?"]
        assert pick_keyword_positions(texts) == [0, 1]

    def test_empty_and_punctuation_only(self) -> None:
        assert pick_keyword_positions(["...", "—", "a", "и"]) == []


class TestCompileAssAutoEmphasis:
    def test_auto_colors_keyword_when_emphasis_color_set(self) -> None:
        words = [_w("Это", 0.0, 0.4), _w("феноменально", 0.4, 1.0)]
        track = CaptionTrack(
            style=CaptionStyle(uppercase=False, emphasis_color="#FF0000"),
            highlight=None,
            replies=[CaptionReply(word_refs=[0, 1])],  # без явных emphasis_refs
        )
        ass = compile_ass(track, words, _cmap())
        d = next(ln for ln in ass.splitlines() if ln.startswith("Dialogue:"))
        # "феноменально" (длинное) окрашено в #FF0000 → инлайн &H0000FF&
        assert "{\\1c&H0000FF&}феноменально" in d

    def test_explicit_refs_override_auto(self) -> None:
        # если юзер задал emphasis_refs вручную — авто НЕ вмешивается
        words = [_w("раз", 0.0, 0.4), _w("феноменально", 0.4, 1.0)]
        track = CaptionTrack(
            style=CaptionStyle(uppercase=False, emphasis_color="#00FF00"),
            highlight=None,
            replies=[CaptionReply(word_refs=[0, 1], emphasis_refs=[0])],  # «раз» вручную
        )
        ass = compile_ass(track, words, _cmap())
        d = next(ln for ln in ass.splitlines() if ln.startswith("Dialogue:"))
        assert "{\\1c&H00FF00&}раз" in d  # подсвечено именно ручное слово

    def test_auto_off_when_flag_false(self) -> None:
        words = [_w("феноменально", 0.0, 1.0)]
        track = CaptionTrack(
            style=CaptionStyle(uppercase=False, emphasis_color="#FF0000", emphasis_auto=False),
            highlight=None,
            replies=[CaptionReply(word_refs=[0])],
        )
        ass = compile_ass(track, words, _cmap())
        assert "\\1c" not in ass  # авто выключено, явных refs нет → без покраски

    def test_no_emphasis_color_no_auto(self) -> None:
        words = [_w("феноменально", 0.0, 1.0)]
        track = CaptionTrack(
            style=CaptionStyle(uppercase=False),  # emphasis_color=None
            highlight=None,
            replies=[CaptionReply(word_refs=[0])],
        )
        ass = compile_ass(track, words, _cmap())
        assert "\\1c" not in ass
