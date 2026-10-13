"""Стартовый каталог: запчасти, оборудование и конфигурации автомобилей.

Загружается в БД при инициализации. Повторная загрузка безопасна: существующие
записи не перезаписываются (цены, изменённые вручную в БД, сохраняются).
"""

from dataclasses import dataclass

from app.game_data.enums import (
    DriveType,
    EquipmentCategory,
    FuelType,
    PartCategory,
    Transmission,
)


@dataclass(frozen=True, slots=True)
class PartSpec:
    sku: str
    name: str
    category: PartCategory
    base_price: int


@dataclass(frozen=True, slots=True)
class EquipmentSpec:
    code: str
    name: str
    category: EquipmentCategory
    price: int
    required_level: int


@dataclass(frozen=True, slots=True)
class CarConfigSpec:
    brand: str
    model: str
    year: int
    body_type: str
    engine_code: str
    engine_volume_cc: int
    power_hp: int
    fuel_type: FuelType
    transmission: Transmission
    drive_type: DriveType


PARTS: tuple[PartSpec, ...] = (
    PartSpec("OIL-5W30-4L", "Масло моторное 5W-30, 4 л", PartCategory.FLUIDS, 2_400),
    PartSpec("FLT-OIL", "Фильтр масляный", PartCategory.FILTERS, 450),
    PartSpec("FLT-AIR", "Фильтр воздушный", PartCategory.FILTERS, 600),
    PartSpec("FLT-CABIN", "Фильтр салонный", PartCategory.FILTERS, 550),
    PartSpec("SPK-PLUG", "Свеча зажигания", PartCategory.ENGINE, 380),
    PartSpec("COIL-IGN", "Катушка зажигания", PartCategory.ELECTRICS, 1_900),
    PartSpec("BRK-PAD-F", "Колодки тормозные передние", PartCategory.BRAKES, 2_200),
    PartSpec("BRK-DISC-F", "Диск тормозной передний", PartCategory.BRAKES, 3_800),
    PartSpec("BRK-FLUID", "Тормозная жидкость DOT 4, 1 л", PartCategory.FLUIDS, 700),
    PartSpec("SUS-STRUT-F", "Амортизатор передний", PartCategory.SUSPENSION, 5_500),
    PartSpec("SUS-LINK", "Стойка стабилизатора", PartCategory.SUSPENSION, 900),
    PartSpec("BELT-TIMING", "Комплект ремня ГРМ", PartCategory.ENGINE, 6_800),
    PartSpec("BAT-60AH", "Аккумулятор 60 А·ч", PartCategory.ELECTRICS, 6_200),
    PartSpec("CLUTCH-KIT", "Комплект сцепления", PartCategory.TRANSMISSION, 9_500),
)

EQUIPMENT: tuple[EquipmentSpec, ...] = (
    EquipmentSpec("TOOLSET-BASIC", "Базовый набор инструментов", EquipmentCategory.HAND_TOOLS, 0, 1),
    EquipmentSpec("JACK-FLOOR", "Подкатной домкрат", EquipmentCategory.LIFTING, 4_500, 1),
    EquipmentSpec("OBD-SCANNER", "OBD-II сканер", EquipmentCategory.DIAGNOSTIC, 3_500, 1),
    EquipmentSpec("IMPACT-WRENCH", "Пневмогайковёрт", EquipmentCategory.POWER_TOOLS, 8_000, 2),
    EquipmentSpec("LIFT-2POST", "Двухстоечный подъёмник", EquipmentCategory.LIFTING, 85_000, 3),
    EquipmentSpec("DIAG-PRO", "Профессиональный диагностический стенд", EquipmentCategory.DIAGNOSTIC, 60_000, 4),
    EquipmentSpec("TIRE-CHANGER", "Шиномонтажный станок", EquipmentCategory.SHOP, 55_000, 4),
)

CAR_CONFIGURATIONS: tuple[CarConfigSpec, ...] = (
    CarConfigSpec("Lada", "Granta", 2018, "sedan", "11186", 1596, 87,
                  FuelType.PETROL, Transmission.MANUAL, DriveType.FWD),
    CarConfigSpec("Kia", "Rio", 2016, "sedan", "G4FA", 1396, 107,
                  FuelType.PETROL, Transmission.AUTOMATIC, DriveType.FWD),
    CarConfigSpec("Hyundai", "Solaris", 2015, "sedan", "G4FC", 1591, 123,
                  FuelType.PETROL, Transmission.MANUAL, DriveType.FWD),
    CarConfigSpec("Volkswagen", "Polo", 2014, "sedan", "CFNA", 1598, 105,
                  FuelType.PETROL, Transmission.AUTOMATIC, DriveType.FWD),
    CarConfigSpec("Toyota", "Camry", 2012, "sedan", "2AR-FE", 2494, 181,
                  FuelType.PETROL, Transmission.AUTOMATIC, DriveType.FWD),
    CarConfigSpec("Renault", "Duster", 2017, "suv", "F4R", 1998, 135,
                  FuelType.PETROL, Transmission.MANUAL, DriveType.AWD),
)
