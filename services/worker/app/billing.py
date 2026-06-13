"""Прайсинг и лимиты Quip — кредит-модель (источник правды планов/лимитов, PURE).

Единица тарификации = **1 «видео» = до 60 мин исходника**. Видео длиннее → стоит
больше кредитов: ``credits = max(1, ceil(минуты / 60))`` (90 мин = 2, 130 = 3). Лимит
плана = число видео-кредитов в месяц — прозрачно, БЕЗ «кредитов-казино» и surprise-paywall.

Баланс PAYG (pay-as-you-go) — отдельный НЕ сгорающий счётчик ($2 за 1 кредит, разово,
без подписки). Списываем сначала месячный лимит, затем PAYG. Поэтому решение квоты несёт
не только ``allowed``, но и split списания (``from_monthly`` / ``from_payg``), чтобы
вызывающий код знал, что записать в usage / profiles.

Лимиты держим в КОДЕ (не в БД) → один источник правды, нет дрейфа. В БД только состояние
пользователя: ``profiles.plan`` + ``profiles.payg_credits`` и месячный расход
(``usage_events``). Фронт (apps/web/lib/plans.ts) ОБЯЗАН зеркалить эти числа.

⚠️ Эконом-обоснование (для справки): себест ~$0.40/видео (60 мин) → маржа Starter ~60%,
Pro ~52%, PAYG ~80% в худшем случае. Лимиты можно поднять после переноса транскрипции на
WhisperX (не сейчас).
"""

from __future__ import annotations

import datetime
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class PlanLimits:
    """Лимиты тарифа. ``monthly_credits`` сбрасывается помесячно (usage_events по месяцу)."""

    id: str
    name: str
    price_usd: float  # в месяц (0 = free)
    monthly_credits: int  # видео-кредитов в месяц (1 кредит = 1 видео ≤60 мин)
    max_video_minutes: int | None  # макс. длина ОДНОГО исходника (None = без лимита)
    watermark: bool  # прожигать вотермарку (free)
    max_resolution: int  # 720 / 1080
    priority: bool = False  # приоритет очереди


# Источник правды тарифов. id стабильны (free/starter/pro) — на них ссылается profiles.plan.
PLANS: dict[str, PlanLimits] = {
    "free": PlanLimits(
        id="free",
        name="Free",
        price_usd=0.0,
        monthly_credits=2,
        max_video_minutes=30,  # free обрабатывает только короткие исходники
        watermark=True,
        max_resolution=720,
    ),  # fmt: skip
    "starter": PlanLimits(
        id="starter",
        name="Starter",
        price_usd=10.0,
        monthly_credits=10,
        max_video_minutes=None,
        watermark=False,
        max_resolution=1080,
    ),  # fmt: skip
    "pro": PlanLimits(
        id="pro",
        name="Pro",
        price_usd=25.0,
        monthly_credits=30,
        max_video_minutes=None,
        watermark=False,
        max_resolution=1080,
        priority=True,
    ),  # fmt: skip
}

_DEFAULT_PLAN = "free"

# Pay-as-you-go: разовая покупка кредитов без подписки. Не сгорают.
PAYG_PRICE_USD = 2.0
PAYG_CREDITS_PER_ORDER = 1  # один $2-заказ = 1 видео-кредит

# Минуты исходника на один кредит (= определение «1 видео»).
MINUTES_PER_CREDIT = 60

# TODO(фаундер): Founding Pass $5 (уже есть в Polar) — РЕШЕНИЕ ЧТО ДАЁТ за фаундером.
# Кандидаты: разовая пачка PAYG-кредитов / пожизненная скидка / ранний доступ. Пока не
# маппим в план — вебхук игнорирует (200 applied=false), число НЕ показываем на сайте.


def credits_per_video(source_minutes: float) -> int:
    """Сколько видео-кредитов стоит исходник длиной ``source_minutes``. PURE.

    ``max(1, ceil(minutes / 60))`` — даже 0-мин/неизвестная длина стоит 1 кредит
    (минимум за обработку); 60 мин = 1, 61 = 2, 130 = 3.
    """
    if source_minutes <= 0:
        return 1
    return max(1, math.ceil(source_minutes / MINUTES_PER_CREDIT))


def resolve_plan(plan_id: str | None) -> PlanLimits:
    """plan_id → PlanLimits. Неизвестный/None → free (безопасный дефолт, НЕ «всё разрешено»)."""
    return PLANS.get(plan_id or _DEFAULT_PLAN, PLANS[_DEFAULT_PLAN])


@dataclass(frozen=True)
class QuotaDecision:
    """Решение квоты. Несёт split списания, чтобы вызывающий записал расход корректно.

    ``allowed``     — пускать ли джоб.
    ``reason``      — человекочитаемая причина отказа (RU), None если allowed.
    ``credits``     — сколько кредитов стоит этот джоб (``credits_per_video``).
    ``from_monthly``— сколько списать с месячного лимита.
    ``from_payg``   — сколько списать с баланса PAYG (не сгорает).
    """

    allowed: bool
    reason: str | None = None
    credits: int = 0
    from_monthly: int = 0
    from_payg: int = 0


def check_quota(
    plan_id: str | None,
    used_credits: int,
    payg_credits: int,
    source_minutes: float,
) -> QuotaDecision:
    """Можно ли запустить джоб длиной ``source_minutes`` при текущем состоянии. PURE.

    Порядок: (1) free отвергает слишком длинный исходник (апселл); (2) считаем need
    кредитов; (3) тянем с месячного остатка, затем с PAYG. Честный отказ с понятной
    причиной (анти-surprise-paywall: лимит известен заранее).
    """
    plan = resolve_plan(plan_id)
    need = credits_per_video(source_minutes)

    # (1) Free не обрабатывает длинные исходники — даже за PAYG (это апселл-точка).
    if plan.max_video_minutes is not None and source_minutes > plan.max_video_minutes:
        return QuotaDecision(
            False,
            f"На плане «{plan.name}» можно обрабатывать видео до {plan.max_video_minutes} мин. "
            f"Это видео — {source_minutes:.0f} мин. Перейдите на Starter, чтобы нарезать длинные.",
            credits=need,
        )

    # (2) Списываем сначала месячный лимит, затем PAYG (не сгорает).
    monthly_remaining = max(0, plan.monthly_credits - used_credits)
    from_monthly = min(need, monthly_remaining)
    shortfall = need - from_monthly

    if shortfall <= payg_credits:
        return QuotaDecision(
            True, None, credits=need, from_monthly=from_monthly, from_payg=shortfall
        )

    # (3) Не хватает ни месячных, ни PAYG → честный отказ с путём решения.
    avail = monthly_remaining + payg_credits
    return QuotaDecision(
        False,
        f"Не хватает кредитов: нужно {need}, доступно {avail} "
        f"(месячный остаток {monthly_remaining} на плане «{plan.name}» + {payg_credits} PAYG). "
        f"Докупите кредиты (${PAYG_PRICE_USD:.0f}/видео) или обновите тариф.",
        credits=need,
    )


def current_month(today: datetime.date | None = None) -> str:
    """Текущий расчётный месяц `YYYY-MM` (ключ месячного окна usage). PURE при заданном today."""
    d = today or datetime.date.today()
    return f"{d.year:04d}-{d.month:02d}"
