"""Генератор предложений клиентов (чистая логика, без БД)."""

import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.game_data.economy import EASY, OFFER_LIFETIME_HOURS
from app.game_data.fleet import FLEET, Trim
from app.game_data.rarity import (
    DIFFICULTY_DEADLINE_PCT,
    DIFFICULTY_PAYMENT_PCT,
    MILEAGE_PCT,
    MODEL_RARITY,
    MODELS_BY_RARITY,
    Rarity,
    roll_rarity,
)
from app.game_data.order_planner import (
    PlannedFault,
    combine_complaint,
    deadline_hours,
    estimate_parts,
    fitting_scenarios,
    order_payment,
    pick_fault_count,
    plan_faults,
    tier_for_count,
)
from app.game_data.scenarios import SCENARIOS, Scenario

CUSTOMER_NAMES: tuple[str, ...] = (
    "Алексей Смирнов", "Дмитрий Кузнецов", "Игорь Попов", "Сергей Васильев",
    "Андрей Петров", "Михаил Соколов", "Николай Орлов", "Павел Морозов",
    "Елена Волкова", "Ольга Фёдорова", "Наталья Новикова", "Татьяна Лебедева",
    "Виктор Зайцев", "Артём Беляев", "Мария Ковалёва", "Роман Григорьев",
)
COLORS: tuple[str, ...] = (
    "белый", "чёрный", "серебристый", "серый", "синий", "красный", "зелёный", "бежевый",
)
_PLATE_LETTERS = "АВЕКМНОРСТУХ"
_VIN_CHARS = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"
_REGIONS = ("77", "50", "78", "63", "16", "52", "66", "74")
REFERENCE_YEAR = 2026


@dataclass(frozen=True, slots=True)
class OfferDraft:
    trim: Trim
    year: int
    mileage_km: int
    condition_pct: int
    color: str
    vin: str
    plate: str
    customer_name: str
    scenario: Scenario
    payment: int
    deadline_hours: int
    expires_at: datetime
    rarity: Rarity = Rarity.COMMON
    difficulty: int = 1  # сложность ремонта модели 1–5 (этап 5)
    tier: int = EASY  # сложность заказа: 1 🟢, 2 🟡, 3 🔴 (по числу неисправностей)
    plan: tuple[PlannedFault, ...] = ()  # скрытые неисправности (игрок их не видит)
    est_cost: int = 0  # ориентировочные расходы на детали
    complaint: str = ""
    symptoms: tuple[str, ...] = ()


_TRIMS_BY_MODEL: dict[str, tuple[Trim, ...]] = {}
for _t in FLEET:
    _TRIMS_BY_MODEL[_t.model_id] = (*_TRIMS_BY_MODEL.get(_t.model_id, ()), _t)
del _t


def round_price(value: float) -> int:
    """Округляет цену до 50 ₽."""
    return int(round(value / 50.0)) * 50


def compute_payment(
    scenario: Scenario, trim: Trim, mileage_km: int, difficulty: int = 1
) -> int:
    """Оплата зависит от сценария, комплектации, сложности модели и пробега."""
    price = scenario.base_payment * trim.price_factor_pct / 100
    price *= DIFFICULTY_PAYMENT_PCT.get(difficulty, 100) / 100
    if mileage_km >= 200_000:
        price *= 1.15
    elif mileage_km >= 120_000:
        price *= 1.07
    return max(50, round_price(price))


def _plate(rng: random.Random) -> str:
    letters = [rng.choice(_PLATE_LETTERS) for _ in range(3)]
    return f"{letters[0]}{rng.randint(100, 999)}{letters[1]}{letters[2]} {rng.choice(_REGIONS)}"


def _vin(rng: random.Random) -> str:
    return "".join(rng.choice(_VIN_CHARS) for _ in range(17))


def generate_offer(
    rng: random.Random, level: int, now: datetime | None = None, tier: int | None = None
) -> OfferDraft:
    """Случайное предложение, подходящее игроку по уровню.

    tier — желаемая сложность заказа (число неисправностей). Если выбранная машина
    поддерживает меньше неисправностей, чем нужно, берётся другая; если подходящей нет,
    заказ получает фактическую сложность (tier в результате всегда соответствует плану).
    """
    now = now or datetime.now(UTC)
    wanted = tier
    best: tuple[Trim, Rarity, str, list[Scenario], list[PlannedFault]] | None = None
    for attempt in range(40):
        # 1) редкость — независимый бросок; 2) случайная модель этой редкости;
        # 3) случайная комплектация модели. Повторы машин разрешены.
        rarity = roll_rarity(rng)
        model_id = rng.choice(MODELS_BY_RARITY[rarity])
        trim = rng.choice(_TRIMS_BY_MODEL[model_id])
        tags = trim.tags
        fitting = fitting_scenarios(trim.model, trim.transmission, level, tags)
        if not fitting:
            continue
        count = pick_fault_count(rng, wanted or EASY)
        plan = plan_faults(rng, fitting, tags, count)
        if not plan:
            continue
        candidate = (trim, rarity, model_id, fitting, plan)
        if best is None or len(plan) > len(best[4]):
            best = candidate
        if len(plan) >= count:
            best = candidate
            break
    if best is None:  # недостижимо: у лёгкого заказа всегда найдётся хотя бы одна жалоба
        raise RuntimeError("Не удалось подобрать автомобиль и неисправности для заказа")
    trim, rarity, model_id, fitting, plan = best
    tags = trim.tags
    by_code = {sc.code: sc for sc in SCENARIOS}
    used = [by_code[f.scenario_code] for f in plan]
    actual_tier = tier_for_count(len(plan))
    difficulty = MODEL_RARITY[model_id][1]
    year = rng.choice(trim.years)
    age = max(1, REFERENCE_YEAR - year)
    mileage = int(age * rng.randint(8_000, 20_000)) * MILEAGE_PCT[rarity] // 100
    mileage = min(450_000, mileage) // 100 * 100
    condition = max(30, min(95, 95 - age * 2 - mileage // 20_000 + rng.randint(-5, 5)))
    complaint, symptoms = combine_complaint(used)
    return OfferDraft(
        trim=trim,
        year=year,
        mileage_km=mileage,
        condition_pct=condition,
        color=rng.choice(COLORS),
        vin=_vin(rng),
        plate=_plate(rng),
        customer_name=rng.choice(CUSTOMER_NAMES),
        scenario=used[0],
        payment=order_payment(
            plan,
            tags,
            tier=actual_tier,
            price_factor_pct=trim.price_factor_pct,
            car_difficulty_pct=DIFFICULTY_PAYMENT_PCT.get(difficulty, 100),
            mileage_km=mileage,
        ),
        deadline_hours=deadline_hours(used, len(plan), DIFFICULTY_DEADLINE_PCT[difficulty]),
        expires_at=now + timedelta(hours=OFFER_LIFETIME_HOURS),
        rarity=rarity,
        difficulty=difficulty,
        tier=actual_tier,
        plan=tuple(plan),
        est_cost=estimate_parts(plan, tags),
        complaint=complaint,
        symptoms=symptoms,
    )
