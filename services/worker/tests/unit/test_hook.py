"""T1/T2 — топ-текст (хук) + богатый reasoning. Pure-логика, тест-первым.

Хук = объяснимый цепляющий заголовок (наш отличитель vs Vizard). Рендерится отдельным
ASS-событием с ВЕРХНИМ якорем (alignment 8) тем же libass-стеком, что субтитры →
превью = экспорт, без второго пайплайна. Вся баг-опасная сборка ASS — PURE под тестами.
"""

from app.editor.captions_v2 import build_hook_event, compile_ass
from app.editor.replies import default_caption_track
from app.editor.timemap import ClipTimeMap
from app.models import (
    CaptionReply,
    CaptionStyle,
    CaptionTrack,
    ClipOut,
    HookOverlay,
    Segment,
    SourceInterval,
    Word,
)


def _w(text, start, end):
    return Word(text=text, start=start, end=end)


def _cmap(dur=12.0):
    return ClipTimeMap([SourceInterval(source_start=0.0, source_end=dur)])


# ─────────────────────────── модель ───────────────────────────


class TestHookOverlayModel:
    def test_defaults(self) -> None:
        h = HookOverlay()
        assert h.text == ""
        assert h.enabled is True
        assert h.font == "Unbounded"  # шрифт уже в обоих местах (fonts/ + public/libass/fonts)
        assert h.uppercase is True

    def test_caption_track_hook_default_none(self) -> None:
        # хук опционален: трек без хука валиден (старый кэш не ломается)
        track = CaptionTrack(style=CaptionStyle())
        assert track.hook is None


class TestSegmentReasoningFields:
    def test_segment_hook_and_why_works_optional(self) -> None:
        # default None → не required в JSON-схеме → старые segments.json валидны
        seg = Segment(start=0, end=20, reason="r", score=0.8, type="hook")
        assert seg.hook is None
        assert seg.why_works is None

    def test_segment_carries_hook_and_why(self) -> None:
        seg = Segment(
            start=0, end=20, reason="r", score=0.8, type="hook",
            hook="Он потерял всё за один день", why_works="Конфликт + ставка в первой фразе",
        )  # fmt: skip
        assert seg.hook == "Он потерял всё за один день"
        assert seg.why_works == "Конфликт + ставка в первой фразе"

    def test_clipout_reasoning_fields_optional(self) -> None:
        c = ClipOut(
            id="clip_01", start=0, end=20, duration=20, reason="r", type="hook",
            score=0.8, video_url="clips/clip_01.mp4", transcript="t", words=[],
        )  # fmt: skip
        assert c.hook is None and c.why_works is None


# ─────────────────────────── build_hook_event (PURE) ───────────────────────────


class TestBuildHookEvent:
    def test_returns_style_and_dialogue(self) -> None:
        style, dialogue = build_hook_event(HookOverlay(text="Привет"), clip_duration=12.0)
        assert style.startswith("Style: Hook,")
        assert dialogue.startswith("Dialogue: 0,0:00:00.00,")

    def test_chosen_font_in_style_for_english_hook(self) -> None:
        # Regression guard: changing the hook font must reach the burned ASS Style line.
        # English text → resolve_font_for_text is a no-op (no Cyrillic fallback) → the EXACT
        # chosen family is emitted as field 1 (Fontname). The "wrong font on download" bug was
        # NOT here (worker is correct) but in the editor flow (un-flushed edit + stale baked
        # render); this pins the worker contract so a future change can't silently regress it.
        style, _ = build_hook_event(
            HookOverlay(text="This changes everything", font="Bebas Neue"), clip_duration=10.0
        )
        assert style.split(",")[1] == "Bebas Neue"

    def test_top_alignment_and_margin(self) -> None:
        style, _ = build_hook_event(HookOverlay(text="x", margin_v=150), clip_duration=10.0)
        fields = style.split(",")
        assert fields[18] == "8"  # alignment 8 = top-center (не пересекается с нижними)
        assert fields[21] == "150"  # MarginV от верха

    def test_box_sets_border_style_3(self) -> None:
        style, _ = build_hook_event(
            HookOverlay(text="x", box_color="#FF5A3D", box_opacity=1.0), clip_duration=10.0
        )
        assert style.split(",")[15] == "3"

    def test_box_color_drives_outline_fill(self) -> None:
        # libass BorderStyle=3 заливает ПЛАШКУ цветом OutlineColour (поле 5), не BackColour.
        # box_color кладём туда → плашка реально коралл (баг найден на реальном рендере:
        # коралл в BackColour → плашка рисовалась чёрной outline'ом).
        style, _ = build_hook_event(
            HookOverlay(text="x", box_color="#FF5A3D", box_opacity=1.0), clip_duration=10.0
        )
        # #FF5A3D → BGR 3D5AFF, opaque alpha 00 → &H003D5AFF
        assert style.split(",")[5] == "&H003D5AFF"

    def test_no_box_border_style_1(self) -> None:
        style, _ = build_hook_event(HookOverlay(text="x", box_color=None), clip_duration=10.0)
        assert style.split(",")[15] == "1"

    def test_full_clip_window(self) -> None:
        _, dialogue = build_hook_event(HookOverlay(text="x", full_clip=True), clip_duration=12.34)
        assert "0:00:12.34" in dialogue  # окно = весь клип

    def test_first_n_seconds_window(self) -> None:
        _, dialogue = build_hook_event(
            HookOverlay(text="x", full_clip=False, duration_sec=4.0), clip_duration=12.0
        )
        assert "0:00:04.00" in dialogue

    def test_first_n_clamped_to_clip(self) -> None:
        # duration_sec длиннее клипа → окно не выходит за длину клипа
        _, dialogue = build_hook_event(
            HookOverlay(text="x", full_clip=False, duration_sec=99.0), clip_duration=8.0
        )
        assert "0:00:08.00" in dialogue

    def test_uppercase(self) -> None:
        _, dialogue = build_hook_event(HookOverlay(text="привет мир"), clip_duration=10.0)
        assert "ПРИВЕТ МИР" in dialogue

    def test_lowercase_preserved(self) -> None:
        _, dialogue = build_hook_event(
            HookOverlay(text="привет", uppercase=False), clip_duration=10.0
        )
        assert "привет" in dialogue

    def test_escapes_braces(self) -> None:
        # {...} в тексте хука = override-блок libass → текст пропал бы. Должно экранироваться.
        _, dialogue = build_hook_event(
            HookOverlay(text="why {it} works", uppercase=False), clip_duration=10.0
        )
        assert "\\{it\\}" in dialogue
        assert ",,why \\{it\\} works" in dialogue

    def test_escapes_backslash(self) -> None:
        _, dialogue = build_hook_event(
            HookOverlay(text="a\\Nb", uppercase=False), clip_duration=10.0
        )
        assert "\\N" not in dialogue  # tag-инъекция нейтрализована
        assert "⧵" in dialogue

    def test_newlines_flattened(self) -> None:
        # перевод строки в тексте → пробел (libass WrapStyle 0 переносит сам)
        _, dialogue = build_hook_event(
            HookOverlay(text="одна\nдве", uppercase=False), clip_duration=10.0
        )
        assert "\n" not in dialogue.split(",,")[-1] if ",," in dialogue else True
        assert "одна две" in dialogue


# ─────────────────── build_hook_event анимация входа (A2) ───────────────────


class TestBuildHookEventAnimation:
    def _body(self, dialogue: str) -> str:
        # текст события = после ПОСЛЕДНЕГО ",," (поле Text; Effect пустое перед ним)
        return dialogue.rsplit(",,", 1)[1]

    def test_none_is_baseline_unchanged(self) -> None:
        # animation="none" (дефолт) → байт-в-байт как раньше (старый кэш хуков валиден)
        h_none = HookOverlay(text="привет", uppercase=False, animation="none")
        h_default = HookOverlay(text="привет", uppercase=False)
        _, d_none = build_hook_event(h_none, clip_duration=10.0)
        _, d_default = build_hook_event(h_default, clip_duration=10.0)
        assert d_none == d_default
        # никакого override-блока с \t у "none"
        assert "{" not in self._body(d_none)

    def test_pop_prepends_override_before_text(self) -> None:
        _, dialogue = build_hook_event(
            HookOverlay(text="привет", uppercase=False, animation="pop"), clip_duration=10.0
        )
        body = self._body(dialogue)
        # override-блок В НАЧАЛЕ текста, перед самим текстом
        assert body.startswith("{")
        tag = body[: body.index("}") + 1]
        assert "\\t(" in tag
        assert "\\fscy" in tag
        assert "\\fscx" not in tag  # ширину не трогаем (реврап-запрет)
        assert "\\fsp" not in tag
        # реальный текст идёт ПОСЛЕ override-блока
        assert body[body.index("}") + 1 :] == "привет"

    def test_fade_emits_alpha(self) -> None:
        _, dialogue = build_hook_event(
            HookOverlay(text="x", uppercase=False, animation="fade"), clip_duration=10.0
        )
        body = self._body(dialogue)
        tag = body[: body.index("}") + 1]
        assert "\\alpha" in tag
        assert "\\t(" in tag
        assert "\\fscx" not in tag

    def test_bounce_emits_fscy_and_no_fscx(self) -> None:
        _, dialogue = build_hook_event(
            HookOverlay(text="x", uppercase=False, animation="bounce"), clip_duration=10.0
        )
        body = self._body(dialogue)
        tag = body[: body.index("}") + 1]
        assert "\\fscy" in tag
        assert "\\t(" in tag
        assert "\\fscx" not in tag

    def test_animation_keeps_text_escaped(self) -> None:
        # текст с {} остаётся экранированным; override-блок — настоящие скобки впереди
        _, dialogue = build_hook_event(
            HookOverlay(text="why {it}", uppercase=False, animation="pop"), clip_duration=10.0
        )
        body = self._body(dialogue)
        assert body.startswith("{")  # override-блок
        # экранированный пользовательский текст уцелел
        assert "why \\{it\\}" in body


# ─────────────────────────── compile_ass с хуком ───────────────────────────


class TestCompileAssHook:
    def test_hook_emitted_as_top_event(self) -> None:
        words = [_w("a", 0.0, 0.4)]
        track = CaptionTrack(
            style=CaptionStyle(),
            replies=[CaptionReply(word_refs=[0])],
            hook=HookOverlay(text="Цепляющий хук"),
        )
        ass = compile_ass(track, words, _cmap())
        assert "Style: Hook," in ass
        assert "ЦЕПЛЯЮЩИЙ ХУК" in ass

    def test_no_hook_when_none(self) -> None:
        words = [_w("a", 0.0, 0.4)]
        track = CaptionTrack(style=CaptionStyle(), replies=[CaptionReply(word_refs=[0])])
        ass = compile_ass(track, words, _cmap())
        assert "Style: Hook," not in ass

    def test_no_hook_when_disabled(self) -> None:
        words = [_w("a", 0.0, 0.4)]
        track = CaptionTrack(
            style=CaptionStyle(),
            replies=[CaptionReply(word_refs=[0])],
            hook=HookOverlay(text="x", enabled=False),
        )
        ass = compile_ass(track, words, _cmap())
        assert "Style: Hook," not in ass

    def test_no_hook_when_empty_text(self) -> None:
        words = [_w("a", 0.0, 0.4)]
        track = CaptionTrack(
            style=CaptionStyle(),
            replies=[CaptionReply(word_refs=[0])],
            hook=HookOverlay(text="   "),
        )
        ass = compile_ass(track, words, _cmap())
        assert "Style: Hook," not in ass


# ─────────────────────────── seed в default_caption_track ───────────────────────────


class TestDefaultCaptionTrackHook:
    def test_seeds_hook_when_text_given(self) -> None:
        words = [_w("раз", 0.0, 0.4), _w("два", 0.4, 0.8)]
        intervals = [SourceInterval(source_start=0.0, source_end=0.8)]
        track = default_caption_track(words, intervals, hook="Бомбический момент")
        assert track.hook is not None
        assert track.hook.text == "Бомбический момент"
        assert track.hook.enabled is True

    def test_no_hook_when_text_none(self) -> None:
        words = [_w("раз", 0.0, 0.4)]
        intervals = [SourceInterval(source_start=0.0, source_end=0.4)]
        track = default_caption_track(words, intervals, hook=None)
        assert track.hook is None

    def test_default_highlight_is_active_word_pop(self) -> None:
        # #4: дефолт = активное слово вспыхивает + pop (вирусный вид), НЕ плоская заливка
        words = [_w("раз", 0.0, 0.4), _w("два", 0.4, 0.8)]
        intervals = [SourceInterval(source_start=0.0, source_end=0.8)]
        track = default_caption_track(words, intervals)
        assert track.highlight is not None
        assert track.highlight.animation == "pop"
        assert track.highlight.box is False  # per-word плашка в libass не рисуется → не обещаем
