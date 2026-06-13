"""Прайсинг/лимиты Quip — кредит-модель (PURE). 1 видео = до 60 мин; длиннее → больше
кредитов. Месячный лимит + не сгорающий PAYG-баланс. check_quota решает «пускать ли джоб»
и возвращает split списания (месячный/PAYG)."""

from app.billing import (
    PAYG_PRICE_USD,
    PLANS,
    QuotaDecision,
    check_quota,
    credits_per_video,
    current_month,
    resolve_plan,
)


class TestCreditsPerVideo:
    def test_short_and_zero_cost_one_credit(self) -> None:
        assert credits_per_video(0) == 1  # неизвестная/нулевая длина → минимум 1
        assert credits_per_video(1) == 1
        assert credits_per_video(30) == 1
        assert credits_per_video(60) == 1

    def test_over_an_hour_rounds_up(self) -> None:
        assert credits_per_video(61) == 2
        assert credits_per_video(90) == 2
        assert credits_per_video(120) == 2
        assert credits_per_video(130) == 3


class TestResolvePlan:
    def test_known_plans(self) -> None:
        assert resolve_plan("free").id == "free"
        assert resolve_plan("starter").id == "starter"
        assert resolve_plan("pro").id == "pro"

    def test_unknown_defaults_to_free(self) -> None:
        assert resolve_plan("bogus").id == "free"
        assert resolve_plan(None).id == "free"

    def test_free_has_watermark_starter_does_not(self) -> None:
        assert resolve_plan("free").watermark is True
        assert resolve_plan("starter").watermark is False


class TestCheckQuota:
    def test_free_allows_first_video(self) -> None:
        d = check_quota("free", used_credits=0, payg_credits=0, source_minutes=10.0)
        assert d.allowed is True
        assert d.reason is None
        assert d.credits == 1
        assert d.from_monthly == 1
        assert d.from_payg == 0

    def test_blocks_when_monthly_credits_exhausted(self) -> None:
        free = resolve_plan("free")
        d = check_quota(
            "free", used_credits=free.monthly_credits, payg_credits=0, source_minutes=5.0
        )
        assert d.allowed is False
        assert "кредит" in d.reason.lower()

    def test_free_rejects_long_source_with_upsell(self) -> None:
        # free обрабатывает только ≤30 мин — длинное видео отвергается (апселл), даже с PAYG
        d = check_quota("free", used_credits=0, payg_credits=50, source_minutes=45.0)
        assert d.allowed is False
        assert "starter" in d.reason.lower()

    def test_paid_plans_accept_long_source_charging_more_credits(self) -> None:
        # 90-мин видео на starter = 2 кредита, пропускается
        d = check_quota("starter", used_credits=0, payg_credits=0, source_minutes=90.0)
        assert d.allowed is True
        assert d.credits == 2
        assert d.from_monthly == 2

    def test_payg_covers_monthly_shortfall(self) -> None:
        # месячный исчерпан, но PAYG покрывает → пускаем, списываем с PAYG
        starter = resolve_plan("starter")
        d = check_quota(
            "starter",
            used_credits=starter.monthly_credits,
            payg_credits=3,
            source_minutes=10.0,
        )
        assert d.allowed is True
        assert d.from_monthly == 0
        assert d.from_payg == 1

    def test_split_deduction_monthly_then_payg(self) -> None:
        # нужно 2 кредита (90 мин), остался 1 месячный + 5 PAYG → 1 с месячного, 1 с PAYG
        starter = resolve_plan("starter")
        d = check_quota(
            "starter",
            used_credits=starter.monthly_credits - 1,
            payg_credits=5,
            source_minutes=90.0,
        )
        assert d.allowed is True
        assert d.credits == 2
        assert d.from_monthly == 1
        assert d.from_payg == 1

    def test_blocks_when_neither_monthly_nor_payg_enough(self) -> None:
        starter = resolve_plan("starter")
        d = check_quota(
            "starter",
            used_credits=starter.monthly_credits,
            payg_credits=0,
            source_minutes=10.0,
        )
        assert d.allowed is False
        assert f"{PAYG_PRICE_USD:.0f}" in d.reason  # подсказывает докупить PAYG

    def test_decision_is_quota_decision(self) -> None:
        assert isinstance(check_quota("free", 0, 0, 1.0), QuotaDecision)


class TestPlansShape:
    def test_three_tiers_ordered_by_price(self) -> None:
        assert set(PLANS) == {"free", "starter", "pro"}
        assert PLANS["free"].price_usd < PLANS["starter"].price_usd < PLANS["pro"].price_usd

    def test_credits_increase_with_tier(self) -> None:
        assert (
            PLANS["free"].monthly_credits
            < PLANS["starter"].monthly_credits
            < PLANS["pro"].monthly_credits
        )

    def test_final_pricing_numbers(self) -> None:
        # зафиксированный фаундером прайсинг (источник правды; фронт зеркалит)
        assert PLANS["free"].price_usd == 0.0
        assert PLANS["free"].monthly_credits == 2
        assert PLANS["free"].max_video_minutes == 30
        assert PLANS["starter"].price_usd == 10.0
        assert PLANS["starter"].monthly_credits == 10
        assert PLANS["pro"].price_usd == 25.0
        assert PLANS["pro"].monthly_credits == 30
        assert PLANS["pro"].priority is True
        assert PAYG_PRICE_USD == 2.0


class TestCurrentMonth:
    def test_format_yyyy_mm(self) -> None:
        import datetime

        assert current_month(datetime.date(2026, 6, 13)) == "2026-06"
        assert current_month(datetime.date(2026, 12, 1)) == "2026-12"
