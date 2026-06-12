"""Прайсинг и лимиты ClipFlow (T6). ИСТОЧНИК ПРАВДЫ планов/лимитов — этот файл (PURE).

Анти-Vizard принципы (LAUNCH_BRIEF §2): простые лимиты «X видео / N минут в месяц»,
БЕЗ кредитов-казино и surprise-paywall. Единица стоимости = минуты ИСХОДНИКА (доминанта
затрат — транскрипция растёт с длиной источника). Честный free-preview с watermark.

Лимиты держим в КОДЕ (не в БД) → один источник правды, нет дрейфа. В БД хранится только
`plan` пользователя (profiles.plan). check_quota — чистое решение «пускать ли джоб».

⚠️ Числа лимитов/цен — ТЮНИНГ-КАНДИДАТЫ (фаундер крутит под юнит-экономику; см.
docs/SUPABASE_SETUP.md). Маржа замерена: ~$0.16/прогон 33-мин видео → лимиты с запасом.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass


@dataclass(frozen=True)
class PlanLimits:
    """Лимиты тарифа. Месячные (сбрасываются помесячно по profiles.plan + usage_events)."""

    id: str
    name: str
    price_usd: float  # в месяц (0 = free)
    max_videos: int  # видео в месяц
    max_source_minutes: int  # минут ИСХОДНИКА в месяц (доминанта стоимости)
    watermark: bool  # прожигать вотермарку (free)
    max_resolution: int  # 720 / 1080
    priority: bool = False  # приоритет очереди


# Источник правды тарифов. id стабильны (free/starter/pro) — на них ссылается profiles.plan.
PLANS: dict[str, PlanLimits] = {
    "free": PlanLimits(
        id="free",
        name="Free",
        price_usd=0.0,
        max_videos=2,
        max_source_minutes=20,
        watermark=True,
        max_resolution=720,
    ),  # fmt: skip
    "starter": PlanLimits(
        id="starter",
        name="Starter",
        price_usd=12.0,
        max_videos=20,
        max_source_minutes=200,
        watermark=False,
        max_resolution=1080,
    ),  # fmt: skip
    "pro": PlanLimits(
        id="pro",
        name="Pro",
        price_usd=29.0,
        max_videos=100,
        max_source_minutes=1000,
        watermark=False,
        max_resolution=1080,
        priority=True,
    ),  # fmt: skip
}

_DEFAULT_PLAN = "free"


def resolve_plan(plan_id: str | None) -> PlanLimits:
    """plan_id → PlanLimits. Неизвестный/None → free (безопасный дефолт, НЕ «всё разрешено")."""
    return PLANS.get(plan_id or _DEFAULT_PLAN, PLANS[_DEFAULT_PLAN])


@dataclass(frozen=True)
class QuotaDecision:
    """Решение квоты: пускать ли джоб. reason (RU) — человекочитаемая причина отказа."""

    allowed: bool
    reason: str | None = None


def check_quota(
    plan_id: str | None,
    used_videos: int,
    used_minutes: float,
    new_minutes: float,
) -> QuotaDecision:
    """Можно ли запустить джоб на new_minutes при текущем месячном расходе и плане. PURE.

    Сначала лимит по числу видео, затем по минутам исходника. Честный отказ с понятной
    причиной (анти-surprise-paywall: юзер заранее знает лимит). Граница включительна по
    минутам (ровно лимит — ОК).
    """
    plan = resolve_plan(plan_id)
    if used_videos >= plan.max_videos:
        return QuotaDecision(
            False,
            f"Лимит видео на месяц исчерпан ({plan.max_videos}). "
            f"План «{plan.name}» — обновите тариф, чтобы продолжить.",
        )
    if used_minutes + new_minutes > plan.max_source_minutes:
        remaining = max(0.0, plan.max_source_minutes - used_minutes)
        return QuotaDecision(
            False,
            f"Лимит минут исходника на месяц почти исчерпан "
            f"(осталось {remaining:.0f} из {plan.max_source_minutes} мин). "
            f"План «{plan.name}» — обновите тариф или возьмите видео короче.",
        )
    return QuotaDecision(True)


def current_month(today: datetime.date | None = None) -> str:
    """Текущий расчётный месяц `YYYY-MM` (ключ месячного окна usage). PURE при заданном today."""
    d = today or datetime.date.today()
    return f"{d.year:04d}-{d.month:02d}"
