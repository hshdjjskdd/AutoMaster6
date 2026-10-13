"""Редкость и сложность ремонта моделей автомобилей.

Редкость определяет шанс выпадения заказа, сложность (1–5) задана для каждой модели
отдельно — по конструкции и сложности диагностики. Вероятности игроку не показываются:
в интерфейсе виден только эмодзи редкости.
"""

import random
from enum import StrEnum

from app.game_data.fleet import MODELS


class Rarity(StrEnum):
    COMMON = "common"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"


RARITY_EMOJI: dict[Rarity, str] = {
    Rarity.COMMON: "🟢",
    Rarity.RARE: "🔵",
    Rarity.EPIC: "🟣",
    Rarity.LEGENDARY: "🟡",
}

# Вероятность редкости при создании каждого заказа, в процентах (сумма = 100).
RARITY_WEIGHTS: dict[Rarity, int] = {
    Rarity.COMMON: 60,
    Rarity.RARE: 25,
    Rarity.EPIC: 12,
    Rarity.LEGENDARY: 3,
}

# Допустимый диапазон сложности для редкости.
DIFFICULTY_RANGE: dict[Rarity, tuple[int, int]] = {
    Rarity.COMMON: (1, 2),
    Rarity.RARE: (2, 4),
    Rarity.EPIC: (3, 5),
    Rarity.LEGENDARY: (4, 5),
}

# Множитель оплаты и срока по сложности, в процентах.
DIFFICULTY_PAYMENT_PCT: dict[int, int] = {1: 100, 2: 115, 3: 130, 4: 150, 5: 175}
DIFFICULTY_DEADLINE_PCT: dict[int, int] = {1: 100, 2: 115, 3: 130, 4: 145, 5: 160}

# Дорогие машины редко имеют большой пробег (множитель к пробегу, %).
MILEAGE_PCT: dict[Rarity, int] = {
    Rarity.COMMON: 100,
    Rarity.RARE: 80,
    Rarity.EPIC: 55,
    Rarity.LEGENDARY: 20,
}

# model_id -> (редкость, сложность 1..5)
_C, _R, _E, _L = Rarity.COMMON, Rarity.RARE, Rarity.EPIC, Rarity.LEGENDARY
MODEL_RARITY: dict[str, tuple[Rarity, int]] = {
    # 🟢 Обычные
    "lada-granta": (_C, 1), "lada-vesta": (_C, 2), "lada-priora": (_C, 1),
    "lada-kalina": (_C, 1), "renault-logan": (_C, 1), "renault-sandero": (_C, 1),
    "hyundai-solaris": (_C, 1), "kia-rio": (_C, 1), "vw-polo": (_C, 2),
    "skoda-rapid": (_C, 2), "toyota-corolla": (_C, 1), "toyota-camry": (_C, 2),
    "ford-focus": (_C, 2), "ford-fiesta": (_C, 1), "chevrolet-cruze": (_C, 2),
    "chevrolet-niva": (_C, 2), "daewoo-nexia": (_C, 1), "daewoo-matiz": (_C, 1),
    "nissan-almera": (_C, 1), "vw-golf": (_C, 2),
    # 🔵 Редкие
    "bmw-3": (_R, 3), "bmw-5": (_R, 4), "mb-c": (_R, 3), "mb-e": (_R, 4),
    "audi-a4": (_R, 3), "audi-a6": (_R, 4), "toyota-prado": (_R, 3),
    "toyota-rav4": (_R, 2), "lexus-rx": (_R, 3), "volvo-xc60": (_R, 3),
    "subaru-wrx": (_R, 4), "mitsubishi-evo": (_R, 4), "vw-touareg": (_R, 4),
    "jeep-grand-cherokee": (_R, 3), "ford-mustang": (_R, 3),
    # 🟣 Эпические
    "bmw-m3": (_E, 4), "bmw-m5": (_E, 5), "amg-c63": (_E, 4), "amg-e63": (_E, 5),
    "audi-rs6": (_E, 5), "nissan-gtr": (_E, 5), "toyota-supra": (_E, 3),
    "corvette-c8": (_E, 4), "porsche-911": (_E, 4), "dodge-hellcat": (_E, 3),
    # 🟡 Легендарные
    "bugatti-chiron": (_L, 5), "koenigsegg-jesko": (_L, 5),
    "lamborghini-svj": (_L, 4), "ferrari-sf90": (_L, 5), "mclaren-p1": (_L, 5),
}

MODELS_BY_RARITY: dict[Rarity, tuple[str, ...]] = {
    r: tuple(mid for mid, (rr, _) in MODEL_RARITY.items() if rr == r) for r in Rarity
}

_RARITY_BY_NAME: dict[tuple[str, str], tuple[Rarity, int]] = {
    (MODELS[mid].brand, MODELS[mid].model): value for mid, value in MODEL_RARITY.items()
}

# --- контроль целостности при импорте ------------------------------------------
if sum(RARITY_WEIGHTS.values()) != 100:
    raise RuntimeError("Сумма вероятностей редкости должна быть 100")
for _mid, (_rarity, _difficulty) in MODEL_RARITY.items():
    if _mid not in MODELS:
        raise RuntimeError(f"Нет модели {_mid} в автопарке")
    _lo, _hi = DIFFICULTY_RANGE[_rarity]
    if not _lo <= _difficulty <= _hi:
        raise RuntimeError(f"Сложность {_mid} вне диапазона редкости")


def rarity_of(brand: str, model: str) -> Rarity | None:
    """Редкость модели; None, если модель не участвует в выпадении заказов."""
    found = _RARITY_BY_NAME.get((brand, model))
    return found[0] if found else None


def difficulty_of(brand: str, model: str) -> int:
    """Сложность ремонта модели (1–5); для моделей вне таблицы — 1."""
    found = _RARITY_BY_NAME.get((brand, model))
    return found[1] if found else 1


def rarity_emoji(brand: str, model: str) -> str:
    """Эмодзи редкости для показа игроку (пусто, если у модели нет редкости)."""
    rarity = rarity_of(brand, model)
    return RARITY_EMOJI[rarity] if rarity else ""


def roll_rarity(rng: random.Random) -> Rarity:
    """Независимый бросок редкости по заданным вероятностям."""
    rarities = list(RARITY_WEIGHTS)
    return rng.choices(rarities, weights=[RARITY_WEIGHTS[r] for r in rarities], k=1)[0]
