"""T6 — прайсинг/лимиты (PURE). Простые лимиты X видео/минут в месяц, без кредитов-казино.

Единица стоимости = минуты исходника (доминанта = транскрипция). check_quota решает,
можно ли запустить джоб данной длины при текущем месячном расходе и плане.
"""

from app.billing import PLANS, QuotaDecision, check_quota, current_month, resolve_plan


class TestResolvePlan:
    def test_known_plans(self) -> None:
        assert resolve_plan("free").id == "free"
        assert resolve_plan("starter").id == "starter"
        assert resolve_plan("pro").id == "pro"

    def test_unknown_defaults_to_free(self) -> None:
        # неизвестный/пустой план → free (безопасный дефолт, не «всё разрешено»)
        assert resolve_plan("bogus").id == "free"
        assert resolve_plan(None).id == "free"

    def test_free_has_watermark_starter_does_not(self) -> None:
        assert resolve_plan("free").watermark is True
        assert resolve_plan("starter").watermark is False


class TestCheckQuota:
    def test_free_allows_first_video(self) -> None:
        d = check_quota("free", used_videos=0, used_minutes=0.0, new_minutes=10.0)
        assert d.allowed is True
        assert d.reason is None

    def test_blocks_when_video_count_reached(self) -> None:
        free = resolve_plan("free")
        d = check_quota("free", used_videos=free.max_videos, used_minutes=0.0, new_minutes=5.0)
        assert d.allowed is False
        assert "видео" in d.reason.lower()

    def test_blocks_when_minutes_exceeded(self) -> None:
        free = resolve_plan("free")
        d = check_quota(
            "free", used_videos=0, used_minutes=free.max_source_minutes - 1.0, new_minutes=10.0
        )
        assert d.allowed is False
        assert "минут" in d.reason.lower()

    def test_allows_exactly_at_minute_limit(self) -> None:
        free = resolve_plan("free")
        d = check_quota(
            "free", used_videos=0, used_minutes=0.0, new_minutes=free.max_source_minutes
        )
        assert d.allowed is True

    def test_starter_allows_more_than_free(self) -> None:
        # объём, который free бы заблокировал, на starter проходит
        free = resolve_plan("free")
        over_free = float(free.max_source_minutes + 30)
        assert check_quota("free", 0, 0.0, over_free).allowed is False
        assert check_quota("starter", 0, 0.0, over_free).allowed is True

    def test_decision_is_quota_decision(self) -> None:
        assert isinstance(check_quota("free", 0, 0.0, 1.0), QuotaDecision)


class TestPlansShape:
    def test_three_tiers_ordered_by_price(self) -> None:
        assert set(PLANS) == {"free", "starter", "pro"}
        assert PLANS["free"].price_usd < PLANS["starter"].price_usd < PLANS["pro"].price_usd

    def test_limits_increase_with_tier(self) -> None:
        assert PLANS["free"].max_videos < PLANS["starter"].max_videos <= PLANS["pro"].max_videos
        assert (
            PLANS["free"].max_source_minutes
            < PLANS["starter"].max_source_minutes
            <= PLANS["pro"].max_source_minutes
        )


class TestCurrentMonth:
    def test_format_yyyy_mm(self) -> None:
        import datetime

        assert current_month(datetime.date(2026, 6, 13)) == "2026-06"
        assert current_month(datetime.date(2026, 12, 1)) == "2026-12"
