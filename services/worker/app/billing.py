"""Прайсинг и лимиты Quip — модель «видео-минут» (источник правды планов/лимитов, PURE).

Единица для пользователя = **«видео» = 60 минут исходника**. Но под капотом всё считается
в МИНУТАХ (БД уже хранит ``usage_events.source_minutes``), а «видео» — это просто
``минуты / 60`` для показа. Поэтому остаток дробный и честный: план Starter = 10 видео =
600 мин; обработал 78 мин → осталось 522 мин = **8.7 видео**. Длинное видео тратит
пропорционально: 124 мин ≈ 2.07 видео (а не «округление вверх до 3»).

Лимит длины ОДНОГО видео:
  • технический потолок ``MAX_VIDEO_MINUTES`` (таймауты/CPU) — для всех планов;
  • план может иметь свой per-video cap (Free = 60 мин — апселл-точка на платные).
А сколько видео в месяц — это месячный пул минут (``monthly_videos × 60``) + не сгорающий
PAYG-баланс. Списываем сначала месячный пул, затем PAYG.

Лимиты держим в КОДЕ (не в БД) → один источник правды. Фронт (apps/web/lib/plans.ts +
UsageMeter) ОБЯЗАН зеркалить эти числа.

⚠️ Эконом-обоснование (2026-06: цены подняты к рынку, всё ещё 3-4× дешевле OpusClip):
себест ~$0.40/видео (60 мин) → $/кредит: Starter $1.50 (маржа ~73%), Pro $1.17 (~66%),
PAYG $3.00. Инвариант: $/кредит растёт при падении приверженности (Pro<Starter<PAYG).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

# Определение «1 видео». Меняешь тут — фронт (plans.ts/UsageMeter) зеркалит.
MINUTES_PER_VIDEO = 60

# Технический потолок длины ОДНОГО исходника для любого плана: транскрипция дорожает
# линейно, а reframe на CPU ~2× длительности + таймауты Modal-функций. Раньше тут стоял
# плоский лимит 90 мин в stage0 (не связанный с планами) — заменён этим единым потолком.
MAX_VIDEO_MINUTES = 180


@dataclass(frozen=True)
class PlanLimits:
    """Лимиты тарифа. ``monthly_videos`` сбрасывается помесячно (usage_events по месяцу)."""

    id: str
    name: str
    price_usd: float  # в месяц (0 = free)
    monthly_videos: int  # «видео» в месяц (1 видео = 60 мин); месячный пул = ×60 минут
    max_video_minutes: int | None  # cap длины ОДНОГО видео (None = только тех. потолок)
    watermark: bool  # прожигать вотермарку (free)
    max_resolution: int  # 720 / 1080
    priority: bool = False  # приоритет очереди


# Источник правды тарифов. id стабильны (free/starter/pro) — на них ссылается profiles.plan.
PLANS: dict[str, PlanLimits] = {
    "free": PlanLimits(
        id="free",
        name="Free",
        price_usd=0.0,
        monthly_videos=2,  # 2 видео = 120 мин/мес
        max_video_minutes=None,  # без per-video кэпа: длина видео ограничена только остатком
        # минут (квота) + техпотолок MAX_VIDEO_MINUTES. Раньше Free капился 60 мин/видео.
        watermark=True,
        max_resolution=720,
    ),  # fmt: skip
    "starter": PlanLimits(
        id="starter",
        name="Starter",
        price_usd=15.0,
        monthly_videos=10,  # 10 видео = 600 мин/мес
        max_video_minutes=None,  # длина одного видео — только тех. потолок
        watermark=False,
        max_resolution=1080,
    ),  # fmt: skip
    "pro": PlanLimits(
        id="pro",
        name="Pro",
        price_usd=35.0,
        monthly_videos=30,  # 30 видео = 1800 мин/мес
        max_video_minutes=None,
        watermark=False,
        max_resolution=1080,
        priority=True,
    ),  # fmt: skip
}

_DEFAULT_PLAN = "free"

# Pay-as-you-go: разовая покупка «видео» без подписки. Не сгорают. 1 заказ ($3) = 1 видео.
# ⚠️ Прайсинг-инвариант: $/кредит ДОЛЖЕН расти при падении приверженности — Pro ($1.17) <
# Starter ($1.50) < PAYG ($3.00). PAYG НИКОГДА ≤ Starter/кредит, иначе подписка теряет смысл.
# $3 (а не $2) также чинит фикс Polar (5%+$0.50: на $2 = 30%, на $3 = 22%).
PAYG_PRICE_USD = 3.0
PAYG_CREDITS_PER_ORDER = 1


def minutes_to_videos(minutes: float) -> float:
    """Минуты → «видео» для показа (дробно): 78 мин → 1.3, 522 → 8.7. PURE."""
    return round(max(0.0, minutes) / MINUTES_PER_VIDEO, 1)


def plan_monthly_minutes(plan: PlanLimits) -> int:
    """Месячный пул плана в минутах (= видео × 60). PURE."""
    return plan.monthly_videos * MINUTES_PER_VIDEO


def credits_per_video(source_minutes: float) -> int:
    """Сколько «видео-кредитов» списать за исходник (для usage_events.credits, целое).

    Округление ВВЕРХ до целого видео для строки расхода (минимум 1 за обработку). Гейт
    квоты считает дробно по минутам — это только для целочисленной колонки учёта. PURE.
    """
    import math

    if source_minutes <= 0:
        return 1
    return max(1, math.ceil(source_minutes / MINUTES_PER_VIDEO))


def resolve_plan(plan_id: str | None) -> PlanLimits:
    """plan_id → PlanLimits. Неизвестный/None → free (безопасный дефолт, НЕ «всё разрешено»)."""
    return PLANS.get(plan_id or _DEFAULT_PLAN, PLANS[_DEFAULT_PLAN])


@dataclass(frozen=True)
class QuotaDecision:
    """Решение квоты в МИНУТАХ. Несёт split списания (месячный/PAYG) для корректного учёта.

    ``allowed``          — пускать ли джоб.
    ``reason``           — человекочитаемая причина отказа (EN), None если allowed.
    ``minutes``          — длина этого исходника (минуты).
    ``from_monthly_min`` — сколько минут списать с месячного пула.
    ``from_payg_min``    — сколько минут покрыть из PAYG-баланса.
    """

    allowed: bool
    reason: str | None = None
    minutes: float = 0.0
    from_monthly_min: float = 0.0
    from_payg_min: float = 0.0


def check_quota(
    plan_id: str | None,
    used_minutes: float,
    payg_minutes: float,
    source_minutes: float,
) -> QuotaDecision:
    """Можно ли запустить джоб длиной ``source_minutes`` мин при текущем расходе. PURE.

    Порядок: (0) технический потолок длины; (1) per-video cap плана (Free-апселл);
    (2) месячный пул минут, затем PAYG. Честный отказ с понятной причиной (анти-surprise-
    paywall: лимит известен заранее). Всё в минутах → остаток дробный («8.7 видео»).
    """
    plan = resolve_plan(plan_id)

    # (0) Технический потолок длины одного видео (любой план).
    if source_minutes > MAX_VIDEO_MINUTES:
        return QuotaDecision(
            False,
            f"This video is {source_minutes:.0f} min long. The maximum we can process is "
            f"{MAX_VIDEO_MINUTES} min — trim it into shorter parts and try again.",
            minutes=source_minutes,
        )

    # (1) Per-video cap плана (Free обрабатывает только короткие исходники — апселл-точка).
    if plan.max_video_minutes is not None and source_minutes > plan.max_video_minutes:
        return QuotaDecision(
            False,
            f"On {plan.name} a single video can be up to {plan.max_video_minutes} min; "
            f"this one is {source_minutes:.0f} min. Upgrade to Starter to process longer videos.",
            minutes=source_minutes,
        )

    # (2) Месячный пул минут, затем PAYG (не сгорает).
    monthly_remaining = max(0.0, plan_monthly_minutes(plan) - used_minutes)
    from_monthly = min(source_minutes, monthly_remaining)
    shortfall = source_minutes - from_monthly

    if shortfall <= payg_minutes + 1e-6:
        return QuotaDecision(
            True,
            None,
            minutes=source_minutes,
            from_monthly_min=round(from_monthly, 2),
            from_payg_min=round(shortfall, 2),
        )

    # (3) Не хватает ни месячных минут, ни PAYG → честный отказ с путём решения.
    avail = monthly_remaining + payg_minutes
    return QuotaDecision(
        False,
        f"Not enough minutes left: this video needs {source_minutes:.0f} min but you have "
        f"{avail:.0f} min ({minutes_to_videos(avail):.1f} videos) on {plan.name}. "
        f"Top up (${PAYG_PRICE_USD:.0f}/video) or upgrade your plan.",
        minutes=source_minutes,
    )


def payg_credits_for_split(decision: QuotaDecision) -> int:
    """Сколько целых PAYG-кредитов списать за PAYG-покрытую часть джоба. PURE.

    PAYG-баланс хранится в целых «видео»-кредитах (1 кредит = ``MINUTES_PER_VIDEO`` мин).
    ``check_quota`` отдаёт покрытый из PAYG объём в МИНУТАХ (``from_payg_min``). Переводим
    обратно в целые кредиты округлением ВВЕРХ — покрытый объём не должен недосписываться
    (консервативно к нам, не к лишнему списанию: partial-видео = 1 кредит, как и при покупке).
    Отклонённое решение или нулевая PAYG-часть → 0 (списывать нечего).
    """
    import math

    if not decision.allowed or decision.from_payg_min <= 0:
        return 0
    return math.ceil(decision.from_payg_min / MINUTES_PER_VIDEO)


def current_month(today: datetime.date | None = None) -> str:
    """Текущий расчётный месяц `YYYY-MM` (ключ месячного окна usage). PURE при заданном today."""
    d = today or datetime.date.today()
    return f"{d.year:04d}-{d.month:02d}"
