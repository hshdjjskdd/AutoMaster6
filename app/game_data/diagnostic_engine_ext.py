"""Измерения новых проверок этапа 5: компрессия, ГРМ, трансмиссия, рулевое и ступицы,
датчики, кондиционер, наддув, анализ выхлопа и доп. строки осмотра/диагностики.

Правила те же, что в diagnostic_engine: каждая проверка видит только свою часть картины,
значения разных причин пересекаются, шум зависит от rng.
"""

import random

from app.game_data.diagnostic_engine import (
    BAD,
    INFO,
    OK,
    WARN,
    Reading,
    Truth,
    VehicleContext,
    _num,
    _side,
    _text,
    _u,
)
from app.game_data.engines import ENGINES

MAX_CYL_SHOWN = 6


def _cylinders(ctx: VehicleContext) -> int:
    return min(int(ctx.tags.get("cylinders", 4)), MAX_CYL_SHOWN)  # type: ignore[call-overload]


def _idx(detail: str) -> int:
    return int(detail.split(":")[1]) if detail.startswith("cyl:") else 0


# --- двигатель --------------------------------------------------------------


def check_compression(ctx: VehicleContext, truth: Truth, rng: random.Random) -> list[Reading]:
    spec = ENGINES.get(ctx.engine_code)
    nominal = spec.compression_bar if spec else 12.0
    wear = 0.97 - min(ctx.mileage_km, 300_000) / 300_000 * 0.08
    gasket = "HEAD_GASKET" in truth
    timing = "TIMING_WORN" in truth
    n = _cylinders(ctx)
    bad_a = rng.randint(1, max(1, n - 1)) if gasket else 0
    readings: list[Reading] = []
    for cyl in range(1, n + 1):
        value = nominal * wear * _u(rng, 0.95, 1.03)
        if gasket and cyl in (bad_a, bad_a + 1):
            value = nominal * _u(rng, 0.45, 0.65)
        elif timing:
            value *= _u(rng, 0.86, 0.94)
        readings.append(
            _num(f"Цилиндр {cyl}: компрессия", value, "бар", nominal * 0.82, nominal * 1.1,
                 decimals=1, warn=nominal * 0.06)
        )
    if gasket:
        readings.append(_text("Пузырьки воздуха в расширительном бачке", "есть, на работающем моторе", BAD,
                              "Газы из камеры сгорания попадают в систему охлаждения."))
        readings.append(_text("Масло на щупе", "светлая эмульсия" if rng.random() < 0.5 else "без изменений",
                              WARN))
    else:
        readings.append(_text("Пузырьки воздуха в расширительном бачке", "нет", OK))
        readings.append(_text("Масло на щупе", "в норме", OK))
    return readings


def check_timing(ctx: VehicleContext, truth: Truth, rng: random.Random) -> list[Reading]:
    chain = ctx.tags.get("timing") == "chain"
    worn = "TIMING_WORN" in truth
    readings: list[Reading] = []
    if chain:
        slack = _u(rng, 7.5, 12.5) if worn else _u(rng, 1.0, 4.5)
        readings.append(_num("Вытяжка цепи (по люфту натяжителя)", slack, "мм", None, 5.0, warn=1.5))
        readings.append(_text("Шум цепи на холодную", "дребезг до прогрева" if worn else "тихо",
                              WARN if worn else OK))
    else:
        wear = _u(rng, 70, 95) if worn else _u(rng, 5, 45)
        readings.append(_num("Износ ремня ГРМ (трещины, расслоение)", wear, "%", None, 60, decimals=0, warn=12))
        readings.append(_num("Усилие натяжения ремня", _u(rng, 20, 45) if worn else _u(rng, 60, 85),
                             "усл. ед.", 55, 90, decimals=0, warn=10))
    offset = rng.choice((1, 2)) if worn and rng.random() < 0.5 else 0
    readings.append(
        _text("Совпадение меток ГРМ", f"смещение на {offset} зуб." if offset else "метки совпадают",
              BAD if offset else OK)
    )
    readings.append(_num("Пробег с последней замены (оценка)", ctx.mileage_km * _u(rng, 0.6, 1.0) if worn
                         else ctx.mileage_km * _u(rng, 0.05, 0.4), "км", None, 120_000, decimals=0, warn=20_000))
    return readings


# --- трансмиссия ------------------------------------------------------------


def check_drivetrain(ctx: VehicleContext, truth: Truth, rng: random.Random) -> list[Reading]:
    readings: list[Reading] = []
    manual = ctx.tags.get("trans", "MT") == "MT"
    if manual:
        clutch = "CLUTCH_WORN" in truth
        readings.append(_num("Свободный ход педали сцепления", _u(rng, 1, 6) if clutch else _u(rng, 10, 25),
                             "мм", 8, 30, decimals=0, warn=4))
        readings.append(_num("Проба на пробуксовку (3-я, полный газ)", _u(rng, 8, 22) if clutch else _u(rng, 0, 2.5),
                             "%", None, 3, warn=3))
        readings.append(_text("Запах при пробе", "жжёная фрикционная накладка" if clutch else "обычный",
                              WARN if clutch else OK))
    else:
        readings.append(_num("Задержка включения передачи (D/R)", _u(rng, 0.6, 1.4) if "GEARBOX_FLUID" in truth
                             else _u(rng, 0.2, 0.5), "с", None, 0.6, decimals=1, warn=0.3))
        readings.append(_text("Рывки при переключении",
                              "заметные" if "GEARBOX_FLUID" in truth and rng.random() < 0.8 else "нет",
                              WARN if "GEARBOX_FLUID" in truth else OK))
    fluid = "GEARBOX_FLUID" in truth
    readings.append(_num("Уровень масла в КПП (от метки MAX)", -_u(rng, 8, 20) if fluid else -_u(rng, 0, 4),
                         "мм", -5, 0, decimals=0, warn=5))
    readings.append(_text("Состояние масла", "тёмное, пахнет гарью" if fluid else "светлое, прозрачное",
                          WARN if fluid else OK))
    return readings


def check_chassis(ctx: VehicleContext, truth: Truth, rng: random.Random) -> list[Reading]:
    tie, bearing, cv = truth.get("TIE_ROD", ""), truth.get("WHEEL_BEARING", ""), truth.get("CV_JOINT", "")

    def play(code_detail: str, side: str, bad_lo: float, bad_hi: float, ok_hi: float) -> float:
        return _u(rng, bad_lo, bad_hi) if code_detail and _side(code_detail, side) else _u(rng, 0.0, ok_hi)

    readings = [
        _num("Люфт рулевого наконечника, левый", play(tie, "left", 1.6, 3.4, 0.4), "мм", None, 1.0, warn=0.5),
        _num("Люфт рулевого наконечника, правый", play(tie, "right", 1.6, 3.4, 0.4), "мм", None, 1.0, warn=0.5),
        _num("Люфт ступичного подшипника, левый", play(bearing, "left", 0.5, 1.4, 0.08), "мм", None, 0.15,
             decimals=2, warn=0.1),
        _num("Люфт ступичного подшипника, правый", play(bearing, "right", 0.5, 1.4, 0.08), "мм", None, 0.15,
             decimals=2, warn=0.1),
    ]
    boot_bad = bool(cv) and rng.random() < 0.6
    readings.append(_text("Пыльники приводов", "порван пыльник, смазка выброшена" if boot_bad else "целые",
                          WARN if boot_bad else OK))
    readings.append(
        _num("Люфт шарнира привода, левый", play(cv, "left", 1.2, 3.0, 0.3), "°", None, 0.8, warn=0.5)
    )
    readings.append(
        _num("Люфт шарнира привода, правый", play(cv, "right", 1.2, 3.0, 0.3), "°", None, 0.8, warn=0.5)
    )
    if ctx.tags.get("steering", "hyd") == "hyd":
        leak = "PS_LEAK" in truth
        readings.append(_text("Уровень жидкости ГУР", "ниже MIN" if leak else "в норме", BAD if leak else OK))
        readings.append(_text("Подтёки на шлангах и рейке", "мокрый шланг, подтёки" if leak else "сухо",
                              WARN if leak else OK))
    return readings


# --- датчики ------------------------------------------------------------------


def check_sensors(ctx: VehicleContext, truth: Truth, rng: random.Random) -> list[Reading]:
    o2, ect, thr = "O2_SENSOR" in truth, "ECT_SENSOR" in truth, "THROTTLE_DIRTY" in truth
    inj = truth.get("INJECTORS", "")
    readings = [
        _num("Размах напряжения лямбда-зонда", _u(rng, 0.08, 0.35) if o2 else _u(rng, 0.65, 0.9), "В",
             0.6, 0.95, decimals=2, warn=0.1),
        _num("Время переключения зонда", _u(rng, 220, 420) if o2 else _u(rng, 60, 130), "мс", None, 150,
             decimals=0, warn=50),
    ]
    real = _u(rng, 88, 95)
    shown = real + _u(rng, 12, 25) * rng.choice((-1, 1)) if ect else real + _u(rng, -2, 2)
    readings.append(_num("Температура ОЖ: показание датчика", shown, "°C", 85, 100, decimals=0, warn=5))
    readings.append(_num("Температура ОЖ: контроль пирометром", real, "°C", 85, 100, decimals=0, warn=5))
    readings.append(_num("Открытие дросселя на холостом ходу", _u(rng, 9, 14) if thr else _u(rng, 2, 5.5), "%",
                         None, 6, decimals=1, warn=2.5))
    n = _cylinders(ctx)
    bad = _idx(inj)
    for cyl in range(1, n + 1):
        trim = _u(rng, 8, 16) if cyl == bad else _u(rng, -3, 3)
        readings.append(_num(f"Цилиндр {cyl}: коррекция по форсунке", trim, "%", -7, 7, decimals=0, warn=3))
    return readings


# --- кондиционер, наддув, выхлоп ----------------------------------------------


def check_aircond(ctx: VehicleContext, truth: Truth, rng: random.Random) -> list[Reading]:
    gas, comp = "AC_LOW_GAS" in truth, truth.get("AC_COMP")
    fan = "FAN_FAIL" in truth or truth.get("FUSE_BLOWN") == "fan"
    if gas:
        low, high, outlet, clutch = _u(rng, 0.4, 1.2), _u(rng, 6, 10), _u(rng, 14, 20), "включается"
    elif comp == "clutch":
        low, high, outlet, clutch = _u(rng, 3.5, 5), _u(rng, 4, 6), _u(rng, 22, 30), "не включается"
    elif comp:
        low, high, outlet, clutch = _u(rng, 3.2, 4.8), _u(rng, 7, 10), _u(rng, 20, 28), "включается, проскальзывает"
    elif fan:
        low, high, outlet, clutch = _u(rng, 2.2, 3.0), _u(rng, 22, 28), _u(rng, 12, 18), "отключается по давлению"
    else:
        low, high, outlet, clutch = _u(rng, 1.8, 2.5), _u(rng, 14, 18), _u(rng, 3, 8), "включается"
    bad_clutch = clutch != "включается"
    return [
        _num("Давление на стороне низкого давления", low, "бар", 1.6, 2.7, decimals=1, warn=0.5),
        _num("Давление на стороне высокого давления", high, "бар", 12, 19, decimals=1, warn=2.5),
        _num("Температура воздуха на выходе дефлектора", outlet, "°C", None, 10, decimals=0, warn=4),
        _text("Муфта компрессора", clutch, WARN if bad_clutch else OK),
        _text("Течеискатель (УФ)", "светящийся след у штуцера" if gas and rng.random() < 0.6 else "утечек нет",
              WARN if gas else OK),
    ]


def check_boost(ctx: VehicleContext, truth: Truth, rng: random.Random) -> list[Reading]:
    turbo, leak = "TURBO_WORN" in truth, "INTAKE_LEAK" in truth
    if turbo:
        boost, shaft, loss, oil = _u(rng, 0.25, 0.65), _u(rng, 0.15, 0.4), _u(rng, 2, 8), "масло в патрубке"
    elif leak:
        boost, shaft, loss, oil = _u(rng, 0.4, 0.75), _u(rng, 0.0, 0.08), _u(rng, 18, 40), "сухо"
    else:
        boost, shaft, loss, oil = _u(rng, 0.9, 1.2), _u(rng, 0.0, 0.08), _u(rng, 0, 6), "сухо"
    return [
        _num("Давление наддува, полная нагрузка", boost, "бар", 0.85, 1.3, decimals=2, warn=0.2),
        _num("Утечка наддувочного тракта при опрессовке", loss, "%", None, 10, decimals=0, warn=6),
        _num("Люфт вала турбины", shaft, "мм", None, 0.1, decimals=2, warn=0.06),
        _text("Следы масла в патрубке после турбины", oil, WARN if oil != "сухо" else OK),
    ]


def check_exhaust(ctx: VehicleContext, truth: Truth, rng: random.Random) -> list[Reading]:
    carb = ctx.tags.get("injection", "mpi") == "carb"
    rich = "CARB_DIRTY" in truth
    misfire = any(c in truth for c in ("PLUGS_WORN", "COIL_FAIL", "INJECTORS"))
    lean = any(c in truth for c in ("INTAKE_LEAK", "MAF_DIRTY", "FUEL_PUMP_WEAK"))
    if rich:
        co, ch, lam = _u(rng, 3.5, 6.5), _u(rng, 400, 900), _u(rng, 0.88, 0.96)
    elif lean:
        co, ch, lam = _u(rng, 0.0, 0.2), _u(rng, 150, 400), _u(rng, 1.06, 1.14)
    elif misfire:
        co, ch, lam = _u(rng, 0.4, 1.4), _u(rng, 400, 1200), _u(rng, 0.98, 1.06)
    else:
        co, ch, lam = (_u(rng, 0.6, 1.6), _u(rng, 100, 300), _u(rng, 0.98, 1.03)) if carb else (
            _u(rng, 0.0, 0.4), _u(rng, 20, 120), _u(rng, 0.99, 1.02))
    return [
        _num("CO на холостом ходу", co, "%", 0.5 if carb else 0.0, 2.0 if carb else 0.5, decimals=2, warn=0.4),
        _num("CH (несгоревшие углеводороды)", ch, "ppm", None, 300 if carb else 150, decimals=0, warn=100),
        _num("Коэффициент избытка воздуха λ", lam, "", 0.97, 1.03, decimals=2, warn=0.04),
    ]


# --- общие дополнения -------------------------------------------------------------


def visual_extra(ctx: VehicleContext, truth: Truth, rng: random.Random) -> list[Reading]:
    """Дополнительные строки визуального осмотра для новых причин."""

    def look(label: str, code: str, p: float, found: str, clear: str) -> Reading:
        if code in truth and rng.random() < p:
            return _text(label, found, WARN)
        return _text(label, clear, OK)

    rows = [
        look("Пыльники приводов и рулевой рейки", "CV_JOINT", 0.5, "порван пыльник, грязь со смазкой", "целые"),
        look("Шланги и сальники ГУР", "PS_LEAK", 0.6, "потёки жидкости", "сухо") if ctx.tags.get("steering", "hyd") == "hyd"
        else None,
        look("Трубки и штуцеры кондиционера", "AC_LOW_GAS", 0.4, "масляный налёт у штуцера", "чисто")
        if ctx.tags.get("ac") else None,
        look("Патрубок после турбины", "TURBO_WORN", 0.45, "масляные подтёки", "сухо") if ctx.tags.get("turbo", True)
        else None,
        look("Маслозаливная горловина", "HEAD_GASKET", 0.3, "светлый налёт-эмульсия", "чисто"),
    ]
    return [r for r in rows if r is not None]


def glow_readings(ctx: VehicleContext, truth: Truth, rng: random.Random) -> list[Reading]:
    """Проверка свечей накала дизеля (вместо свечей зажигания)."""
    bad = "GLOW_FAIL" in truth
    n = _cylinders(ctx)
    broken = rng.randint(1, n) if bad else 0
    readings = []
    for cyl in range(1, n + 1):
        if cyl == broken or (bad and rng.random() < 0.4):
            readings.append(Reading(f"Цилиндр {cyl}: сопротивление свечи накала", "обрыв", "", "0.5–1.2",
                                    BAD))
        else:
            readings.append(_num(f"Цилиндр {cyl}: сопротивление свечи накала", _u(rng, 0.6, 1.1), "Ом", 0.5,
                                 1.2, decimals=2, warn=0.2))
    readings.append(_text("Реле свечей накала", "срабатывает", OK))
    return readings


def extra_dtcs(truth: Truth, rng: random.Random) -> list[str]:
    """Дополнительные коды OBD для новых причин (с вероятностью)."""
    codes: list[str] = []

    def maybe(code: str, p: float) -> None:
        if rng.random() < p and code not in codes:
            codes.append(code)

    if "O2_SENSOR" in truth:
        maybe("P0133", 0.8)
    if "ECT_SENSOR" in truth:
        maybe("P0117", 0.7)
    if "THROTTLE_DIRTY" in truth:
        maybe("P0507", 0.6)
        maybe("P0121", 0.3)
    if "INJECTORS" in truth:
        maybe("P0171", 0.5)
        maybe(f"P030{_idx(truth['INJECTORS']) or 1}", 0.5)
    if "TURBO_WORN" in truth:
        maybe("P0299", 0.75)
    if "GEARBOX_FLUID" in truth:
        maybe("P0700", 0.35)
    if "TIMING_WORN" in truth:
        maybe("P0016", 0.55)
    if "HEAD_GASKET" in truth:
        maybe("P0300", 0.5)
    return codes


EXT_DTC_TEXT: dict[str, tuple[str, str]] = {
    "P0133": ("Лямбда-зонд: медленный отклик", "лямбда-зонд, проводка, утечки выхлопа"),
    "P0117": ("Датчик температуры ОЖ: низкий сигнал", "датчик, проводка, разъём"),
    "P0121": ("Датчик положения дросселя: сигнал вне диапазона", "датчик, дроссель, проводка"),
    "P0299": ("Недостаточный наддув", "турбина, утечки наддува, клапан"),
    "P0700": ("Неисправность системы управления АКПП", "блок АКПП, масло, датчики"),
    "P0016": ("Рассогласование положения коленвала и распредвала", "ремень/цепь ГРМ, датчики"),
}

EXT_HANDLERS = {
    "compression": check_compression,
    "timing": check_timing,
    "drivetrain": check_drivetrain,
    "chassis": check_chassis,
    "sensors": check_sensors,
    "aircond": check_aircond,
    "boost": check_boost,
    "exhaust": check_exhaust,
}

__all__ = ["EXT_HANDLERS", "INFO"]
