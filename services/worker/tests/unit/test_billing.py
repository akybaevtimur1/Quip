"""Прайсинг/лимиты Quip — модель видео-минут (PURE). 1 видео = 60 мин; считаем в минутах,
показываем «видео» = минуты/60 (дробно). Месячный пул минут + не сгорающий PAYG. check_quota
решает «пускать ли джоб» и возвращает split списания (месячный/PAYG) в минутах.
"""

from app.billing import (
    MAX_VIDEO_MINUTES,
    MINUTES_PER_VIDEO,
    PAYG_PRICE_USD,
    PLANS,
    QuotaDecision,
    check_quota,
    credits_per_video,
    current_month,
    minutes_to_videos,
    plan_monthly_minutes,
    resolve_plan,
)


class TestVideoUnits:
    def test_minutes_to_videos_fractional(self) -> None:
        assert minutes_to_videos(0) == 0.0
        assert minutes_to_videos(60) == 1.0
        assert minutes_to_videos(78) == 1.3
        assert minutes_to_videos(522) == 8.7

    def test_plan_monthly_minutes(self) -> None:
        assert plan_monthly_minutes(resolve_plan("free")) == 120  # 2 видео
        assert plan_monthly_minutes(resolve_plan("starter")) == 600  # 10 видео
        assert plan_monthly_minutes(resolve_plan("pro")) == 1800  # 30 видео

    def test_minutes_per_video_is_60(self) -> None:
        assert MINUTES_PER_VIDEO == 60


class TestCreditsPerVideo:
    # credits_per_video — целочисленная колонка usage_events (округление вверх); гейт дробный.
    def test_short_and_zero_cost_one(self) -> None:
        assert credits_per_video(0) == 1
        assert credits_per_video(30) == 1
        assert credits_per_video(60) == 1

    def test_over_an_hour_rounds_up(self) -> None:
        assert credits_per_video(61) == 2
        assert credits_per_video(124) == 3


class TestResolvePlan:
    def test_known_and_unknown(self) -> None:
        assert resolve_plan("starter").id == "starter"
        assert resolve_plan("bogus").id == "free"
        assert resolve_plan(None).id == "free"

    def test_free_watermark_paid_not(self) -> None:
        assert resolve_plan("free").watermark is True
        assert resolve_plan("starter").watermark is False


class TestCheckQuota:
    def test_free_allows_short_video(self) -> None:
        d = check_quota("free", used_minutes=0.0, payg_minutes=0.0, source_minutes=10.0)
        assert d.allowed is True
        assert d.from_monthly_min == 10.0 and d.from_payg_min == 0.0

    def test_free_two_videos_equals_120_min(self) -> None:
        # free = 2 видео = 120 мин: 119 мин использовано → ещё 1 мин ок; ровно 120 → отказ.
        assert check_quota("free", 119.0, 0.0, 1.0).allowed is True
        assert check_quota("free", 120.0, 0.0, 5.0).allowed is False

    def test_free_has_no_per_video_cap_only_quota(self) -> None:
        # Free больше НЕ капит длину одного видео: 90-мин видео ОК, если влезает в месячный
        # пул (120 мин). Длина ограничена только остатком минут + техпотолком.
        assert check_quota("free", 0.0, 0.0, 90.0).allowed is True
        # видео длиннее остатка минут (120) → отказ по КВОТЕ, не по per-video кэпу
        over = check_quota("free", 0.0, 0.0, 130.0)
        assert over.allowed is False
        assert over.reason is not None and "minutes" in over.reason.lower()

    def test_hard_ceiling_blocks_very_long_for_any_plan(self) -> None:
        d = check_quota("pro", 0.0, 0.0, MAX_VIDEO_MINUTES + 1)
        assert d.allowed is False
        assert d.reason is not None and str(MAX_VIDEO_MINUTES) in d.reason

    def test_paid_accepts_long_video_proportionally(self) -> None:
        # 124-мин видео на starter (≤180 тех.потолок, ≤600 месячных) → ок, тратит 124 мин
        d = check_quota("starter", 0.0, 0.0, 124.0)
        assert d.allowed is True
        assert d.from_monthly_min == 124.0

    def test_payg_covers_monthly_shortfall(self) -> None:
        # месячные исчерпаны (600), PAYG 180 мин (3 видео) → 10-мин видео с PAYG
        d = check_quota("starter", used_minutes=600.0, payg_minutes=180.0, source_minutes=10.0)
        assert d.allowed is True
        assert d.from_monthly_min == 0.0 and d.from_payg_min == 10.0

    def test_split_monthly_then_payg(self) -> None:
        # осталось 5 месячных минут + 180 PAYG, видео 65 мин → 5 с месячного, 60 с PAYG
        d = check_quota("starter", used_minutes=595.0, payg_minutes=180.0, source_minutes=65.0)
        assert d.allowed is True
        assert d.from_monthly_min == 5.0 and d.from_payg_min == 60.0

    def test_blocks_when_neither_enough(self) -> None:
        d = check_quota("starter", used_minutes=600.0, payg_minutes=0.0, source_minutes=10.0)
        assert d.allowed is False
        assert d.reason is not None and f"{PAYG_PRICE_USD:.0f}" in d.reason

    def test_decision_type(self) -> None:
        assert isinstance(check_quota("free", 0.0, 0.0, 1.0), QuotaDecision)


class TestPaygCreditsForSplit:
    # BE-H: PAYG-минуты split'а → целое число PAYG-кредитов к списанию. Округление ВВЕРХ
    # (1 кредит = 60 мин): покрытый объём не должен недосписываться. 0 минут → 0 кредитов.
    def test_no_payg_portion_zero_credits(self) -> None:
        from app.billing import payg_credits_for_split

        d = check_quota("starter", used_minutes=0.0, payg_minutes=0.0, source_minutes=40.0)
        assert d.from_payg_min == 0.0
        assert payg_credits_for_split(d) == 0

    def test_partial_payg_rounds_up(self) -> None:
        from app.billing import payg_credits_for_split

        # 5 месячных + 60 PAYG → 60 мин из PAYG = ровно 1 кредит.
        d = check_quota("starter", used_minutes=595.0, payg_minutes=180.0, source_minutes=65.0)
        assert d.from_payg_min == 60.0
        assert payg_credits_for_split(d) == 1

    def test_payg_61_min_rounds_up_to_two(self) -> None:
        from app.billing import payg_credits_for_split

        # всё из PAYG, 61 мин → ceil(61/60) = 2 кредита.
        d = check_quota("starter", used_minutes=600.0, payg_minutes=180.0, source_minutes=61.0)
        assert d.from_monthly_min == 0.0 and d.from_payg_min == 61.0
        assert payg_credits_for_split(d) == 2

    def test_blocked_decision_charges_nothing(self) -> None:
        from app.billing import payg_credits_for_split

        d = check_quota("starter", used_minutes=600.0, payg_minutes=0.0, source_minutes=10.0)
        assert d.allowed is False
        assert payg_credits_for_split(d) == 0


class TestPlansShape:
    def test_three_tiers_ordered_by_price(self) -> None:
        assert set(PLANS) == {"free", "starter", "pro"}
        assert PLANS["free"].price_usd < PLANS["starter"].price_usd < PLANS["pro"].price_usd

    def test_monthly_videos(self) -> None:
        assert PLANS["free"].monthly_videos == 2
        assert PLANS["starter"].monthly_videos == 10
        assert PLANS["pro"].monthly_videos == 30


def test_current_month_format() -> None:
    import datetime

    assert current_month(datetime.date(2026, 6, 14)) == "2026-06"
