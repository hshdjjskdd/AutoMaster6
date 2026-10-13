"""Симуляция экономики заказов (чистая логика): сколько зарабатывает мастер на заказах.

Не часть игры, а инструмент баланса: помогает проверить, что сложные заказы не
гарантированно выгоднее лёгких. Допущения игрока — параметры ниже, их можно менять.
"""

import random
import statistics
from dataclasses import dataclass

from app.game_data.economy import EASY, HARD, MEDIUM, TIERS
from app.game_data.offer_generator import OfferDraft, generate_offer
from app.game_data.order_planner import cause_cost
from app.game_data.fault_catalog import applicable_causes

# Допущения о игроке: шанс ошибиться в диагнозе одной неисправности (и купить не те детали).
ERROR_RATE: dict[int, float] = {EASY: 0.05, MEDIUM: 0.12, HARD: 0.22}
# Диагностика: среднее число проверок на одну неисправность и средняя плата за проверку.
CHECKS_PER_FAULT = 2.5
CHECK_FEE = 180
BASE_CHECKS = 3


@dataclass(frozen=True, slots=True)
class SimOrder:
    tier: int
    faults: int
    payment: int
    parts: int  # детали, нужные для ремонта (среднее качество)
    waste: int  # детали, купленные по ошибке диагностики
    diagnostics: int
    net: int


def simulate_order(rng: random.Random, draft: OfferDraft, level: int = 1) -> SimOrder:
    tags = draft.trim.tags
    parts = sum(cause_cost(f.code, tags) for f in draft.plan)
    pool = [c.code for c in applicable_causes(tags)]
    waste = 0
    for fault in draft.plan:
        if rng.random() < ERROR_RATE[draft.tier]:
            wrong = rng.choice([c for c in pool if c != fault.code])
            waste += cause_cost(wrong, tags)
    diagnostics = int((BASE_CHECKS + CHECKS_PER_FAULT * len(draft.plan)) * CHECK_FEE)
    return SimOrder(
        tier=draft.tier,
        faults=len(draft.plan),
        payment=draft.payment,
        parts=parts,
        waste=waste,
        diagnostics=diagnostics,
        net=draft.payment - parts - waste - diagnostics,
    )


def simulate(n_orders: int, seed: int = 1, tiers: tuple[int, ...] | None = None) -> list[SimOrder]:
    """n заказов подряд: сложность каждого — случайная по вероятностям доски (или из tiers)."""
    from app.game_data.economy import TIER_SPAWN_CHANCE

    rng = random.Random(seed)
    result: list[SimOrder] = []
    for _ in range(n_orders):
        tier = rng.choice(tiers) if tiers else rng.choices(
            TIERS, [TIER_SPAWN_CHANCE[t] for t in TIERS]
        )[0]
        result.append(simulate_order(rng, generate_offer(rng, 10, None, tier)))
    return result


def summarize(orders: list[SimOrder]) -> dict[str, float]:
    nets = [o.net for o in orders]
    return {
        "orders": len(orders),
        "revenue": sum(o.payment for o in orders),
        "expenses": sum(o.parts + o.waste + o.diagnostics for o in orders),
        "profit": sum(nets),
        "median_net": statistics.median(nets) if nets else 0,
        "loss_share": sum(1 for n in nets if n < 0) / len(nets) if nets else 0,
    }
