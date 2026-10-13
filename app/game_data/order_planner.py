"""Планирование неисправностей заказа и расчёт оплаты/сметы (чистая логика, без БД)."""

import json
import random
from dataclasses import dataclass

from app.game_data.economy import (
    DEADLINE_HOURS_PER_EXTRA_FAULT,
    ESTIMATE_QUALITY,
    INCOMPATIBLE_CAUSES,
    LABOR_RATE_PER_MINUTE,
    MULTI_FAULT_LABOR_PCT,
    PARTS_MARKUP_PCT,
    TIER_FAULT_RANGE,
    VISIT_FEE,
)
from app.game_data.fault_catalog import CAUSE_BY_CODE, SCENARIO_CAUSES, matches
from app.game_data.part_catalog import PART_TYPE_BY_CODE, car_skus, fit_value, price_of
from app.game_data.repair_catalog import ops_for_cause
from app.game_data.scenarios import SCENARIOS, Scenario


@dataclass(frozen=True, slots=True)
class PlannedFault:
    code: str  # причина (скрыта от игрока до диагностики)
    scenario_code: str  # жалоба клиента, через которую она проявляется


def parts_supported(cause_code: str, tags: dict[str, object]) -> bool:
    """Для каждой детали ремонта есть совместимый артикул у этой машины."""
    for op in ops_for_cause(cause_code):
        for need in op.needs:
            if not car_skus(PART_TYPE_BY_CODE[need.type_code], tags):
                return False
    return True


def cause_cost(cause_code: str, tags: dict[str, object], quality: int = ESTIMATE_QUALITY) -> int:
    """Стоимость деталей для устранения причины на этой машине."""
    total = 0
    for op in ops_for_cause(cause_code):
        for need in op.needs:
            ptype = PART_TYPE_BY_CODE[need.type_code]
            total += price_of(ptype, fit_value(ptype, tags), quality) * need.qty
    return total


def cause_minutes(cause_code: str) -> int:
    return sum(op.minutes for op in ops_for_cause(cause_code))


def compatible(code: str, chosen: set[str]) -> bool:
    return code not in chosen and all(frozenset({code, other}) not in INCOMPATIBLE_CAUSES for other in chosen)


def plan_faults(
    rng: random.Random,
    scenarios: list[Scenario],
    tags: dict[str, object],
    count: int,
) -> list[PlannedFault]:
    """До count разных причин: каждая приходит из своей жалобы, подходит машине и деталям.

    Возвращает меньше, если машина столько неисправностей не поддерживает.
    """
    pool = list(scenarios)
    rng.shuffle(pool)
    chosen: set[str] = set()
    plan: list[PlannedFault] = []
    for scenario in pool:
        if len(plan) >= count:
            break
        options = [
            (code, weight)
            for code, weight in SCENARIO_CAUSES.get(scenario.code, ())
            if matches(CAUSE_BY_CODE[code].requires, tags)
            and compatible(code, chosen)
            and parts_supported(code, tags)
        ]
        if not options:
            continue
        code = rng.choices([c for c, _ in options], [w for _, w in options])[0]
        chosen.add(code)
        plan.append(PlannedFault(code, scenario.code))
    return plan


def fitting_scenarios(model: str, transmission: object, level: int, tags: dict[str, object]) -> list[Scenario]:
    return [
        s for s in SCENARIOS if s.fits(model, transmission, level) and s.fits_tags(tags)  # type: ignore[arg-type]
    ]


def tier_for_count(count: int) -> int:
    """Какой сложности соответствует число неисправностей."""
    for tier, (low, high) in sorted(TIER_FAULT_RANGE.items(), reverse=True):
        if count >= low:
            return tier
    return 1


def pick_fault_count(rng: random.Random, tier: int) -> int:
    low, high = TIER_FAULT_RANGE[tier]
    return rng.randint(low, high)


def estimate_parts(plan: list[PlannedFault], tags: dict[str, object]) -> int:
    return sum(cause_cost(f.code, tags) for f in plan)


def labor_minutes(plan: list[PlannedFault]) -> int:
    return sum(cause_minutes(f.code) for f in plan)


def order_payment(
    plan: list[PlannedFault],
    tags: dict[str, object],
    *,
    tier: int,
    price_factor_pct: int,
    car_difficulty_pct: int,
    mileage_km: int,
) -> int:
    """Оплата клиента: работа с коэффициентами машины + возмещение деталей с наценкой."""
    n = len(plan)
    labor_pct = MULTI_FAULT_LABOR_PCT.get(n, min(MULTI_FAULT_LABOR_PCT.values()))
    work = VISIT_FEE + labor_minutes(plan) * LABOR_RATE_PER_MINUTE * labor_pct / 100
    work = work * price_factor_pct / 100 * car_difficulty_pct / 100
    if mileage_km >= 200_000:
        work *= 1.15
    elif mileage_km >= 120_000:
        work *= 1.07
    parts = estimate_parts(plan, tags) * PARTS_MARKUP_PCT[tier] / 100
    return max(50, int(round((work + parts) / 50.0)) * 50)


def deadline_hours(scenarios: list[Scenario], n_faults: int, difficulty_pct: int) -> int:
    base = max(s.deadline_hours for s in scenarios) + DEADLINE_HOURS_PER_EXTRA_FAULT * max(0, n_faults - 1)
    return max(1, base * difficulty_pct // 100)


def serialize_plan(plan: list[PlannedFault]) -> str:
    return json.dumps([[f.code, f.scenario_code] for f in plan], ensure_ascii=False)


def parse_plan(raw: str | None) -> list[PlannedFault]:
    if not raw:
        return []
    return [PlannedFault(code, scenario) for code, scenario in json.loads(raw)]


def combine_complaint(scenarios: list[Scenario]) -> tuple[str, tuple[str, ...]]:
    """Жалоба клиента и симптомы по нескольким сценариям (без повторов, только симптомы)."""
    complaint = " ".join(s.complaint.strip() for s in scenarios)
    seen: dict[str, None] = {}
    for s in scenarios:
        for line in s.symptoms:
            seen.setdefault(line, None)
    return complaint, tuple(seen)
