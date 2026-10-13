"""Движок измерений: что покажет проверка при данных реальных неисправностях.

Чистая логика без БД. Результат зависит от (реальные неисправности, автомобиль,
rng): шум измерений разный в каждой попытке, но воспроизводим по seed.

Принципы реализма, заложенные здесь:
  * разные причины дают пересекающиеся значения (разряженная АКБ и неисправный
    генератор оба дают низкое напряжение покоя);
  * каждая проверка видит только свою часть картины;
  * коды OBD-II появляются с вероятностью, могут быть чужими или отсутствовать;
  * одна неисправность часто требует двух-трёх проверок для уверенного вывода.
"""

import random
from dataclasses import dataclass, field

from app.game_data.diagnostic_checks import (
    CHECK_BY_CODE,
    DEFAULT_MODEL_SPEC,
    DEFAULT_PLUG_GAP_MM,
    MODEL_SPECS,
    PLUG_GAP_MM,
)

OK = "ok"
WARN = "warn"
BAD = "bad"
INFO = "info"

CIRCUIT_TITLES: dict[str, str] = {
    "ignition": "зажигания",
    "fuel_pump": "топливного насоса",
    "fan": "вентилятора радиатора",
    "lights": "освещения",
}


@dataclass(frozen=True, slots=True)
class VehicleContext:
    model: str
    engine_code: str
    engine_volume_cc: int
    mileage_km: int
    # Теги совместимости автомобиля (fleet.build_tags); пусто — старое поведение.
    tags: dict[str, object] = field(default_factory=dict, hash=False, compare=False)


@dataclass(frozen=True, slots=True)
class Reading:
    label: str
    value: str
    unit: str = ""
    norm: str = ""
    flag: str = INFO
    note: str = ""


@dataclass(frozen=True, slots=True)
class CheckOutcome:
    readings: tuple[Reading, ...]
    interpretation: str


Truth = dict[str, str]  # код причины -> детали


def _fmt(value: float, decimals: int) -> str:
    return f"{value:.{decimals}f}"


def _num(
    label: str,
    value: float,
    unit: str,
    lo: float | None,
    hi: float | None,
    *,
    decimals: int = 1,
    warn: float = 0.0,
    note: str = "",
) -> Reading:
    """Числовое измерение с нормой [lo, hi]; warn — ширина «пограничной» зоны."""
    below = lo is not None and value < lo
    above = hi is not None and value > hi
    if not below and not above:
        flag = OK
    else:
        distance = (lo - value) if below else (value - hi)  # type: ignore[operator]
        flag = WARN if distance <= warn else BAD
    if lo is not None and hi is not None:
        norm = f"{_fmt(lo, decimals)}–{_fmt(hi, decimals)}"
    elif lo is not None:
        norm = f"от {_fmt(lo, decimals)}"
    elif hi is not None:
        norm = f"до {_fmt(hi, decimals)}"
    else:
        norm = ""
    return Reading(label, _fmt(value, decimals), unit, norm, flag, note)


def _text(label: str, value: str, flag: str = INFO, note: str = "") -> Reading:
    return Reading(label, value, "", "", flag, note)


def _u(rng: random.Random, lo: float, hi: float) -> float:
    return rng.uniform(lo, hi)


def _side(detail: str, side: str) -> bool:
    return detail == "both" or detail == side


# --- электрика -------------------------------------------------------------


def _battery_voltage(truth: Truth, rng: random.Random) -> float:
    if "BAT_WEAK" in truth and "ALT_FAIL" in truth:
        return _u(rng, 11.5, 12.0)
    if "BAT_WEAK" in truth:
        return _u(rng, 11.7, 12.15)
    if "ALT_FAIL" in truth:
        return _u(rng, 12.0, 12.35)
    return _u(rng, 12.45, 12.75)


def _check_battery(ctx: VehicleContext, truth: Truth, rng: random.Random) -> list[Reading]:
    return [
        _num("Напряжение покоя на клеммах", _battery_voltage(truth, rng), "В", 12.4, 12.8,
             decimals=2, warn=0.3),
    ]


def _check_alternator(ctx: VehicleContext, truth: Truth, rng: random.Random) -> list[Reading]:
    alt = truth.get("ALT_FAIL")
    if alt == "no_charge":
        idle, high, ripple = _u(rng, 12.3, 12.9), _u(rng, 12.4, 13.0), _u(rng, 60, 120)
    elif alt == "overcharge":
        idle, high, ripple = _u(rng, 15.1, 15.9), _u(rng, 15.2, 16.0), _u(rng, 30, 90)
    elif alt == "diode":
        idle, high, ripple = _u(rng, 13.2, 13.7), _u(rng, 13.3, 13.9), _u(rng, 350, 800)
    elif "BAT_WEAK" in truth:
        idle, high, ripple = _u(rng, 14.2, 14.7), _u(rng, 14.2, 14.7), _u(rng, 20, 80)
    elif "WIRE_CORR" in truth:
        idle, high, ripple = _u(rng, 13.4, 14.0), _u(rng, 13.5, 14.1), _u(rng, 20, 90)
    else:
        idle, high, ripple = _u(rng, 13.9, 14.5), _u(rng, 14.0, 14.6), _u(rng, 20, 80)
    return [
        _num("Напряжение бортсети, холостой ход", idle, "В", 13.8, 14.6, decimals=2, warn=0.5),
        _num("Напряжение бортсети, 2500 об/мин", high, "В", 13.8, 14.7, decimals=2, warn=0.5),
        _num("Пульсации напряжения", ripple, "мВ", None, 100, decimals=0, warn=100),
    ]


def _check_fuses(ctx: VehicleContext, truth: Truth, rng: random.Random) -> list[Reading]:
    blown = truth.get("FUSE_BLOWN")
    readings = []
    for circuit, title in CIRCUIT_TITLES.items():
        if blown == circuit:
            readings.append(_text(f"Предохранитель цепи {title}", "перегорел", BAD))
        else:
            readings.append(_text(f"Предохранитель цепи {title}", "цел", OK))
    drop = _u(rng, 0.5, 1.2) if "WIRE_CORR" in truth else _u(rng, 0.05, 0.2)
    readings.append(
        _num("Падение напряжения на плюсе и массе под нагрузкой", drop, "В", None, 0.3,
             decimals=2, warn=0.15)
    )
    return readings


def _check_starter(ctx: VehicleContext, truth: Truth, rng: random.Random) -> list[Reading]:
    scale = 1.15 if ctx.engine_volume_cc >= 1700 else 1.0
    bat, starter = "BAT_WEAK" in truth, "STARTER_FAIL" in truth
    wire, alt = "WIRE_CORR" in truth, "ALT_FAIL" in truth
    if bat and starter:
        volts, amps, rpm, drop = _u(rng, 8.0, 9.0), _u(rng, 180, 240), _u(rng, 100, 150), _u(rng, 0.2, 0.4)
    elif bat:
        volts, amps, rpm, drop = _u(rng, 8.2, 9.4), _u(rng, 85, 120), _u(rng, 140, 190), _u(rng, 0.2, 0.4)
    elif starter:
        volts, amps, rpm, drop = _u(rng, 9.5, 10.3), _u(rng, 210, 290), _u(rng, 110, 170), _u(rng, 0.2, 0.4)
    elif wire:
        volts, amps, rpm, drop = _u(rng, 10.3, 11.0), _u(rng, 90, 130), _u(rng, 150, 200), _u(rng, 2.0, 3.5)
    elif alt:
        volts, amps, rpm, drop = _u(rng, 9.3, 10.0), _u(rng, 105, 140), _u(rng, 190, 230), _u(rng, 0.1, 0.4)
    else:
        volts, amps, rpm, drop = _u(rng, 10.0, 11.2), _u(rng, 110, 160), _u(rng, 220, 290), _u(rng, 0.1, 0.4)
    return [
        _num("Напряжение на АКБ при проворачивании", volts, "В", 9.6, 12.5, warn=0.6),
        _num("Ток стартера", amps * scale, "А", 105 * scale, 175 * scale,
             decimals=0, warn=25),
        _num("Обороты проворачивания", rpm, "об/мин", 200, 300, decimals=0, warn=30),
        _num("Падение напряжения АКБ — стартер", drop, "В", None, 0.5, decimals=2, warn=0.3),
    ]


# --- двигатель -------------------------------------------------------------


def _check_plugs(ctx: VehicleContext, truth: Truth, rng: random.Random) -> list[Reading]:
    if ctx.tags.get("fuel") == "diesel":
        from app.game_data.diagnostic_engine_ext import glow_readings

        return glow_readings(ctx, truth, rng)
    cylinders = min(int(ctx.tags.get("cylinders", 4)), 6)  # type: ignore[call-overload]
    gap = PLUG_GAP_MM.get(ctx.engine_code, DEFAULT_PLUG_GAP_MM)
    worn = "PLUGS_WORN" in truth
    coil_detail = truth.get("COIL_FAIL", "")
    bad_cyl = int(coil_detail.split(":")[1]) if coil_detail.startswith("cyl:") else 0
    lean = any(c in truth for c in ("INTAKE_LEAK", "MAF_DIRTY", "FUEL_PUMP_WEAK", "FUEL_FILTER_CLOG"))
    readings: list[Reading] = []
    for cyl in range(1, cylinders + 1):
        g = gap + (_u(rng, 0.25, 0.45) if worn else _u(rng, -0.05, 0.1))
        readings.append(
            _num(f"Цилиндр {cyl}: зазор свечи", g, "мм", gap - 0.05, gap + 0.15,
                 decimals=2, warn=0.1)
        )
        if cyl == bad_cyl:
            look, flag = "чёрный сухой нагар", WARN
        elif worn:
            look, flag = "электроды закруглены, износ", WARN
        elif lean and rng.random() < 0.5:
            look, flag = "светлый налёт", WARN
        else:
            look, flag = "светло-коричневый налёт", OK
        readings.append(_text(f"Цилиндр {cyl}: вид свечи", look, flag))
        if cyl == bad_cyl:
            if rng.random() < 0.5:
                readings.append(
                    Reading(f"Цилиндр {cyl}: вторичная обмотка катушки", "обрыв", "", "6.0–13.0", BAD)
                )
            else:
                readings.append(
                    _num(f"Цилиндр {cyl}: вторичная обмотка катушки", _u(rng, 2.1, 3.5), "кОм",
                         6.0, 13.0, warn=1.0)
                )
        else:
            readings.append(
                _num(f"Цилиндр {cyl}: вторичная обмотка катушки", _u(rng, 7.5, 11.5), "кОм",
                     6.0, 13.0, warn=1.0)
            )
    return readings


_DTC_TEXT: dict[str, tuple[str, str]] = {
    "P0300": ("Случайные / множественные пропуски зажигания", "зажигание, топливо, впуск"),
    "P0301": ("Пропуски зажигания в цилиндре 1", "зажигание, форсунка, компрессия"),
    "P0302": ("Пропуски зажигания в цилиндре 2", "зажигание, форсунка, компрессия"),
    "P0303": ("Пропуски зажигания в цилиндре 3", "зажигание, форсунка, компрессия"),
    "P0304": ("Пропуски зажигания в цилиндре 4", "зажигание, форсунка, компрессия"),
    "P0171": ("Смесь слишком бедная", "подсос воздуха, ДМРВ, давление топлива, форсунки"),
    "P0101": ("ДМРВ: сигнал вне ожидаемого диапазона", "ДМРВ, воздуховод, проводка"),
    "P0507": ("Обороты холостого хода выше ожидаемых", "подсос воздуха, регулятор ХХ"),
    "P0230": ("Цепь управления топливным насосом", "реле, предохранитель, проводка, насос"),
    "P0351": ("Цепь управления катушкой зажигания", "катушка, питание, проводка, ЭБУ"),
    "P0480": ("Цепь управления вентилятором охлаждения", "реле, предохранитель, вентилятор"),
    "P0128": ("Температура ОЖ ниже порога открытия термостата", "термостат, датчик температуры"),
    "P0217": ("Перегрев двигателя", "охлаждение, термостат, вентилятор"),
    "P0562": ("Низкое напряжение бортсети", "АКБ, генератор, клеммы, проводка"),
    "P0563": ("Высокое напряжение бортсети", "реле-регулятор генератора, проводка"),
    "P0420": ("Эффективность катализатора ниже порога", "катализатор, лямбда-зонд, пропуски"),
    "P0455": ("Крупная утечка в системе улавливания паров", "крышка бака, шланги, клапан"),
}


def _dtcs(truth: Truth, ctx: VehicleContext, rng: random.Random) -> list[tuple[str, bool]]:
    """Список (код, активен). Коды выпадают с вероятностью и бывают чужими."""
    codes: list[tuple[str, bool]] = []

    def maybe(code: str, p: float) -> None:
        if rng.random() < p and all(code != c for c, _ in codes):
            codes.append((code, True))

    if "PLUGS_WORN" in truth:
        maybe("P0300", 0.8)
        maybe(f"P030{rng.randint(1, 4)}", 0.4)
    coil = truth.get("COIL_FAIL", "")
    if coil.startswith("cyl:"):
        maybe(f"P030{coil.split(':')[1]}", 0.9)
        maybe("P0300", 0.3)
    if "INTAKE_LEAK" in truth:
        maybe("P0171", 0.85)
        maybe("P0507", 0.3)
    if "MAF_DIRTY" in truth:
        maybe("P0171", 0.6)
        maybe("P0101", 0.4)
    if "FUEL_PUMP_WEAK" in truth:
        maybe("P0171", 0.5)
    if "FUEL_FILTER_CLOG" in truth:
        maybe("P0171", 0.4)
    circuit = truth.get("FUSE_BLOWN")
    if circuit == "fuel_pump":
        maybe("P0230", 0.7)
    elif circuit == "ignition":
        maybe("P0351", 0.5)
    elif circuit == "fan":
        maybe("P0480", 0.6)
    if "FAN_FAIL" in truth:
        maybe("P0480", 0.5)
    stuck = truth.get("THERMOSTAT_STUCK")
    if stuck == "open":
        maybe("P0128", 0.85)
    elif stuck == "closed":
        maybe("P0217", 0.3)
    if "COOLANT_LEAK" in truth:
        maybe("P0217", 0.15)
    alt = truth.get("ALT_FAIL")
    if alt == "overcharge":
        maybe("P0563", 0.7)
    elif alt:
        maybe("P0562", 0.7)
    if "BAT_WEAK" in truth:
        maybe("P0562", 0.3)
    if "WIRE_CORR" in truth:
        maybe("P0562", 0.3)
    # Случайные «посторонние» записи, не связанные с поломкой.
    if rng.random() < (0.3 if ctx.mileage_km > 150_000 else 0.1):
        codes.append(("P0420", rng.random() < 0.5))
    if rng.random() < 0.08:
        codes.append(("P0455", False))
    return codes


def _check_obd(ctx: VehicleContext, truth: Truth, rng: random.Random) -> list[Reading]:
    readings: list[Reading] = []
    from app.game_data.diagnostic_engine_ext import EXT_DTC_TEXT, extra_dtcs

    dtcs = _dtcs(truth, ctx, rng)
    texts = {**_DTC_TEXT, **EXT_DTC_TEXT}
    for extra in extra_dtcs(truth, rng):
        if all(extra != c for c, _ in dtcs):
            dtcs.append((extra, True))
    if not dtcs:
        readings.append(_text("Коды неисправностей", "ошибок не найдено", OK))
    for code, active in dtcs:
        title, area = texts[code]
        readings.append(
            _text(
                code,
                title + ("" if active else " (сохранённая, не активна)"),
                WARN if active else INFO,
                f"Затронутая область: {area}. Это не приговор конкретной детали.",
            )
        )

    leak, maf = "INTAKE_LEAK" in truth, "MAF_DIRTY" in truth
    pump, filt = "FUEL_PUMP_WEAK" in truth, "FUEL_FILTER_CLOG" in truth
    if leak:
        stft_idle, stft_load = _u(rng, 10, 20), _u(rng, 2, 6)
    elif maf:
        stft_idle, stft_load = _u(rng, 7, 14), _u(rng, 6, 12)
    elif pump:
        stft_idle, stft_load = _u(rng, 2, 6), _u(rng, 10, 18)
    elif filt:
        stft_idle, stft_load = _u(rng, 1, 5), _u(rng, 8, 14)
    else:
        stft_idle, stft_load = _u(rng, -3, 3), _u(rng, -3, 3)
    readings += [
        _num("Топливная коррекция, холостой ход", stft_idle, "%", -7, 7, warn=3),
        _num("Топливная коррекция, 2500 об/мин", stft_load, "%", -7, 7, warn=3),
    ]
    stuck = truth.get("THERMOSTAT_STUCK")
    if stuck == "open":
        ect = _u(rng, 66, 76)
    elif stuck == "closed":
        ect = _u(rng, 104, 112)
    else:
        ect = _u(rng, 88, 96)
    readings.append(_num("Температура ОЖ после прогрева", ect, "°C", 85, 100, decimals=0, warn=6))
    misfire = "PLUGS_WORN" in truth or "COIL_FAIL" in truth
    if leak:
        rpm = _u(rng, 950, 1150)
    elif misfire:
        rpm = _u(rng, 640, 780)
    elif maf:
        rpm = _u(rng, 700, 950)
    else:
        rpm = _u(rng, 770, 880)
    readings.append(_num("Обороты холостого хода", rpm, "об/мин", 750, 900, decimals=0, warn=80))
    return readings


def _check_fuel(ctx: VehicleContext, truth: Truth, rng: random.Random) -> list[Reading]:
    spec = MODEL_SPECS.get(ctx.model, DEFAULT_MODEL_SPEC).fuel_bar
    note = ""
    if truth.get("FUSE_BLOWN") == "fuel_pump":
        idle = load = hold = 0.0
        note = "Насос не включается: нет характерного гудения при включении зажигания."
    elif "FUEL_PUMP_WEAK" in truth:
        idle = spec * _u(rng, 0.62, 0.8)
        load = spec * _u(rng, 0.45, 0.65)
        hold = idle * _u(rng, 0.8, 0.9)
    elif "FUEL_FILTER_CLOG" in truth:
        idle = spec * _u(rng, 0.88, 1.0)
        load = spec * _u(rng, 0.5, 0.7)
        hold = idle * _u(rng, 0.85, 0.95)
    else:
        idle = spec + _u(rng, -0.15, 0.15)
        load = spec - _u(rng, 0.0, 0.2)
        hold = spec * _u(rng, 0.82, 0.95)
    return [
        _num("Давление в рампе, холостой ход", idle, "бар", spec - 0.3, spec + 0.3,
             decimals=2, warn=0.3, note=note),
        _num("Давление при резком открытии дросселя", load, "бар", spec - 0.4, spec + 0.4,
             decimals=2, warn=0.3),
        _num("Остаточное давление через 5 мин", hold, "бар", spec * 0.8, spec + 0.2,
             decimals=2, warn=0.3),
    ]


def _check_intake(ctx: VehicleContext, truth: Truth, rng: random.Random) -> list[Reading]:
    leak = truth.get("INTAKE_LEAK")
    misfire = "PLUGS_WORN" in truth or "COIL_FAIL" in truth
    if leak:
        vacuum = _u(rng, 36, 50)
        flutter = _u(rng, 1.0, 3.0)
        spray = _u(rng, 180, 420)
        where = "в зоне воздуховода" if leak == "hose" else "по стыку впускного коллектора"
        spray_note = f"Обороты выросли {where}."
    else:
        vacuum = _u(rng, 46, 60) if misfire else _u(rng, 58, 68)
        flutter = _u(rng, 5.0, 10.0) if misfire else _u(rng, 0.5, 2.5)
        spray = _u(rng, 0, 25)
        spray_note = ""
    return [
        _num("Разрежение на холостом ходу", vacuum, "кПа", 56, 70, warn=6),
        _num("Колебания стрелки вакуумметра", flutter, "кПа", None, 3.0, warn=1.5),
        _num("Прирост оборотов при распылении очистителя", spray, "об/мин", None, 40,
             decimals=0, warn=30, note=spray_note),
    ]


# --- охлаждение -------------------------------------------------------------


def _check_cooling(ctx: VehicleContext, truth: Truth, rng: random.Random) -> list[Reading]:
    spec = MODEL_SPECS.get(ctx.model, DEFAULT_MODEL_SPEC)
    readings: list[Reading] = []
    if "COOLANT_LEAK" in truth:
        low = rng.random() < 0.85
        readings.append(_text("Уровень охлаждающей жидкости", "ниже MIN" if low else "около MIN",
                              BAD if low else WARN))
        drop = _u(rng, 0.25, 0.6)
    else:
        readings.append(_text("Уровень охлаждающей жидкости", "в норме", OK))
        drop = _u(rng, 0.0, 0.05)
    readings.append(_num("Падение давления при опрессовке за 5 мин", drop, "бар", None, 0.1,
                         decimals=2, warn=0.1))

    stuck = truth.get("THERMOSTAT_STUCK")
    t = spec.thermostat_c
    if stuck == "open":
        opens = _u(rng, 38, 50)
        peak = _u(rng, 65, 76)
    elif stuck == "closed":
        opens = _u(rng, 100, 108)
        peak = _u(rng, 104, 112)
    else:
        opens = t + _u(rng, -2, 2)
        peak = t + _u(rng, 7, 12)
    readings.append(_num("Температура начала открытия термостата", opens, "°C", t - 3, t + 3,
                         decimals=0, warn=4))
    readings.append(_num("Максимум за 15 мин прогрева", peak, "°C", t + 5, t + 15,
                         decimals=0, warn=5))

    if "FAN_FAIL" in truth or truth.get("FUSE_BLOWN") == "fan":
        readings.append(_text("Включение вентилятора", "не включился до 108 °C", BAD))
    else:
        on = spec.fan_on_c + _u(rng, -2, 2)
        readings.append(_num("Температура включения вентилятора", on, "°C", spec.fan_on_c - 3,
                             spec.fan_on_c + 3, decimals=0, warn=3))
    return readings


# --- тормоза и подвеска ---------------------------------------------------------


def _check_brakes(ctx: VehicleContext, truth: Truth, rng: random.Random) -> list[Reading]:
    spec = MODEL_SPECS.get(ctx.model, DEFAULT_MODEL_SPEC)
    pads = truth.get("BRAKE_PADS_WORN")

    def pad(side: str) -> float:
        if pads and _side(pads, side):
            return _u(rng, 1.0, 2.6)
        return _u(rng, spec.pad_new_mm * 0.5, spec.pad_new_mm * 0.9)

    if pads in ("left", "right"):
        imbalance = _u(rng, 14, 26)
    else:
        imbalance = _u(rng, 2, 8)
    if pads:
        efficiency = _u(rng, 58, 68)
    elif "BRAKE_FLUID_OLD" in truth:
        efficiency = _u(rng, 66, 74)
    else:
        efficiency = _u(rng, 78, 92)
    if "BRAKE_FLUID_OLD" in truth:
        water = _u(rng, 3.8, 6.5)
        boil = _u(rng, 125, 165)
    else:
        water = _u(rng, 0.3, 1.8)
        boil = _u(rng, 205, 235)
    return [
        _num("Толщина колодки, левая передняя", pad("left"), "мм", 3.0, spec.pad_new_mm + 0.5, warn=1.0),
        _num("Толщина колодки, правая передняя", pad("right"), "мм", 3.0, spec.pad_new_mm + 0.5, warn=1.0),
        _num("Разбаланс тормозных усилий по оси", imbalance, "%", None, 10, warn=4),
        _num("Эффективность торможения", efficiency, "%", 70, None, decimals=0, warn=4),
        _num("Вода в тормозной жидкости", water, "%", None, 3.0, warn=0.8),
        _num("Температура кипения жидкости (расчётная)", boil, "°C", 180, None, decimals=0, warn=25),
    ]


def _check_suspension(ctx: VehicleContext, truth: Truth, rng: random.Random) -> list[Reading]:
    strut = truth.get("SUSP_STRUT")
    link = truth.get("SUSP_LINK")
    left = _u(rng, 62, 85)
    right = min(88.0, max(60.0, left + _u(rng, -10, 10)))
    if strut == "left":
        left = _u(rng, 22, 38)
    elif strut == "right":
        right = _u(rng, 22, 38)
    link_l = _u(rng, 0.0, 0.4)
    link_r = _u(rng, 0.0, 0.4)
    if link == "left":
        link_l = _u(rng, 2.0, 4.5)
    elif link == "right":
        link_r = _u(rng, 2.0, 4.5)
    return [
        _num("Эффективность амортизатора, левый", left, "%", 50, None, decimals=0, warn=8),
        _num("Эффективность амортизатора, правый", right, "%", 50, None, decimals=0, warn=8),
        _num("Разница между сторонами", abs(left - right), "%", None, 15, decimals=0, warn=6),
        _num("Люфт стойки стабилизатора, левая", link_l, "мм", None, 0.8, decimals=1, warn=0.5),
        _num("Люфт стойки стабилизатора, правая", link_r, "мм", None, 0.8, decimals=1, warn=0.5),
        _num("Люфт шаровой опоры", _u(rng, 0.1, 0.5), "мм", None, 1.0, decimals=1, warn=0.5),
    ]


# --- осмотр -----------------------------------------------------------------


def _check_visual(ctx: VehicleContext, truth: Truth, rng: random.Random) -> list[Reading]:
    def look(label: str, code: str, p: float, found: str, clear: str) -> Reading:
        if code in truth and rng.random() < p:
            return _text(label, found, WARN)
        return _text(label, clear, OK)

    from app.game_data.diagnostic_engine_ext import visual_extra

    leak_hose = truth.get("INTAKE_LEAK") == "hose"
    rows = [
        look("Следы масла на двигателе", "OIL_LEAK", 0.9,
             "потёки на крышке клапанов / поддоне", "сухо"),
        look("Следы охлаждающей жидкости", "COOLANT_LEAK", 0.5,
             "потёки вокруг патрубка", "следов нет"),
        look("Воздуховод и гофры", "INTAKE_LEAK", 0.35 if leak_hose else 0.0,
             "небольшая трещина на гофре", "без видимых дефектов"),
        look("Клеммы АКБ и масса", "WIRE_CORR", 0.75,
             "окислены, контакт плохой", "без видимых дефектов"),
        look("Тормозные колодки (через спицы)", "BRAKE_PADS_WORN", 0.5,
             "остаток тонкий", "остаток выглядит приемлемым"),
        look("Блок предохранителей", "FUSE_BLOWN", 0.15,
             "один предохранитель потемнел", "визуально все целы"),
    ]
    return rows + visual_extra(ctx, truth, rng)


_HANDLERS = {
    "visual": _check_visual,
    "battery": _check_battery,
    "alternator": _check_alternator,
    "fuses": _check_fuses,
    "starter": _check_starter,
    "plugs": _check_plugs,
    "obd": _check_obd,
    "fuel": _check_fuel,
    "intake": _check_intake,
    "cooling": _check_cooling,
    "brakes": _check_brakes,
    "suspension": _check_suspension,
}



def _handler(check_code: str):  # type: ignore[no-untyped-def]
    handler = _HANDLERS.get(check_code)
    if handler is None:  # проверки этапа 5 живут в отдельном модуле
        from app.game_data.diagnostic_engine_ext import EXT_HANDLERS

        handler = EXT_HANDLERS[check_code]
    return handler


def perform_check(
    check_code: str, ctx: VehicleContext, truth: Truth, rng: random.Random
) -> CheckOutcome:
    """Выполняет проверку и возвращает измеренные значения."""
    readings = _handler(check_code)(ctx, truth, rng)
    return CheckOutcome(tuple(readings), CHECK_BY_CODE[check_code].interpretation)
