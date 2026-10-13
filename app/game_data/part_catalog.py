"""Единый каталог запчастей: типы деталей, совместимость, качество и цены.

Деталь = тип + «посадка» (двигатель / кузов-шасси / группа свечей / класс АКБ /
коробка передач или универсальная) + качество. Все варианты порождаются кодом и
записываются в таблицу parts лениво, при первом показе или покупке: SKU
`тип:посадка:качество` (до 32 символов). Так каталог покрывает каждый двигатель и
шасси автопарка без десятков тысяч строк в БД.

Совместимость проверяется по тегам автомобиля (fleet.build_tags): деталь подходит
машине, только если её посадка совпадает с соответствующим тегом.
"""

import re
from dataclasses import dataclass

from app.game_data.catalog import PartSpec
from app.game_data.enums import PartCategory
from app.game_data.fleet import FLEET
from app.game_data.rarity import MODEL_RARITY

UNIVERSAL = "ALL"
MAX_SKU = 32


@dataclass(frozen=True, slots=True)
class Quality:
    level: int
    title: str
    emoji: str
    price_pct: int  # множитель цены, %
    note: str


QUALITIES: tuple[Quality, ...] = (
    Quality(1, "Бюджетный", "🥉", 60, "дёшево, ресурс невысокий"),
    Quality(2, "Качественный аналог", "🥈", 100, "оптимальное соотношение цены и качества"),
    Quality(3, "Оригинал", "🥇", 170, "заводское качество и максимальный ресурс"),
)
QUALITY_BY_LEVEL: dict[int, Quality] = {q.level: q for q in QUALITIES}


@dataclass(frozen=True, slots=True)
class PartType:
    code: str  # до 10 символов, входит в SKU
    name: str
    section: str
    category: PartCategory  # значение колонки parts.category
    fit: str | None  # какой тег автомобиля определяет совместимость; None — универсальная
    price: int  # цена «качественного аналога» для обычной машины, ₽
    description: str = ""

    @property
    def universal(self) -> bool:
        return self.fit is None


S_ENGINE = "Двигатель"
S_IGN = "Зажигание"
S_FUEL = "Топливо и впуск"
S_COOL = "Охлаждение"
S_ELEC = "Электрика"
S_BRAKE = "Тормоза"
S_SUSP = "Подвеска и рулевое"
S_TRANS = "Трансмиссия"
S_AC = "Кондиционер"
S_FLUID = "Жидкости и фильтры"

SECTIONS: tuple[str, ...] = (
    S_ENGINE, S_IGN, S_FUEL, S_COOL, S_ELEC, S_BRAKE, S_SUSP, S_TRANS, S_AC, S_FLUID,
)
SECTION_EMOJI: dict[str, str] = {
    S_ENGINE: "⚙️", S_IGN: "🔥", S_FUEL: "⛽", S_COOL: "🌡", S_ELEC: "🔋", S_BRAKE: "🛑",
    S_SUSP: "🛞", S_TRANS: "🕹", S_AC: "❄️", S_FLUID: "🛢",
}

E, EL, BR, SU, FL, TR, FI = (
    PartCategory.ENGINE, PartCategory.ELECTRICS, PartCategory.BRAKES, PartCategory.SUSPENSION,
    PartCategory.FLUIDS, PartCategory.TRANSMISSION, PartCategory.FILTERS,
)

PART_TYPES: tuple[PartType, ...] = (
    # Двигатель
    PartType("oilseal", "Комплект прокладок и сальников", S_ENGINE, E, "engine", 1_800),
    PartType("timing", "Комплект привода ГРМ", S_ENGINE, E, "engine", 6_500),
    PartType("headgask", "Комплект прокладок ГБЦ", S_ENGINE, E, "engine", 5_500),
    PartType("turbo", "Турбокомпрессор", S_ENGINE, E, "engine", 28_000),
    # Зажигание
    PartType("plugs", "Комплект свечей зажигания", S_IGN, EL, "plug", 1_200),
    PartType("coil", "Катушка (модуль) зажигания", S_IGN, EL, "engine", 2_500),
    PartType("glow", "Комплект свечей накала", S_IGN, EL, "plug", 3_200),
    # Топливо и впуск
    PartType("fuelpump", "Топливный насос", S_FUEL, E, "engine", 5_000),
    PartType("fuelfltr", "Топливный фильтр", S_FUEL, FI, "engine", 700),
    PartType("injector", "Комплект форсунок", S_FUEL, E, "engine", 7_500),
    PartType("carbkit", "Ремкомплект карбюратора", S_FUEL, E, "engine", 1_400),
    PartType("intake", "Патрубки и прокладки впуска", S_FUEL, E, "engine", 1_500),
    PartType("maf", "Датчик массового расхода воздуха", S_FUEL, EL, "engine", 3_500),
    PartType("throttle", "Очиститель и прокладка дросселя", S_FUEL, E, "engine", 900),
    PartType("o2", "Датчик кислорода (лямбда-зонд)", S_FUEL, EL, "engine", 3_200),
    PartType("ect", "Датчик температуры охлаждающей жидкости", S_FUEL, EL, "engine", 800),
    # Охлаждение
    PartType("thermo", "Термостат", S_COOL, E, "engine", 1_100),
    PartType("coolhose", "Патрубки системы охлаждения", S_COOL, E, "chassis", 1_300),
    PartType("fan", "Вентилятор радиатора", S_COOL, EL, "chassis", 4_500),
    PartType("antifrz", "Антифриз, 5 л", S_COOL, FL, None, 1_100),
    # Электрика
    PartType("battery", "Аккумуляторная батарея", S_ELEC, EL, "battery", 4_500),
    PartType("alt", "Генератор", S_ELEC, EL, "engine", 9_000),
    PartType("starter", "Стартер", S_ELEC, EL, "engine", 6_500),
    PartType("fuse", "Набор предохранителей", S_ELEC, EL, None, 300),
    PartType("terminal", "Клеммы и провод массы", S_ELEC, EL, None, 700),
    # Тормоза
    PartType("pads", "Колодки тормозные", S_BRAKE, BR, "chassis", 2_200),
    PartType("brkfluid", "Тормозная жидкость DOT 4, 1 л", S_BRAKE, FL, None, 450),
    # Подвеска и рулевое
    PartType("strut", "Амортизатор", S_SUSP, SU, "chassis", 5_500),
    PartType("link", "Стойка стабилизатора", S_SUSP, SU, "chassis", 900),
    PartType("bearing", "Ступичный подшипник", S_SUSP, SU, "chassis", 2_800),
    PartType("tierod", "Рулевой наконечник", S_SUSP, SU, "chassis", 1_500),
    PartType("pshose", "Шланг и сальник ГУР", S_SUSP, SU, "chassis", 3_000),
    # Трансмиссия
    PartType("clutch", "Комплект сцепления", S_TRANS, TR, "engine", 7_500),
    PartType("gearoil", "Масло КПП с фильтром", S_TRANS, TR, "trans", 2_200),
    PartType("cvjoint", "Шарнир привода (ШРУС)", S_TRANS, TR, "chassis", 3_500),
    # Кондиционер
    PartType("refrig", "Хладагент и масло кондиционера", S_AC, FL, None, 1_800),
    PartType("accomp", "Компрессор кондиционера", S_AC, EL, "chassis", 18_000),
    # Жидкости и фильтры
    PartType("oil", "Моторное масло, 4 л", S_FLUID, FL, None, 2_400),
    PartType("oilfltr", "Масляный фильтр", S_FLUID, FI, "engine", 450),
    PartType("airfltr", "Воздушный фильтр", S_FLUID, FI, "chassis", 600),
)
PART_TYPE_BY_CODE: dict[str, PartType] = {p.code: p for p in PART_TYPES}

if len(PART_TYPE_BY_CODE) != len(PART_TYPES):
    raise RuntimeError("Коды типов деталей должны быть уникальными")
for _p in PART_TYPES:
    if _p.section not in SECTIONS or len(_p.code) > 10 or ":" in _p.code:
        raise RuntimeError(f"Некорректный тип детали {_p.code}")

FIT_KEYS = ("engine", "chassis", "plug", "battery", "trans")
_FIT_RE = re.compile(r"^[A-Za-z0-9.\-]{1,16}$")

# Редкость модели -> наценка на детали (дорогие автомобили — дорогие запчасти), %.
_TIER_PCT = {"common": 100, "rare": 220, "epic": 400, "legendary": 900}
_SHARED_FITS = {"trans", "battery"}  # общие для всех машин: цена не зависит от модели


def _build_indexes() -> tuple[dict[tuple[str, str], int], dict[tuple[str, str], set[str]]]:
    tier: dict[tuple[str, str], int] = {}
    users: dict[tuple[str, str], set[str]] = {}
    for trim in FLEET:
        pct = 100
        found = MODEL_RARITY.get(trim.model_id)
        if found:
            pct = _TIER_PCT[found[0].value]
        for key, value in trim.tags.items():
            if key not in FIT_KEYS:
                continue
            ident = (key, str(value))
            users.setdefault(ident, set()).add(f"{trim.brand} {trim.model}")
            tier[ident] = pct if ident not in tier else min(tier[ident], pct)
    return tier, users


_FIT_TIER, _FIT_USERS = _build_indexes()


def fit_value(ptype: PartType, tags: dict[str, object]) -> str:
    """Посадка детали для автомобиля с данными тегами."""
    if ptype.fit is None:
        return UNIVERSAL
    return str(tags[ptype.fit])


def make_sku(type_code: str, fit: str, quality: int) -> str:
    sku = f"{type_code}:{fit}:{quality}"
    if len(sku) > MAX_SKU:
        raise ValueError(f"SKU длиннее {MAX_SKU} символов: {sku}")
    return sku


def parse_sku(sku: str) -> tuple[PartType, str, int] | None:
    """Разбирает SKU динамического каталога. None, если SKU не из этого каталога."""
    parts = sku.split(":")
    if len(parts) != 3:
        return None
    code, fit, q = parts
    ptype = PART_TYPE_BY_CODE.get(code)
    if ptype is None or not q.isdigit() or int(q) not in QUALITY_BY_LEVEL:
        return None
    if ptype.universal != (fit == UNIVERSAL):
        return None
    if not ptype.universal and not _FIT_RE.match(fit):
        return None
    return ptype, fit, int(q)


def price_of(ptype: PartType, fit: str, quality: int) -> int:
    """Цена детали, округлённая до 10 ₽."""
    tier = 100 if ptype.fit is None or ptype.fit in _SHARED_FITS else _FIT_TIER.get((ptype.fit, fit), 100)
    value = ptype.price * QUALITY_BY_LEVEL[quality].price_pct * tier / 10_000
    return max(10, int(round(value / 10.0)) * 10)


def fit_models(ptype: PartType, fit: str, limit: int = 4) -> list[str]:
    """Модели, которым подходит деталь (для карточки в магазине)."""
    if ptype.fit is None:
        return []
    return sorted(_FIT_USERS.get((ptype.fit, fit), ()))[:limit]


def part_name(ptype: PartType, fit: str, quality: int) -> str:
    q = QUALITY_BY_LEVEL[quality]
    where = "универсальная" if ptype.universal else fit
    return f"{ptype.name} [{where}] · {q.title}"[:128]


def spec_for(sku: str) -> PartSpec | None:
    """Описание детали для записи в БД. None — SKU не принадлежит каталогу."""
    parsed = parse_sku(sku)
    if parsed is None:
        return None
    ptype, fit, quality = parsed
    return PartSpec(sku, part_name(ptype, fit, quality), ptype.category, price_of(ptype, fit, quality))


def is_compatible(sku: str, tags: dict[str, object]) -> bool:
    """Подходит ли деталь автомобилю: универсальная — всегда, иная — по совпадению тега."""
    parsed = parse_sku(sku)
    if parsed is None:
        return False
    ptype, fit, _ = parsed
    if ptype.universal:
        return True
    return str(tags.get(ptype.fit or "")) == fit


def types_in_section(section: str) -> list[PartType]:
    return [p for p in PART_TYPES if p.section == section]


def car_skus(ptype: PartType, tags: dict[str, object]) -> list[str]:
    """Все три варианта качества детали для автомобиля."""
    fit = fit_value(ptype, tags)
    return [make_sku(ptype.code, fit, q.level) for q in QUALITIES]
