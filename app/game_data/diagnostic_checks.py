"""Диагностические проверки, инструменты и справочные значения по моделям."""

from dataclasses import dataclass

from app.game_data.catalog import EquipmentSpec
from app.game_data.enums import EquipmentCategory

# Сколько минут срока заказа съедает одна игровая минута работы.
DEADLINE_MINUTES_PER_GAME_MINUTE = 2

TOOLSET = "TOOLSET-BASIC"
MULTIMETER = "MULTIMETER"
OBD_SCANNER = "OBD-SCANNER"
FUEL_KIT = "FUEL-PRESSURE-KIT"
BRAKE_TESTER = "BRAKE-SUSP-TESTER"
COMPRESSION_TESTER = "COMPRESSION-TESTER"
AC_MANIFOLD = "AC-MANIFOLD"

# Новое оборудование для диагностики (TOOLSET-BASIC и OBD-SCANNER уже есть в каталоге).
DIAGNOSTIC_EQUIPMENT: tuple[EquipmentSpec, ...] = (
    EquipmentSpec(MULTIMETER, "Мультиметр", EquipmentCategory.DIAGNOSTIC, 1_200, 1),
    EquipmentSpec(FUEL_KIT, "Манометр топливного давления", EquipmentCategory.DIAGNOSTIC, 4_500, 2),
    EquipmentSpec(BRAKE_TESTER, "Тестер тормозов и подвески", EquipmentCategory.DIAGNOSTIC, 6_000, 2),
    EquipmentSpec(COMPRESSION_TESTER, "Компрессометр", EquipmentCategory.DIAGNOSTIC, 2_500, 1),
    EquipmentSpec(AC_MANIFOLD, "Манометрический коллектор кондиционера", EquipmentCategory.DIAGNOSTIC, 5_000, 3),
)

# Инструменты, нужные для диагностики, в порядке показа.
TOOL_CODES: tuple[str, ...] = (
    TOOLSET, MULTIMETER, OBD_SCANNER, FUEL_KIT, BRAKE_TESTER, COMPRESSION_TESTER, AC_MANIFOLD,
)
TOOL_TITLES: dict[str, str] = {
    TOOLSET: "Набор инструментов",
    MULTIMETER: "Мультиметр",
    OBD_SCANNER: "OBD-II сканер",
    FUEL_KIT: "Манометр топливного давления",
    BRAKE_TESTER: "Тестер тормозов и подвески",
    COMPRESSION_TESTER: "Компрессометр",
    AC_MANIFOLD: "Манометрический коллектор кондиционера",
}


@dataclass(frozen=True, slots=True)
class CheckDef:
    code: str
    title: str
    emoji: str
    group: str
    tool_code: str | None
    minutes: int
    # Расходные материалы: платятся всегда.
    consumable_cost: int
    # Аренда оборудования у соседнего сервиса, если своего нет.
    rental_fee: int
    description: str
    # Что умеет и чего не умеет эта проверка (показывается игроку).
    interpretation: str
    # Условия применимости по тегам автомобиля (пусто — подходит любой машине).
    requires: tuple[tuple[str, tuple[object, ...]], ...] = ()


CHECK_GROUPS: tuple[str, ...] = (
    "Электрика", "Двигатель", "Охлаждение", "Тормоза и подвеска", "Трансмиссия и рулевое",
    "Кондиционер", "Осмотр",
)

CHECKS: tuple[CheckDef, ...] = (
    CheckDef(
        "visual", "Визуальный осмотр", "👁", "Осмотр", None, 10, 0, 0,
        "Осмотр подкапотного пространства и колёс без инструментов.",
        "Глазом видно не всё: «чисто» не означает «исправно».",
    ),
    CheckDef(
        "battery", "Напряжение АКБ", "🔋", "Электрика", MULTIMETER, 5, 0, 150,
        "Замер напряжения покоя аккумулятора.",
        "Низкое напряжение бывает и у изношенной батареи, и при недозаряде от генератора.",
    ),
    CheckDef(
        "alternator", "Зарядка генератора", "⚡", "Электрика", MULTIMETER, 10, 0, 150,
        "Напряжение бортсети на работающем двигателе и пульсации.",
        "Показывает, как заряжает генератор, но не состояние самой батареи.",
    ),
    CheckDef(
        "fuses", "Предохранители и цепи", "🔌", "Электрика", MULTIMETER, 15, 0, 200,
        "Прозвонка предохранителей и падение напряжения на силовых проводах.",
        "Перегоревший предохранитель — следствие: почему он перегорел, надо выяснять отдельно.",
    ),
    CheckDef(
        "starter", "Стартер", "🔑", "Электрика", MULTIMETER, 15, 0, 250,
        "Напряжение, ток и обороты при проворачивании двигателя.",
        "Слабый пуск даёт и батарея, и стартер, и плохой контакт: сравнивай напряжение и ток.",
    ),
    CheckDef(
        "plugs", "Свечи и катушки", "🔥", "Двигатель", TOOLSET, 30, 0, 200,
        "Зазоры и вид свечей, сопротивление вторичной обмотки катушек.",
        "Закопчённая свеча — часто следствие пропусков, а не их причина.",
    ),
    CheckDef(
        "obd", "Ошибки OBD-II", "📟", "Двигатель", OBD_SCANNER, 5, 0, 300,
        "Чтение кодов неисправностей и живых данных блока управления.",
        "Код указывает на систему или цепь, а не на конкретную деталь: проверь причину замерами.",
        (("ecu", (True,)),),
    ),
    CheckDef(
        "fuel", "Давление топлива", "⛽", "Двигатель", FUEL_KIT, 20, 0, 600,
        "Давление в рампе на холостых, под нагрузкой и удержание после остановки.",
        "Низкое давление не различает насос, фильтр и питание насоса.",
    ),
    CheckDef(
        "intake", "Подсос воздуха", "💨", "Двигатель", TOOLSET, 20, 100, 200,
        "Разрежение во впуске и проба с распылением очистителя.",
        "Низкое разрежение бывает и при пропусках зажигания: смотри на колебания и реакцию на распыление.",
    ),
    CheckDef(
        "cooling", "Система охлаждения", "🌡", "Охлаждение", TOOLSET, 25, 0, 200,
        "Уровень, опрессовка, работа термостата и включение вентилятора.",
        "Невключение вентилятора может быть и неисправностью самого вентилятора, и питания.",
    ),
    CheckDef(
        "brakes", "Тормоза", "🛑", "Тормоза и подвеска", BRAKE_TESTER, 25, 150, 700,
        "Колодки, эффективность, разбаланс усилий и качество жидкости.",
        "Увод при торможении даёт не только тормозная система.",
    ),
    CheckDef(
        "suspension", "Подвеска", "🛞", "Тормоза и подвеска", BRAKE_TESTER, 20, 0, 700,
        "Эффективность амортизаторов и люфты узлов подвески.",
        "Стук и скрип подвески могут давать разные узлы: сравнивай стороны.",
    ),
    CheckDef(
        "compression", "Компрессия и ГБЦ", "🗜", "Двигатель", COMPRESSION_TESTER, 30, 0, 400,
        "Компрессия по цилиндрам, пузырьки в бачке, состояние масла.",
        "Низкая компрессия в паре соседних цилиндров похожа на ГБЦ, но износ колец даёт другую картину.",
    ),
    CheckDef(
        "timing", "Привод ГРМ", "⛓", "Двигатель", TOOLSET, 35, 0, 200,
        "Износ ремня или вытяжка цепи, метки ГРМ.",
        "Шум цепи на холодную бывает и без критического износа: сравнивай с замером люфта.",
    ),
    CheckDef(
        "exhaust", "Анализ выхлопа", "🌫", "Двигатель", TOOLSET, 15, 80, 250,
        "CO, CH и λ на холостом ходу.",
        "Богатая смесь не говорит, карбюратор это, форсунки или свечи: сопоставь с другими замерами.",
    ),
    CheckDef(
        "sensors", "Датчики (живые данные)", "📡", "Двигатель", OBD_SCANNER, 15, 0, 300,
        "Лямбда-зонд, температура ОЖ, дроссель и баланс форсунок.",
        "Показания датчика могут врать: сверяй с независимым замером.",
        (("ecu", (True,)),),
    ),
    CheckDef(
        "boost", "Наддув", "🌀", "Двигатель", TOOLSET, 20, 0, 300,
        "Давление наддува, опрессовка тракта, люфт вала турбины.",
        "Низкий наддув даёт и сама турбина, и утечка в патрубках.",
        (("turbo", (True,)),),
    ),
    CheckDef(
        "drivetrain", "Сцепление и КПП", "🕹", "Трансмиссия и рулевое", TOOLSET, 25, 0, 200,
        "Ход педали, проба на пробуксовку, уровень и состояние масла в коробке.",
        "Рывки в коробке бывают из-за масла, а не из-за износа механизма.",
    ),
    CheckDef(
        "chassis", "Рулевое, привод и ступицы", "🎡", "Трансмиссия и рулевое", TOOLSET, 30, 0, 200,
        "Люфты наконечников, подшипников, приводов; жидкость ГУР.",
        "Стук и гул дают разные узлы: сравнивай левую и правую стороны.",
    ),
    CheckDef(
        "aircond", "Кондиционер", "❄️", "Кондиционер", AC_MANIFOLD, 25, 100, 600,
        "Давление по сторонам, температура на выходе, муфта компрессора.",
        "Тёплый воздух бывает из-за утечки хладагента, компрессора и даже вентилятора радиатора.",
        (("ac", (True,)),),
    ),
)


CHECK_BY_CODE: dict[str, CheckDef] = {c.code: c for c in CHECKS}
if len(CHECK_BY_CODE) != len(CHECKS):
    raise RuntimeError("Коды проверок должны быть уникальными")
for _check in CHECKS:
    if _check.group not in CHECK_GROUPS:
        raise RuntimeError(f"Неизвестная группа проверки {_check.code}")
    if _check.tool_code is not None and _check.tool_code not in TOOL_TITLES:
        raise RuntimeError(f"Неизвестный инструмент проверки {_check.code}")


def check_available(check: CheckDef, tags: dict[str, object] | None) -> bool:
    """Подходит ли проверка автомобилю (OBD-II на карбюраторной машине не бывает и т. п.)."""
    if tags is None:
        return True
    return all(tags.get(key) in allowed for key, allowed in check.requires)


def check_fee(check: CheckDef, tool_owned: bool) -> int:
    """Сколько стоит проверка: расходники + аренда, если своего инструмента нет."""
    rental = 0 if (check.tool_code is None or tool_owned) else check.rental_fee
    return check.consumable_cost + rental


@dataclass(frozen=True, slots=True)
class ModelSpec:
    """Справочные значения модели для расчёта измерений (игровые, приближённые)."""

    fuel_bar: float
    thermostat_c: int
    fan_on_c: int
    pad_new_mm: float


MODEL_SPECS: dict[str, ModelSpec] = {
    "2114": ModelSpec(3.0, 85, 99, 12.0),
    "Granta": ModelSpec(3.0, 85, 98, 12.0),
    "Corolla": ModelSpec(3.4, 82, 93, 11.0),
    "Polo": ModelSpec(3.7, 87, 95, 12.0),
    "Solaris": ModelSpec(3.8, 82, 95, 11.0),
}
DEFAULT_MODEL_SPEC = ModelSpec(3.3, 85, 96, 11.0)

PLUG_GAP_MM: dict[str, float] = {
    "2111": 1.0, "21114": 1.0, "21124": 1.1, "11186": 1.0, "11189": 1.0, "21127": 1.1,
    "4ZZ-FE": 1.1, "1ZR-FE": 1.1, "2ZR-FE": 1.1, "CFNA": 0.8, "CWVA": 0.8,
    "G4FA": 1.0, "G4FC": 1.0,
}
DEFAULT_PLUG_GAP_MM = 1.0
