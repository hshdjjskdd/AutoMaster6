"""Каталог причин неисправностей и связь жалоб клиентов с возможными причинами.

Одна жалоба (сценарий) может быть вызвана несколькими разными причинами — так симптом
не называет поломку однозначно. Какая причина реальна, определяется при первой
проверке заказа и хранится в БД (скрыто от игрока).
"""

import random
from dataclasses import dataclass

from app.game_data.enums import FaultSeverity


Requires = tuple[tuple[str, tuple[object, ...]], ...]


def _req(**conditions: object) -> Requires:
    """Условия применимости по тегам автомобиля: ключ -> допустимые значения."""
    return tuple(
        (key, tuple(value) if isinstance(value, (tuple, list, set, frozenset)) else (value,))
        for key, value in conditions.items()
    )


def matches(requires: Requires, tags: "dict[str, object] | None") -> bool:
    """True, если автомобиль с данными тегами подходит под условия. Без тегов — всегда."""
    if tags is None:
        return True
    return all(tags.get(key) in allowed for key, allowed in requires)


@dataclass(frozen=True, slots=True)
class Cause:
    code: str  # до 16 символов: хранится в faults.code
    name: str
    system: str
    severity: FaultSeverity
    requires: Requires = ()  # на каких автомобилях неисправность вообще возможна


CAUSES: tuple[Cause, ...] = (
    Cause("BAT_WEAK", "Изношенная аккумуляторная батарея", "Электрика", FaultSeverity.MODERATE),
    Cause("ALT_FAIL", "Неисправный генератор / реле-регулятор", "Электрика", FaultSeverity.SERIOUS),
    Cause("FUSE_BLOWN", "Перегоревший предохранитель", "Электрика", FaultSeverity.MINOR),
    Cause("WIRE_CORR", "Окисленные клеммы / плохая масса", "Электрика", FaultSeverity.MINOR),
    Cause("STARTER_FAIL", "Износ стартера / втягивающего реле", "Электрика", FaultSeverity.MODERATE),
    Cause("PLUGS_WORN", "Изношенные свечи зажигания", "Зажигание", FaultSeverity.MINOR),
    Cause("COIL_FAIL", "Неисправная катушка зажигания", "Зажигание", FaultSeverity.MODERATE),
    Cause("FUEL_PUMP_WEAK", "Слабый топливный насос", "Топливо", FaultSeverity.SERIOUS),
    Cause("FUEL_FILTER_CLOG", "Забитый топливный фильтр", "Топливо", FaultSeverity.MINOR),
    Cause("INTAKE_LEAK", "Подсос воздуха во впуске", "Впуск", FaultSeverity.MODERATE),
    Cause("MAF_DIRTY", "Загрязнённый датчик массового расхода воздуха", "Впуск", FaultSeverity.MINOR),
    Cause("COOLANT_LEAK", "Утечка охлаждающей жидкости", "Охлаждение", FaultSeverity.SERIOUS),
    Cause("THERMOSTAT_STUCK", "Неисправный термостат", "Охлаждение", FaultSeverity.MODERATE),
    Cause("FAN_FAIL", "Неисправен вентилятор радиатора", "Охлаждение", FaultSeverity.MODERATE),
    Cause("BRAKE_PADS_WORN", "Изношенные тормозные колодки", "Тормоза", FaultSeverity.SERIOUS),
    Cause("BRAKE_FLUID_OLD", "Обводнённая тормозная жидкость", "Тормоза", FaultSeverity.MODERATE),
    Cause("SUSP_LINK", "Изношенная стойка стабилизатора", "Подвеска", FaultSeverity.MINOR),
    Cause("SUSP_STRUT", "Изношенный амортизатор", "Подвеска", FaultSeverity.MODERATE),
    Cause("OIL_LEAK", "Течь масла (прокладка / сальник)", "Двигатель", FaultSeverity.MODERATE),
    # --- этап 5: расширенный справочник (дописывается в конец: индексы старых не меняются) ---
    Cause("CLUTCH_WORN", "Изношенное сцепление", "Сцепление", FaultSeverity.SERIOUS, _req(trans="MT")),
    Cause("GEARBOX_FLUID", "Низкий уровень / старое масло в КПП", "Коробка передач", FaultSeverity.MODERATE),
    Cause("CV_JOINT", "Изношенный шарнир привода (ШРУС)", "Трансмиссия", FaultSeverity.MODERATE),
    Cause("WHEEL_BEARING", "Изношенный ступичный подшипник", "Подвеска", FaultSeverity.MODERATE),
    Cause("TIE_ROD", "Люфт рулевого наконечника", "Рулевое управление", FaultSeverity.MODERATE),
    Cause("PS_LEAK", "Течь гидроусилителя руля", "Рулевое управление", FaultSeverity.MODERATE, _req(steering="hyd")),
    Cause("TIMING_WORN", "Износ привода ГРМ (ремень / цепь)", "Двигатель", FaultSeverity.SERIOUS),
    Cause("HEAD_GASKET", "Пробита прокладка ГБЦ", "Двигатель", FaultSeverity.CRITICAL),
    Cause("TURBO_WORN", "Износ турбокомпрессора", "Двигатель", FaultSeverity.SERIOUS, _req(turbo=True)),
    Cause("AC_LOW_GAS", "Утечка хладагента кондиционера", "Кондиционер", FaultSeverity.MINOR, _req(ac=True)),
    Cause("AC_COMP", "Неисправен компрессор кондиционера", "Кондиционер", FaultSeverity.MODERATE, _req(ac=True)),
    Cause("O2_SENSOR", "Неисправен датчик кислорода", "Датчики", FaultSeverity.MINOR, _req(injection=("mpi", "gdi"))),
    Cause("ECT_SENSOR", "Неисправен датчик температуры ОЖ", "Датчики", FaultSeverity.MINOR, _req(ecu=True)),
    Cause("THROTTLE_DIRTY", "Загрязнена дроссельная заслонка", "Впуск", FaultSeverity.MINOR, _req(injection=("mpi", "gdi"))),
    Cause("INJECTORS", "Засорены форсунки", "Топливо", FaultSeverity.MODERATE, _req(injection=("mpi", "gdi", "diesel"))),
    Cause("CARB_DIRTY", "Загрязнён карбюратор (жиклёры)", "Топливо", FaultSeverity.MODERATE, _req(injection="carb")),
    Cause("GLOW_FAIL", "Неисправны свечи накала", "Зажигание", FaultSeverity.MODERATE, _req(fuel="diesel")),
)

# Исправления применимости старых причин: без этого на карбюраторных и дизельных
# машинах возникали бы невозможные поломки (катушка на трамблёрной системе и т. п.).
_LEGACY_REQUIRES: dict[str, Requires] = {
    "COIL_FAIL": _req(ignition=("coil", "module")),
    "MAF_DIRTY": _req(injection=("mpi", "gdi", "diesel")),
    "PLUGS_WORN": _req(fuel=("petrol", "lpg", "hybrid")),
}
CAUSES = tuple(
    Cause(c.code, c.name, c.system, c.severity, _LEGACY_REQUIRES.get(c.code, c.requires))
    for c in CAUSES
)

CAUSE_BY_CODE: dict[str, Cause] = {c.code: c for c in CAUSES}

if len(CAUSE_BY_CODE) != len(CAUSES) or any(len(c.code) > 16 for c in CAUSES):
    raise RuntimeError("Коды причин должны быть уникальными и не длиннее 16 символов")

# Жалоба -> возможные причины с весами. Нужно, чтобы симптом не определял поломку.
SCENARIO_CAUSES: dict[str, tuple[tuple[str, int], ...]] = {
    "brake_squeal": (("BRAKE_PADS_WORN", 5), ("BRAKE_FLUID_OLD", 2), ("SUSP_LINK", 1)),
    "knock_front": (("SUSP_LINK", 4), ("SUSP_STRUT", 3), ("BRAKE_PADS_WORN", 1)),
    "no_start_cold": (
        ("BAT_WEAK", 4), ("STARTER_FAIL", 3), ("WIRE_CORR", 2), ("ALT_FAIL", 1), ("FUSE_BLOWN", 1),
    ),
    "idle_unstable": (
        ("INTAKE_LEAK", 4), ("MAF_DIRTY", 3), ("PLUGS_WORN", 2), ("COIL_FAIL", 1),
    ),
    "oil_leak": (("OIL_LEAK", 6), ("COOLANT_LEAK", 1)),
    "overheat": (
        ("THERMOSTAT_STUCK", 3), ("COOLANT_LEAK", 3), ("FAN_FAIL", 3), ("FUSE_BLOWN", 1),
    ),
    "lights_dead": (("FUSE_BLOWN", 3), ("WIRE_CORR", 3), ("ALT_FAIL", 2), ("BAT_WEAK", 1)),
    "vaz_carburetor_like": (
        ("PLUGS_WORN", 3), ("COIL_FAIL", 3), ("FUEL_FILTER_CLOG", 2), ("INTAKE_LEAK", 1),
    ),
    "vaz_heater": (("THERMOSTAT_STUCK", 4), ("COOLANT_LEAK", 3)),
    "corolla_vibration": (("SUSP_STRUT", 3), ("SUSP_LINK", 3), ("PLUGS_WORN", 1)),
    "polo_dsg_like": (
        ("COIL_FAIL", 3), ("MAF_DIRTY", 3), ("INTAKE_LEAK", 2), ("PLUGS_WORN", 1),
    ),
    "solaris_suspension": (("SUSP_LINK", 4), ("SUSP_STRUT", 3)),
    "misfire_cel": (
        ("PLUGS_WORN", 4), ("COIL_FAIL", 3), ("INTAKE_LEAK", 1), ("FUSE_BLOWN", 1),
    ),
    "battery_drain": (("ALT_FAIL", 3), ("BAT_WEAK", 3), ("WIRE_CORR", 2), ("FUSE_BLOWN", 1)),
    "weak_acceleration": (
        ("FUEL_FILTER_CLOG", 3), ("FUEL_PUMP_WEAK", 3), ("PLUGS_WORN", 2),
        ("MAF_DIRTY", 2), ("INTAKE_LEAK", 1),
    ),
    "pulls_braking": (
        ("BRAKE_PADS_WORN", 3), ("SUSP_STRUT", 2), ("BRAKE_FLUID_OLD", 1), ("SUSP_LINK", 1),
    ),
}

SCENARIO_CAUSES.update(
    {
        "clutch_slip": (("CLUTCH_WORN", 6), ("GEARBOX_FLUID", 1)),
        "gearbox_jerk": (("GEARBOX_FLUID", 5), ("ECT_SENSOR", 1), ("WIRE_CORR", 1)),
        "cv_crunch": (("CV_JOINT", 5), ("WHEEL_BEARING", 3), ("SUSP_LINK", 1)),
        "steering_play": (("TIE_ROD", 4), ("WHEEL_BEARING", 2), ("SUSP_LINK", 2)),
        "steering_hard": (("PS_LEAK", 5), ("TIE_ROD", 1)),
        "wheel_hum": (("WHEEL_BEARING", 5), ("CV_JOINT", 1), ("BRAKE_PADS_WORN", 1)),
        "timing_noise": (("TIMING_WORN", 5), ("PLUGS_WORN", 1), ("OIL_LEAK", 1)),
        "white_smoke": (("HEAD_GASKET", 5), ("COOLANT_LEAK", 3), ("THERMOSTAT_STUCK", 1)),
        "ac_warm": (("AC_LOW_GAS", 4), ("AC_COMP", 3), ("FUSE_BLOWN", 1), ("FAN_FAIL", 1)),
        "cel_sensor": (("O2_SENSOR", 3), ("ECT_SENSOR", 2), ("MAF_DIRTY", 2), ("INTAKE_LEAK", 1)),
        "carb_rich": (("CARB_DIRTY", 5), ("PLUGS_WORN", 2), ("FUEL_FILTER_CLOG", 2)),
        "fuel_economy": (("INJECTORS", 4), ("FUEL_PUMP_WEAK", 2), ("FUEL_FILTER_CLOG", 2)),
        "idle_dirty": (("THROTTLE_DIRTY", 4), ("MAF_DIRTY", 2), ("INTAKE_LEAK", 1)),
        "turbo_loss": (("TURBO_WORN", 4), ("INTAKE_LEAK", 3), ("MAF_DIRTY", 1)),
        "glow_cold": (("GLOW_FAIL", 4), ("BAT_WEAK", 2), ("FUEL_FILTER_CLOG", 2), ("STARTER_FAIL", 1)),
    }
)

for _code, _pool in SCENARIO_CAUSES.items():
    for _cause, _weight in _pool:
        if _cause not in CAUSE_BY_CODE or _weight <= 0:
            raise RuntimeError(f"Некорректная причина в сценарии {_code}: {_cause}")

# Какие цепи может затронуть перегоревший предохранитель в данном сценарии.
ALL_CIRCUITS: tuple[str, ...] = ("ignition", "fuel_pump", "fan", "lights")
FUSE_CIRCUITS_BY_SCENARIO: dict[str, tuple[str, ...]] = {
    "overheat": ("fan",),
    "lights_dead": ("lights",),
    "no_start_cold": ("ignition", "fuel_pump"),
    "misfire_cel": ("ignition",),
    "battery_drain": ("lights",),
}

# Следствия: износ одного узла часто портит другой.
_CONSEQUENCES: dict[str, tuple[str, float]] = {"ALT_FAIL": ("BAT_WEAK", 0.5)}
SECONDARY_CHANCE = 0.25
MAX_FAULTS = 2


@dataclass(frozen=True, slots=True)
class TruthFault:
    code: str
    detail: str = ""


def _pick_detail(
    code: str, scenario_code: str | None, rng: random.Random, tags: "dict[str, object] | None" = None
) -> str:
    cylinders = min(int((tags or {}).get("cylinders", 4)), 6)  # type: ignore[call-overload]
    if code == "FUSE_BLOWN":
        return rng.choice(FUSE_CIRCUITS_BY_SCENARIO.get(scenario_code or "", ALL_CIRCUITS))
    if code == "COIL_FAIL":
        return f"cyl:{rng.randint(1, cylinders)}"
    if code == "THERMOSTAT_STUCK":
        if scenario_code == "vaz_heater":
            return "open"
        if scenario_code == "overheat":
            return "closed"
        return rng.choice(("open", "closed"))
    if code == "INTAKE_LEAK":
        return rng.choice(("hose", "gasket"))
    if code == "ALT_FAIL":
        return rng.choice(("no_charge", "overcharge", "diode"))
    if code in ("SUSP_STRUT", "SUSP_LINK", "WHEEL_BEARING", "CV_JOINT", "TIE_ROD"):
        return rng.choice(("left", "right"))
    if code == "BRAKE_PADS_WORN":
        return rng.choice(("left", "right", "both"))
    if code == "INJECTORS":
        return f"cyl:{rng.randint(1, cylinders)}"
    if code == "AC_COMP":
        return rng.choice(("clutch", "worn"))
    return ""


def applicable_causes(tags: "dict[str, object] | None") -> tuple[Cause, ...]:
    """Причины, возможные на автомобиле с данными тегами (без тегов — все)."""
    return tuple(c for c in CAUSES if matches(c.requires, tags))


def generate_truth(
    seed: str, scenario_code: str | None, tags: "dict[str, object] | None" = None
) -> list[TruthFault]:
    """Реальные неисправности автомобиля (1–2 штуки). Результат зависит только от seed.

    Если переданы теги автомобиля, невозможные для него причины отбрасываются.
    """
    rng = random.Random(seed)
    pool = SCENARIO_CAUSES.get(scenario_code or "")
    if pool is None:
        pool = tuple((c.code, 1) for c in CAUSES)
    pool = tuple((code, w) for code, w in pool if matches(CAUSE_BY_CODE[code].requires, tags))
    if not pool:  # сценарий не подходит машине: берём любые применимые причины
        pool = tuple((c.code, 1) for c in applicable_causes(tags))
    codes = [code for code, _ in pool]
    weights = [weight for _, weight in pool]

    chosen = [rng.choices(codes, weights)[0]]
    consequence = _CONSEQUENCES.get(chosen[0])
    if consequence and rng.random() < consequence[1] and matches(
        CAUSE_BY_CODE[consequence[0]].requires, tags
    ):
        chosen.append(consequence[0])
    elif rng.random() < SECONDARY_CHANCE:
        rest = [c for c in codes if c not in chosen]
        if rest:
            rest_weights = [w for c, w in pool if c not in chosen]
            chosen.append(rng.choices(rest, rest_weights)[0])
    return [
        TruthFault(code, _pick_detail(code, scenario_code, rng, tags)) for code in chosen[:MAX_FAULTS]
    ]


def truth_from_plan(
    seed: str, plan: "list[tuple[str, str]]", tags: "dict[str, object] | None" = None
) -> list[TruthFault]:
    """Реальные неисправности по плану заказа (этап 6): причины заданы при создании заказа.

    plan — пары (код причины, код сценария). Детали (цилиндр, цепь и т. п.) выбираются от
    seed, поэтому результат воспроизводим. Причины, невозможные для машины, отбрасываются.
    """
    rng = random.Random(seed)
    result: list[TruthFault] = []
    for code, scenario_code in plan:
        if code in CAUSE_BY_CODE and matches(CAUSE_BY_CODE[code].requires, tags):
            if all(f.code != code for f in result):
                result.append(TruthFault(code, _pick_detail(code, scenario_code, rng, tags)))
    return result
