"""Справочник ремонта: симптомы, методы диагностики и ремонтные операции по причинам.

Для каждой причины неисправности (fault_catalog) описаны:
  * симптомы, с которыми клиент обычно приезжает (общие, не называющие деталь);
  * проверки, которые помогают выявить причину;
  * ремонтные операции: время и нужные детали (тип детали + количество).
Деталь подбирается под автомобиль по тегам (part_catalog); качество выбирает игрок
при покупке, а при ремонте со склада списывается подходящая по совместимости.
"""

from dataclasses import dataclass

from app.game_data.diagnostic_checks import CHECK_BY_CODE
from app.game_data.fault_catalog import CAUSE_BY_CODE
from app.game_data.part_catalog import PART_TYPE_BY_CODE


@dataclass(frozen=True, slots=True)
class PartNeed:
    type_code: str
    qty: int = 1


@dataclass(frozen=True, slots=True)
class RepairOp:
    code: str  # уникален в рамках всех причин, до 32 символов
    title: str
    minutes: int
    needs: tuple[PartNeed, ...] = ()


@dataclass(frozen=True, slots=True)
class FaultInfo:
    cause_code: str
    symptoms: tuple[str, ...]
    checks: tuple[str, ...]
    ops: tuple[RepairOp, ...]


def _n(type_code: str, qty: int = 1) -> PartNeed:
    return PartNeed(type_code, qty)


def _op(cause: str, no: int, title: str, minutes: int, *needs: PartNeed) -> RepairOp:
    return RepairOp(f"{cause}.{no}", title, minutes, tuple(needs))


def _info(cause: str, symptoms: tuple[str, ...], checks: tuple[str, ...], *ops: RepairOp) -> FaultInfo:
    return FaultInfo(cause, symptoms, checks, ops)


_INFO_LIST: tuple[FaultInfo, ...] = (
    _info("BAT_WEAK", ("Тяжёлый пуск", "Тусклые приборы"), ("battery", "starter", "alternator"),
          _op("BAT_WEAK", 1, "Заменить аккумулятор", 10, _n("battery"))),
    _info("ALT_FAIL", ("Садится АКБ", "Горит лампа заряда"), ("alternator", "battery", "obd"),
          _op("ALT_FAIL", 1, "Заменить генератор", 40, _n("alt"))),
    _info("FUSE_BLOWN", ("Не работает один потребитель",), ("fuses", "visual"),
          _op("FUSE_BLOWN", 1, "Заменить предохранитель", 10, _n("fuse"))),
    _info("WIRE_CORR", ("Плохой контакт, провалы напряжения",), ("fuses", "starter", "visual"),
          _op("WIRE_CORR", 1, "Зачистить и заменить клеммы и массу", 20, _n("terminal"))),
    _info("STARTER_FAIL", ("Вялый пуск, щелчки",), ("starter", "battery"),
          _op("STARTER_FAIL", 1, "Заменить стартер", 45, _n("starter"))),
    _info("PLUGS_WORN", ("Троит, плохой разгон",), ("plugs", "obd", "exhaust"),
          _op("PLUGS_WORN", 1, "Заменить свечи зажигания", 25, _n("plugs"))),
    _info("COIL_FAIL", ("Троит на одном цилиндре",), ("plugs", "obd"),
          _op("COIL_FAIL", 1, "Заменить катушку зажигания", 20, _n("coil"))),
    _info("FUEL_PUMP_WEAK", ("Провалы под нагрузкой",), ("fuel", "obd"),
          _op("FUEL_PUMP_WEAK", 1, "Заменить топливный насос", 50, _n("fuelpump"))),
    _info("FUEL_FILTER_CLOG", ("Не тянет на скорости",), ("fuel", "obd"),
          _op("FUEL_FILTER_CLOG", 1, "Заменить топливный фильтр", 20, _n("fuelfltr"))),
    _info("INTAKE_LEAK", ("Плавают обороты",), ("intake", "obd", "exhaust"),
          _op("INTAKE_LEAK", 1, "Заменить патрубки и прокладки впуска", 30, _n("intake"))),
    _info("MAF_DIRTY", ("Неровный холостой ход",), ("obd", "sensors"),
          _op("MAF_DIRTY", 1, "Промыть датчик расхода воздуха", 15)),
    _info("COOLANT_LEAK", ("Падает уровень антифриза",), ("cooling", "visual"),
          _op("COOLANT_LEAK", 1, "Заменить патрубок и долить антифриз", 40, _n("coolhose"), _n("antifrz"))),
    _info("THERMOSTAT_STUCK", ("Не греет печка или перегрев",), ("cooling", "obd"),
          _op("THERMOSTAT_STUCK", 1, "Заменить термостат", 35, _n("thermo"), _n("antifrz"))),
    _info("FAN_FAIL", ("Перегрев в пробке",), ("cooling", "fuses"),
          _op("FAN_FAIL", 1, "Заменить вентилятор радиатора", 35, _n("fan"))),
    _info("BRAKE_PADS_WORN", ("Скрип, увод при торможении",), ("brakes", "visual"),
          _op("BRAKE_PADS_WORN", 1, "Заменить тормозные колодки", 30, _n("pads"))),
    _info("BRAKE_FLUID_OLD", ("Мягкая педаль",), ("brakes",),
          _op("BRAKE_FLUID_OLD", 1, "Заменить тормозную жидкость и прокачать", 25, _n("brkfluid"))),
    _info("SUSP_LINK", ("Стук на мелких неровностях",), ("suspension",),
          _op("SUSP_LINK", 1, "Заменить стойки стабилизатора", 20, _n("link", 2))),
    _info("SUSP_STRUT", ("Раскачка, стук на кочках",), ("suspension",),
          _op("SUSP_STRUT", 1, "Заменить амортизаторы оси", 60, _n("strut", 2))),
    _info("OIL_LEAK", ("Масляные пятна",), ("visual", "compression"),
          _op("OIL_LEAK", 1, "Заменить прокладки и сальники, долить масло", 60, _n("oilseal"), _n("oil"))),
    _info("CLUTCH_WORN", ("Пробуксовка, запах гари",), ("drivetrain",),
          _op("CLUTCH_WORN", 1, "Заменить комплект сцепления", 120, _n("clutch"))),
    _info("GEARBOX_FLUID", ("Рывки при переключении",), ("drivetrain", "obd"),
          _op("GEARBOX_FLUID", 1, "Заменить масло и фильтр коробки", 40, _n("gearoil"))),
    _info("CV_JOINT", ("Хруст в поворотах",), ("chassis", "visual"),
          _op("CV_JOINT", 1, "Заменить шарнир привода", 60, _n("cvjoint"))),
    _info("WHEEL_BEARING", ("Гул от колеса",), ("chassis", "suspension"),
          _op("WHEEL_BEARING", 1, "Заменить ступичный подшипник", 50, _n("bearing"))),
    _info("TIE_ROD", ("Люфт руля",), ("chassis", "suspension"),
          _op("TIE_ROD", 1, "Заменить рулевой наконечник", 30, _n("tierod")),
          _op("TIE_ROD", 2, "Выставить развал-схождение", 25)),
    _info("PS_LEAK", ("Тугой руль, подтёки",), ("chassis", "visual"),
          _op("PS_LEAK", 1, "Заменить шланг и сальник ГУР", 45, _n("pshose"))),
    _info("TIMING_WORN", ("Шум в моторе, троение",), ("timing", "compression", "obd"),
          _op("TIMING_WORN", 1, "Заменить комплект привода ГРМ", 180, _n("timing"))),
    _info("HEAD_GASKET", ("Белый дым, уходит антифриз",), ("compression", "cooling", "visual"),
          _op("HEAD_GASKET", 1, "Заменить прокладку ГБЦ", 240, _n("headgask"), _n("antifrz"), _n("oil"))),
    _info("TURBO_WORN", ("Нет тяги, свист",), ("boost", "obd"),
          _op("TURBO_WORN", 1, "Заменить турбокомпрессор", 150, _n("turbo"), _n("oil"))),
    _info("AC_LOW_GAS", ("Кондиционер дует тёплым",), ("aircond", "visual"),
          _op("AC_LOW_GAS", 1, "Устранить утечку и заправить кондиционер", 40, _n("refrig"))),
    _info("AC_COMP", ("Кондиционер не включается",), ("aircond",),
          _op("AC_COMP", 1, "Заменить компрессор кондиционера", 90, _n("accomp"), _n("refrig"))),
    _info("O2_SENSOR", ("Горит Check, вырос расход",), ("sensors", "obd", "exhaust"),
          _op("O2_SENSOR", 1, "Заменить датчик кислорода", 20, _n("o2"))),
    _info("ECT_SENSOR", ("Вентилятор включается невпопад",), ("sensors", "cooling"),
          _op("ECT_SENSOR", 1, "Заменить датчик температуры ОЖ", 15, _n("ect"))),
    _info("THROTTLE_DIRTY", ("Плавают обороты после прогрева",), ("sensors", "obd"),
          _op("THROTTLE_DIRTY", 1, "Очистить дроссельную заслонку", 25, _n("throttle"))),
    _info("INJECTORS", ("Троит, вырос расход",), ("sensors", "exhaust", "plugs"),
          _op("INJECTORS", 1, "Заменить комплект форсунок", 70, _n("injector"))),
    _info("CARB_DIRTY", ("Богатая смесь, чёрный нагар",), ("exhaust", "plugs"),
          _op("CARB_DIRTY", 1, "Разобрать и почистить карбюратор, заменить ремкомплект", 50, _n("carbkit"))),
    _info("GLOW_FAIL", ("Дизель не заводится в мороз",), ("plugs", "battery"),
          _op("GLOW_FAIL", 1, "Заменить свечи накала", 45, _n("glow"))),
)

FAULT_INFO: dict[str, FaultInfo] = {i.cause_code: i for i in _INFO_LIST}
OPS_BY_CODE: dict[str, RepairOp] = {op.code: op for info in _INFO_LIST for op in info.ops}
CAUSE_OF_OP: dict[str, str] = {op.code: info.cause_code for info in _INFO_LIST for op in info.ops}


def ops_for_cause(cause_code: str) -> tuple[RepairOp, ...]:
    info = FAULT_INFO.get(cause_code)
    return info.ops if info else ()


# --- контроль целостности при импорте --------------------------------------------
if set(FAULT_INFO) != set(CAUSE_BY_CODE):
    raise RuntimeError("Справочник ремонта должен покрывать все причины неисправностей")
if len(OPS_BY_CODE) != sum(len(i.ops) for i in _INFO_LIST):
    raise RuntimeError("Коды ремонтных операций должны быть уникальными")
for _info_item in _INFO_LIST:
    for _check in _info_item.checks:
        if _check not in CHECK_BY_CODE:
            raise RuntimeError(f"{_info_item.cause_code}: неизвестная проверка {_check}")
    for _op_item in _info_item.ops:
        if len(_op_item.code) > 32:
            raise RuntimeError(f"Слишком длинный код операции {_op_item.code}")
        for _need in _op_item.needs:
            if _need.type_code not in PART_TYPE_BY_CODE or _need.qty <= 0:
                raise RuntimeError(f"{_op_item.code}: неизвестная деталь {_need.type_code}")
