"""Автопарк клиентов: модели, комплектации (силовые установки) и теги совместимости.

Каждая комплектация (Trim) имеет уникальный catalog_id, технические параметры и теги.
Теги определяют, какие детали подходят автомобилю и какие неисправности на нём возможны:
  engine / chassis     — ключи совместимости деталей;
  injection, ignition, timing, turbo, fuel, trans, ac, steering — условия неисправностей.

Значения игровые и приближённые, не заводские данные.
"""

from dataclasses import dataclass, field

from app.game_data.engines import ENGINES, EngineSpec
from app.game_data.enums import DriveType, FuelType, Transmission

FWD, RWD, AWD = DriveType.FWD, DriveType.RWD, DriveType.AWD

_TRANS: dict[str, Transmission] = {
    "MT": Transmission.MANUAL,
    "AT": Transmission.AUTOMATIC,
    "CVT": Transmission.CVT,
    "AMT": Transmission.ROBOT,
    "DCT": Transmission.ROBOT,
}
_TRANS_TAG: dict[Transmission, str] = {
    Transmission.MANUAL: "MT",
    Transmission.AUTOMATIC: "AT",
    Transmission.CVT: "CVT",
    Transmission.ROBOT: "AMT",
}

Tags = dict[str, object]


@dataclass(frozen=True, slots=True)
class ModelInfo:
    model_id: str
    brand: str
    model: str
    body_type: str
    chassis: str
    steering: str  # mech | hyd | eps
    ac: bool
    drive: DriveType


@dataclass(frozen=True, slots=True)
class Trim:
    """Комплектация автомобиля (модель + силовая установка)."""

    brand: str
    model: str
    name: str
    years: tuple[int, ...]
    body_type: str
    engine_code: str
    engine_volume_cc: int
    power_hp: int
    transmission: Transmission
    price_factor_pct: int
    fuel_type: FuelType = FuelType.PETROL
    drive_type: DriveType = DriveType.FWD
    model_id: str = ""
    chassis: str = "GENERIC"
    steering: str = "hyd"
    ac: bool = True
    trans_tag: str = "MT"
    extra: dict[str, object] = field(default_factory=dict, hash=False, compare=False)

    @property
    def title(self) -> str:
        return f"{self.brand} {self.model}"

    @property
    def catalog_id(self) -> str:
        """Уникальный ID комплектации: модель / двигатель / коробка / мощность / первый год."""
        return f"{self.model_id}/{self.engine_code}/{self.trans_tag}/{self.power_hp}/{self.years[0]}"

    @property
    def tags(self) -> Tags:
        return build_tags(
            self.engine_code, self.trans_tag, self.chassis, self.steering, self.ac,
            volume_cc=self.engine_volume_cc,
        )

    def configuration_kwargs(self, year: int) -> dict[str, object]:
        """Поля технической конфигурации для автомобиля этого года выпуска."""
        if year not in self.years:
            raise ValueError(f"{self.title} «{self.name}» не выпускалась в {year} году")
        return {
            "brand": self.brand,
            "model": self.model,
            "year": year,
            "body_type": self.body_type,
            "engine_code": self.engine_code,
            "engine_volume_cc": self.engine_volume_cc,
            "power_hp": self.power_hp,
            "fuel_type": self.fuel_type,
            "transmission": self.transmission,
            "drive_type": self.drive_type,
        }


def battery_class(volume_cc: int, fuel: FuelType) -> str:
    """Класс аккумулятора по объёму двигателя (определяет совместимость АКБ)."""
    if fuel == FuelType.DIESEL:
        return "75"
    if volume_cc <= 1300:
        return "45"
    if volume_cc <= 1800:
        return "55"
    if volume_cc <= 2500:
        return "62"
    return "75"


def build_tags(
    engine_code: str,
    trans_tag: str,
    chassis: str,
    steering: str,
    ac: bool,
    *,
    volume_cc: int | None = None,
) -> Tags:
    engine = ENGINES.get(engine_code)
    tags: Tags = {
        "engine": engine_code,
        "chassis": chassis,
        "trans": trans_tag,
        "steering": steering,
        "ac": ac,
    }
    if engine is not None:
        tags.update(
            injection=engine.injection,
            ignition=engine.ignition,
            timing=engine.timing,
            turbo=engine.turbo,
            fuel=engine.fuel_type.value,
            plug=engine.plug,
            cylinders=engine.cylinders,
            ecu=engine.has_ecu,
            battery=battery_class(engine.volume_cc, engine.fuel_type),
        )
    else:  # неизвестный двигатель (например, старое сохранение): самые частые значения
        tags.update(
            injection="mpi", ignition="coil", timing="belt", turbo=False, fuel="petrol",
            plug=f"P-{engine_code}", cylinders=4, ecu=True,
            battery=battery_class(volume_cc or 1600, FuelType.PETROL),
        )
    return tags


# --- модели -------------------------------------------------------------------

_MODEL_LIST: tuple[ModelInfo, ...] = tuple(
    ModelInfo(mid, brand, model, body, chassis, steering, ac, drive)
    for mid, brand, model, body, chassis, steering, ac, drive in (
        # ВАЗ классика и переднеприводные
        ("vaz-2101", "ВАЗ", "2101", "седан", "VAZ-CLASSIC", "mech", False, RWD),
        ("vaz-2102", "ВАЗ", "2102", "универсал", "VAZ-CLASSIC", "mech", False, RWD),
        ("vaz-2103", "ВАЗ", "2103", "седан", "VAZ-CLASSIC", "mech", False, RWD),
        ("vaz-2104", "ВАЗ", "2104", "универсал", "VAZ-CLASSIC", "mech", False, RWD),
        ("vaz-2105", "ВАЗ", "2105", "седан", "VAZ-CLASSIC", "mech", False, RWD),
        ("vaz-2106", "ВАЗ", "2106", "седан", "VAZ-CLASSIC", "mech", False, RWD),
        ("vaz-2107", "ВАЗ", "2107", "седан", "VAZ-CLASSIC", "mech", False, RWD),
        ("vaz-2108", "ВАЗ", "2108", "хэтчбек", "VAZ-2108", "mech", False, FWD),
        ("vaz-2109", "ВАЗ", "2109", "хэтчбек", "VAZ-2108", "mech", False, FWD),
        ("vaz-21099", "ВАЗ", "21099", "седан", "VAZ-2108", "mech", False, FWD),
        ("vaz-2110", "ВАЗ", "2110", "седан", "VAZ-2110", "mech", False, FWD),
        ("vaz-2111", "ВАЗ", "2111", "универсал", "VAZ-2110", "mech", False, FWD),
        ("vaz-2112", "ВАЗ", "2112", "хэтчбек", "VAZ-2110", "mech", False, FWD),
        ("vaz-2113", "ВАЗ", "2113", "хэтчбек", "VAZ-2108", "mech", False, FWD),
        ("vaz-2114", "ВАЗ", "2114", "хэтчбек", "VAZ-2108", "mech", False, FWD),
        ("vaz-2115", "ВАЗ", "2115", "седан", "VAZ-2108", "mech", False, FWD),
        # LADA
        ("lada-priora", "LADA", "Priora", "седан", "LADA-PRIORA", "hyd", True, FWD),
        ("lada-kalina", "LADA", "Kalina", "хэтчбек", "LADA-KALINA", "mech", False, FWD),
        ("lada-granta", "LADA", "Granta", "седан", "LADA-KALINA", "mech", False, FWD),
        ("lada-vesta", "LADA", "Vesta", "седан", "LADA-VESTA", "eps", True, FWD),
        ("lada-largus", "LADA", "Largus", "универсал", "REN-B0", "hyd", True, FWD),
        ("lada-niva", "LADA", "Niva Legend", "внедорожник", "VAZ-NIVA", "mech", False, AWD),
        ("chevrolet-niva", "Chevrolet", "Niva", "внедорожник", "CHEVY-NIVA", "hyd", True, AWD),
        # ГАЗ / УАЗ
        ("gaz-3110", "ГАЗ", "3110", "седан", "GAZ-3110", "hyd", False, RWD),
        ("gaz-gazelle", "ГАЗ", "Газель", "фургон", "GAZELLE", "hyd", False, RWD),
        ("uaz-patriot", "УАЗ", "Patriot", "внедорожник", "UAZ-PATRIOT", "hyd", True, AWD),
        # Renault
        ("renault-logan", "Renault", "Logan", "седан", "REN-B0", "hyd", True, FWD),
        ("renault-sandero", "Renault", "Sandero", "хэтчбек", "REN-B0", "hyd", True, FWD),
        ("renault-duster", "Renault", "Duster", "внедорожник", "REN-DUSTER", "hyd", True, FWD),
        # Hyundai / Kia
        ("hyundai-solaris", "Hyundai", "Solaris", "седан", "HK-RB", "hyd", True, FWD),
        ("hyundai-creta", "Hyundai", "Creta", "внедорожник", "HK-CRETA", "eps", True, FWD),
        ("hyundai-tucson", "Hyundai", "Tucson", "внедорожник", "HK-SUV", "eps", True, FWD),
        ("kia-rio", "Kia", "Rio", "седан", "HK-RB", "hyd", True, FWD),
        ("kia-ceed", "Kia", "Ceed", "хэтчбек", "KIA-CEED", "eps", True, FWD),
        ("kia-sportage", "Kia", "Sportage", "внедорожник", "HK-SUV", "eps", True, FWD),
        # VW group
        ("vw-polo", "Volkswagen", "Polo", "седан", "VW-PQ25", "eps", True, FWD),
        ("skoda-octavia", "Skoda", "Octavia", "лифтбэк", "VW-PQ35", "eps", True, FWD),
        ("skoda-rapid", "Skoda", "Rapid", "лифтбэк", "VW-PQ25", "eps", True, FWD),
        # Toyota / Nissan
        ("toyota-corolla", "Toyota", "Corolla", "седан", "TOY-E150", "eps", True, FWD),
        ("toyota-camry", "Toyota", "Camry", "седан", "TOY-XV40", "hyd", True, FWD),
        ("toyota-rav4", "Toyota", "RAV4", "внедорожник", "TOY-RAV4", "eps", True, AWD),
        ("nissan-almera", "Nissan", "Almera", "седан", "NIS-B10", "hyd", True, FWD),
        ("nissan-qashqai", "Nissan", "Qashqai", "внедорожник", "NIS-J10", "eps", True, FWD),
        # Ford / GM / Daewoo / Opel / Suzuki
        ("ford-focus", "Ford", "Focus", "хэтчбек", "FORD-FOC2", "hyd", True, FWD),
        ("chevrolet-lacetti", "Chevrolet", "Lacetti", "седан", "GM-LACETTI", "hyd", True, FWD),
        ("chevrolet-cobalt", "Chevrolet", "Cobalt", "седан", "GM-COBALT", "hyd", True, FWD),
        ("daewoo-nexia", "Daewoo", "Nexia", "седан", "DAEWOO-NEX", "mech", False, FWD),
        ("daewoo-matiz", "Daewoo", "Matiz", "хэтчбек", "DAEWOO-MAT", "mech", False, FWD),
        ("opel-astra", "Opel", "Astra", "хэтчбек", "OPEL-ASTRA", "eps", True, FWD),
        ("suzuki-grand-vitara", "Suzuki", "Grand Vitara", "внедорожник", "SUZ-GV", "hyd", True, AWD),
        # Mazda / Mitsubishi / Honda
        ("mazda-3", "Mazda", "3", "седан", "MAZDA-3", "hyd", True, FWD),
        ("mazda-6", "Mazda", "6", "седан", "MAZDA-6", "hyd", True, FWD),
        ("mazda-cx5", "Mazda", "CX-5", "внедорожник", "MAZDA-CX5", "eps", True, AWD),
        ("mitsubishi-lancer", "Mitsubishi", "Lancer", "седан", "MIT-LANCER", "hyd", True, FWD),
        ("mitsubishi-outlander", "Mitsubishi", "Outlander", "внедорожник", "MIT-OUTL", "hyd", True, AWD),
        ("honda-civic", "Honda", "Civic", "седан", "HON-CIVIC", "hyd", True, FWD),
        ("honda-crv", "Honda", "CR-V", "внедорожник", "HON-CRV", "hyd", True, AWD),
        # Китай
        ("chery-tiggo", "Chery", "Tiggo", "внедорожник", "CHERY-T11", "hyd", True, FWD),
        ("chery-tiggo7pro", "Chery", "Tiggo 7 Pro", "внедорожник", "CHERY-T7", "eps", True, FWD),
        ("geely-coolray", "Geely", "Coolray", "внедорожник", "GEELY-COOL", "eps", True, FWD),
        ("geely-emgrand", "Geely", "Emgrand", "седан", "GEELY-EMGR", "eps", True, FWD),
        ("haval-jolion", "Haval", "Jolion", "внедорожник", "HAVAL-JOL", "eps", True, FWD),
        ("haval-h6", "Haval", "H6", "внедорожник", "HAVAL-H6", "eps", True, AWD),
        ("changan-cs55", "Changan", "CS55", "внедорожник", "CHANGAN-55", "eps", True, FWD),
        # Ford / Chevrolet / VW (массовые)
        ("ford-fiesta", "Ford", "Fiesta", "хэтчбек", "FORD-FIESTA", "eps", True, FWD),
        ("chevrolet-cruze", "Chevrolet", "Cruze", "седан", "GM-CRUZE", "eps", True, FWD),
        ("vw-golf", "Volkswagen", "Golf", "хэтчбек", "VW-PQ35", "eps", True, FWD),
        # Премиум (редкие)
        ("bmw-3", "BMW", "3 Series", "седан", "BMW-E90", "eps", True, RWD),
        ("bmw-5", "BMW", "5 Series", "седан", "BMW-F10", "eps", True, RWD),
        ("mb-c", "Mercedes-Benz", "C-Class", "седан", "MB-W204", "eps", True, RWD),
        ("mb-e", "Mercedes-Benz", "E-Class", "седан", "MB-W212", "eps", True, RWD),
        ("audi-a4", "Audi", "A4", "седан", "AUDI-B8", "eps", True, AWD),
        ("audi-a6", "Audi", "A6", "седан", "AUDI-C7", "eps", True, AWD),
        ("toyota-prado", "Toyota", "Land Cruiser Prado", "внедорожник", "TOY-J150", "hyd", True, AWD),
        ("lexus-rx", "Lexus", "RX", "внедорожник", "LEX-RX", "eps", True, AWD),
        ("volvo-xc60", "Volvo", "XC60", "внедорожник", "VOLVO-XC60", "eps", True, AWD),
        ("subaru-wrx", "Subaru", "WRX", "седан", "SUB-GR", "hyd", True, AWD),
        ("mitsubishi-evo", "Mitsubishi", "Lancer Evolution", "седан", "MIT-EVO", "hyd", True, AWD),
        ("vw-touareg", "Volkswagen", "Touareg", "внедорожник", "VW-TOUAREG", "eps", True, AWD),
        ("jeep-grand-cherokee", "Jeep", "Grand Cherokee", "внедорожник", "JEEP-WK2", "hyd", True, AWD),
        ("ford-mustang", "Ford", "Mustang", "купе", "FORD-MUSTANG", "eps", True, RWD),
        # Эпические
        ("bmw-m3", "BMW", "M3", "седан", "BMW-M", "eps", True, RWD),
        ("bmw-m5", "BMW", "M5", "седан", "BMW-M", "eps", True, RWD),
        ("amg-c63", "Mercedes-AMG", "C63", "седан", "MB-AMG", "eps", True, RWD),
        ("amg-e63", "Mercedes-AMG", "E63", "седан", "MB-AMG", "eps", True, AWD),
        ("audi-rs6", "Audi", "RS6", "универсал", "AUDI-RS", "eps", True, AWD),
        ("nissan-gtr", "Nissan", "GT-R", "купе", "NIS-R35", "eps", True, AWD),
        ("toyota-supra", "Toyota", "Supra A90", "купе", "TOY-A90", "eps", True, RWD),
        ("corvette-c8", "Chevrolet", "Corvette C8", "купе", "GM-C8", "eps", True, RWD),
        ("porsche-911", "Porsche", "911 Carrera", "купе", "POR-992", "eps", True, RWD),
        ("dodge-hellcat", "Dodge", "Challenger Hellcat", "купе", "DODGE-LC", "eps", True, RWD),
        # Легендарные
        ("bugatti-chiron", "Bugatti", "Chiron", "купе", "HYPER-BUG", "eps", True, AWD),
        ("koenigsegg-jesko", "Koenigsegg", "Jesko", "купе", "HYPER-KOE", "eps", True, RWD),
        ("lamborghini-svj", "Lamborghini", "Aventador SVJ", "купе", "SUPER-LAM", "eps", True, AWD),
        ("ferrari-sf90", "Ferrari", "SF90 Stradale", "купе", "SUPER-FER", "eps", True, AWD),
        ("mclaren-p1", "McLaren", "P1", "купе", "HYPER-MCL", "eps", True, RWD),
    )
)
MODELS: dict[str, ModelInfo] = {m.model_id: m for m in _MODEL_LIST}


def _trim(
    model_id: str, engine: str, trans: str, first: int, last: int, factor: int,
    name: str | None = None, *, hp: int | None = None, chassis: str | None = None,
    steering: str | None = None, ac: bool | None = None, drive: DriveType | None = None,
) -> Trim:
    info = MODELS[model_id]
    spec: EngineSpec = ENGINES[engine]
    transmission = _TRANS[trans]
    if name is None:
        label = {"MT": "МКПП", "AT": "АКПП", "CVT": "вариатор", "AMT": "робот", "DCT": "DSG/DCT"}[trans]
        name = f"{spec.name} · {label} · {hp or spec.power_hp} л.с."
    return Trim(
        brand=info.brand,
        model=info.model,
        name=name,
        years=tuple(range(first, last + 1)),
        body_type=info.body_type,
        engine_code=engine,
        engine_volume_cc=spec.volume_cc,
        power_hp=hp or spec.power_hp,
        transmission=transmission,
        price_factor_pct=factor,
        fuel_type=spec.fuel_type,
        drive_type=drive or info.drive,
        model_id=model_id,
        chassis=chassis or info.chassis,
        steering=steering or info.steering,
        ac=info.ac if ac is None else ac,
        trans_tag=trans if trans in ("DCT",) else _TRANS_TAG[transmission],
    )


_T = _trim
FLEET: tuple[Trim, ...] = (
    # --- ВАЗ классика ---
    _T("vaz-2101", "2101", "MT", 1970, 1982, 62),
    _T("vaz-2101", "2105", "MT", 1979, 1988, 64),
    _T("vaz-2102", "2103", "MT", 1972, 1985, 66),
    _T("vaz-2103", "2103", "MT", 1972, 1984, 68),
    _T("vaz-2104", "2106", "MT", 1984, 2012, 70),
    _T("vaz-2105", "2105", "MT", 1980, 2010, 68),
    _T("vaz-2105", "2106", "MT", 1985, 2010, 70),
    _T("vaz-2106", "2106", "MT", 1976, 2006, 72),
    _T("vaz-2106", "2103", "MT", 1976, 1990, 70),
    _T("vaz-2107", "2105", "MT", 1982, 2012, 72),
    _T("vaz-2107", "2106", "MT", 1982, 2012, 74),
    # --- ВАЗ переднеприводные ---
    _T("vaz-2108", "2108", "MT", 1984, 2003, 70),
    _T("vaz-2108", "21083", "MT", 1987, 2003, 74),
    _T("vaz-2109", "21083", "MT", 1987, 2004, 74),
    _T("vaz-2109", "2111", "MT", 2000, 2004, 78),
    _T("vaz-21099", "21083", "MT", 1990, 2004, 74),
    _T("vaz-21099", "2111", "MT", 2000, 2004, 78),
    _T("vaz-2110", "2111", "MT", 1996, 2005, 78),
    _T("vaz-2110", "21114", "MT", 2005, 2007, 82),
    _T("vaz-2110", "21124", "MT", 2004, 2007, 88),
    _T("vaz-2111", "2111", "MT", 1998, 2009, 78),
    _T("vaz-2111", "21114", "MT", 2004, 2009, 82),
    _T("vaz-2112", "21124", "MT", 2002, 2008, 88),
    _T("vaz-2113", "2111", "MT", 2004, 2008, 78),
    _T("vaz-2113", "21114", "MT", 2008, 2013, 82),
    _T("vaz-2114", "2111", "MT", 2004, 2008, 80, "1.5 8V Стандарт"),
    _T("vaz-2114", "21114", "MT", 2008, 2012, 85, "1.6 8V Норма"),
    _T("vaz-2114", "21124", "MT", 2009, 2013, 95, "1.6 16V Люкс"),
    _T("vaz-2115", "2111", "MT", 1997, 2008, 78),
    _T("vaz-2115", "21114", "MT", 2005, 2012, 82),
    # --- LADA ---
    _T("lada-priora", "21126", "MT", 2007, 2015, 100),
    _T("lada-priora", "21126", "AMT", 2012, 2015, 108),
    _T("lada-priora", "11186", "MT", 2010, 2015, 96),
    _T("lada-kalina", "11183", "MT", 2004, 2013, 88),
    _T("lada-kalina", "21124", "MT", 2007, 2013, 96),
    _T("lada-kalina", "11186", "MT", 2013, 2018, 100, steering="eps", ac=True),
    _T("lada-kalina", "11189", "AT", 2013, 2018, 108, steering="eps", ac=True),
    _T("lada-granta", "11186", "MT", 2012, 2015, 100, "1.6 8V Стандарт"),
    _T("lada-granta", "11186", "AMT", 2016, 2019, 105, "1.6 8V Норма (робот)", steering="eps", ac=True),
    _T("lada-granta", "11189", "AT", 2015, 2018, 110, "1.6 8V Комфорт (автомат)", steering="eps", ac=True),
    _T("lada-granta", "21127", "MT", 2018, 2021, 115, "1.6 16V Люкс", steering="eps", ac=True),
    _T("lada-granta", "11186", "MT", 2018, 2023, 100, "1.6 8V Классик"),
    _T("lada-vesta", "21129", "MT", 2015, 2023, 125),
    _T("lada-vesta", "21129", "AMT", 2016, 2023, 132),
    _T("lada-vesta", "21179", "MT", 2018, 2023, 138),
    _T("lada-vesta", "21179", "AMT", 2018, 2023, 145),
    _T("lada-largus", "K7M", "MT", 2012, 2021, 112),
    _T("lada-largus", "K4M", "MT", 2012, 2023, 120),
    _T("lada-largus", "21129", "MT", 2021, 2023, 125),
    _T("lada-niva", "21213", "MT", 1994, 2006, 85),
    _T("lada-niva", "21214", "MT", 2006, 2023, 100),
    _T("chevrolet-niva", "2123", "MT", 2002, 2020, 110),
    # --- ГАЗ / УАЗ ---
    _T("gaz-3110", "ZMZ-402", "MT", 1997, 2004, 85),
    _T("gaz-3110", "ZMZ-4062", "MT", 1997, 2004, 100),
    _T("gaz-gazelle", "ZMZ-402", "MT", 1994, 2002, 95),
    _T("gaz-gazelle", "ZMZ-4216", "MT", 2003, 2023, 115),
    _T("gaz-gazelle", "ISF28", "MT", 2013, 2023, 135),
    _T("uaz-patriot", "ZMZ-409", "MT", 2005, 2023, 135),
    _T("uaz-patriot", "ZMZ-514", "MT", 2008, 2016, 145),
    # --- Renault ---
    _T("renault-logan", "K7M", "MT", 2005, 2014, 100),
    _T("renault-logan", "K4M", "MT", 2005, 2014, 110),
    _T("renault-logan", "H4M", "MT", 2014, 2022, 118),
    _T("renault-sandero", "K7M", "MT", 2009, 2014, 105),
    _T("renault-sandero", "K4M", "AT", 2010, 2014, 118),
    _T("renault-duster", "K4M", "MT", 2010, 2020, 140),
    _T("renault-duster", "F4R", "MT", 2010, 2020, 155, drive=AWD),
    _T("renault-duster", "F4R", "AT", 2012, 2020, 165, drive=AWD),
    _T("renault-duster", "K9K", "MT", 2011, 2020, 160, drive=AWD),
    # --- Hyundai / Kia ---
    _T("hyundai-solaris", "G4FA", "MT", 2011, 2015, 125, "Active 1.4"),
    _T("hyundai-solaris", "G4FA", "AT", 2011, 2016, 135, "Comfort 1.4 (автомат)"),
    _T("hyundai-solaris", "G4FC", "MT", 2012, 2016, 140, "Comfort 1.6"),
    _T("hyundai-solaris", "G4FC", "AT", 2013, 2017, 150, "Elegance 1.6 (автомат)"),
    _T("hyundai-creta", "G4FC", "MT", 2016, 2021, 165),
    _T("hyundai-creta", "G4FC", "AT", 2016, 2021, 175),
    _T("hyundai-creta", "G4NA", "AT", 2016, 2021, 190, drive=AWD),
    _T("hyundai-tucson", "G4NA", "AT", 2015, 2021, 195, drive=AWD),
    _T("hyundai-tucson", "G4KE", "AT", 2015, 2021, 205, drive=AWD),
    _T("kia-rio", "G4FA", "MT", 2011, 2017, 125),
    _T("kia-rio", "G4FA", "AT", 2011, 2017, 135),
    _T("kia-rio", "G4FC", "MT", 2011, 2017, 140),
    _T("kia-rio", "G4FC", "AT", 2011, 2017, 150),
    _T("kia-ceed", "G4FC", "MT", 2012, 2018, 150),
    _T("kia-ceed", "G4FC", "AT", 2012, 2018, 160),
    _T("kia-ceed", "G4NA", "AT", 2012, 2018, 170),
    _T("kia-sportage", "G4NA", "AT", 2015, 2021, 195, drive=AWD),
    _T("kia-sportage", "G4KE", "AT", 2015, 2021, 205, drive=AWD),
    # --- Volkswagen group ---
    _T("vw-polo", "CFNB", "MT", 2011, 2014, 125, "Trendline 1.6 85 л.с.", hp=85),
    _T("vw-polo", "CFNA", "MT", 2011, 2015, 135, "Comfortline 1.6 105 л.с."),
    _T("vw-polo", "CFNA", "AT", 2012, 2015, 145, "Comfortline 1.6 105 л.с. (автомат)"),
    _T("vw-polo", "CWVA", "AT", 2016, 2019, 155, "Highline 1.6 110 л.с. (автомат)"),
    _T("skoda-octavia", "BSE", "MT", 2004, 2013, 150),
    _T("skoda-octavia", "CWVA", "MT", 2013, 2020, 170, chassis="VW-MQB"),
    _T("skoda-octavia", "CWVA", "AT", 2013, 2020, 180, chassis="VW-MQB"),
    _T("skoda-octavia", "CDAB", "DCT", 2013, 2020, 200, chassis="VW-MQB"),
    _T("skoda-rapid", "CFNA", "MT", 2012, 2019, 135),
    _T("skoda-rapid", "CFNA", "AT", 2012, 2019, 145),
    _T("skoda-rapid", "CAXA", "DCT", 2014, 2019, 165),
    # --- Toyota / Nissan ---
    _T("toyota-corolla", "4ZZ-FE", "MT", 2007, 2010, 120, "1.4 Стандарт"),
    _T("toyota-corolla", "1ZR-FE", "MT", 2009, 2012, 135, "1.6 Комфорт"),
    _T("toyota-corolla", "1ZR-FE", "AMT", 2008, 2010, 140, "1.6 Комфорт (робот)"),
    _T("toyota-corolla", "2ZR-FE", "CVT", 2010, 2013, 160, "1.8 Престиж (вариатор)"),
    _T("toyota-corolla", "1ZR-FE", "CVT", 2013, 2018, 170, chassis="TOY-E180"),
    _T("toyota-corolla", "2ZR-FE", "CVT", 2014, 2018, 180, chassis="TOY-E180"),
    _T("toyota-camry", "2AZ-FE", "AT", 2006, 2011, 175),
    _T("toyota-camry", "2AR-FE", "AT", 2011, 2017, 195, chassis="TOY-XV50", steering="eps"),
    _T("toyota-rav4", "2AZ-FE", "AT", 2006, 2012, 190),
    _T("toyota-rav4", "2AR-FE", "AT", 2012, 2018, 210),
    _T("nissan-almera", "QG16", "MT", 2006, 2012, 115),
    _T("nissan-almera", "QG16", "AT", 2006, 2012, 125),
    _T("nissan-almera", "K4M", "MT", 2013, 2018, 130, chassis="NIS-G15", steering="eps"),
    _T("nissan-almera", "K4M", "AT", 2013, 2018, 140, chassis="NIS-G15", steering="eps"),
    _T("nissan-qashqai", "HR16DE", "MT", 2007, 2013, 160),
    _T("nissan-qashqai", "MR20DE", "CVT", 2007, 2013, 180, drive=AWD),
    _T("nissan-qashqai", "HR16DE", "CVT", 2014, 2021, 185, chassis="NIS-J11"),
    # --- Ford / GM / Daewoo / Opel / Suzuki ---
    _T("ford-focus", "HWDA", "MT", 2005, 2011, 120),
    _T("ford-focus", "HWDA", "AT", 2005, 2011, 130),
    _T("ford-focus", "QQDB", "MT", 2005, 2011, 135),
    _T("ford-focus", "IQDB", "MT", 2011, 2019, 150, chassis="FORD-FOC3", steering="eps"),
    _T("ford-focus", "IQDB", "DCT", 2011, 2019, 160, chassis="FORD-FOC3", steering="eps"),
    _T("chevrolet-lacetti", "F14D3", "MT", 2004, 2013, 105),
    _T("chevrolet-lacetti", "F16D3", "MT", 2004, 2013, 112),
    _T("chevrolet-lacetti", "F16D3", "AT", 2004, 2013, 120),
    _T("chevrolet-lacetti", "F18D3", "AT", 2004, 2013, 128),
    _T("chevrolet-cobalt", "B15D2", "MT", 2011, 2020, 115),
    _T("chevrolet-cobalt", "B15D2", "AT", 2011, 2020, 125),
    _T("daewoo-nexia", "A15SMS", "MT", 1995, 2016, 75),
    _T("daewoo-matiz", "F8CV", "MT", 1998, 2015, 60),
    _T("daewoo-matiz", "B10S1", "MT", 2005, 2015, 65),
    _T("daewoo-matiz", "B10S1", "AT", 2006, 2015, 72),
    _T("opel-astra", "A16XER", "MT", 2009, 2015, 140),
    _T("opel-astra", "A16XER", "AT", 2009, 2015, 150),
    _T("suzuki-grand-vitara", "M16A", "MT", 2005, 2016, 150),
    _T("suzuki-grand-vitara", "J24B", "AT", 2008, 2016, 170),
    # --- Mazda / Mitsubishi / Honda ---
    _T("mazda-3", "Z6", "MT", 2003, 2013, 140),
    _T("mazda-3", "LF-VE", "AT", 2003, 2013, 155),
    _T("mazda-3", "PE-VPS", "MT", 2013, 2019, 175, chassis="MAZDA-3BM", steering="eps"),
    _T("mazda-3", "PE-VPS", "AT", 2013, 2019, 185, chassis="MAZDA-3BM", steering="eps"),
    _T("mazda-6", "LF-VE", "MT", 2002, 2012, 160),
    _T("mazda-6", "L5-VE", "AT", 2008, 2012, 180),
    _T("mazda-6", "PE-VPS", "AT", 2012, 2018, 200, chassis="MAZDA-6GJ", steering="eps"),
    _T("mazda-cx5", "PE-VPS", "AT", 2012, 2017, 210),
    _T("mitsubishi-lancer", "4A91", "MT", 2007, 2015, 135),
    _T("mitsubishi-lancer", "4B11", "MT", 2007, 2015, 155),
    _T("mitsubishi-lancer", "4B11", "CVT", 2008, 2015, 165),
    _T("mitsubishi-outlander", "4B11", "CVT", 2012, 2021, 195),
    _T("mitsubishi-outlander", "4B12", "CVT", 2012, 2021, 205),
    _T("honda-civic", "R18A", "MT", 2006, 2011, 150),
    _T("honda-civic", "R18A", "AT", 2006, 2011, 160),
    _T("honda-civic", "R18A", "AT", 2012, 2015, 170, chassis="HON-CIVIC9", steering="eps"),
    _T("honda-crv", "R20A", "AT", 2007, 2012, 190),
    _T("honda-crv", "K24Z", "AT", 2012, 2017, 215),
    # --- Китай ---
    _T("chery-tiggo", "SQR481FC", "MT", 2008, 2016, 120),
    _T("chery-tiggo", "SQR484F", "MT", 2008, 2016, 130),
    _T("chery-tiggo", "SQR484F", "AT", 2008, 2016, 140),
    _T("chery-tiggo7pro", "SQRE4T15C", "CVT", 2020, 2024, 175),
    _T("chery-tiggo7pro", "SQRE4T15C", "DCT", 2020, 2024, 180),
    _T("geely-coolray", "JLH-3G15TD", "DCT", 2019, 2024, 175),
    _T("geely-emgrand", "JL-4G15", "MT", 2009, 2018, 105),
    _T("geely-emgrand", "JL-4G18", "MT", 2009, 2018, 115),
    _T("geely-emgrand", "JL-4G18", "CVT", 2013, 2018, 125),
    _T("haval-jolion", "GW4B15A", "MT", 2021, 2024, 170),
    _T("haval-jolion", "GW4B15A", "DCT", 2021, 2024, 180),
    _T("haval-h6", "GW4C20", "AT", 2017, 2023, 210),
    _T("haval-h6", "GW4B15A", "DCT", 2019, 2023, 190),
    _T("changan-cs55", "JL473ZQ2", "AT", 2018, 2024, 165),
    _T("changan-cs55", "JL473ZQ2", "DCT", 2021, 2024, 175),
    # --- Ford / Chevrolet / VW массовые ---
    _T("ford-fiesta", "HWDA", "MT", 2008, 2017, 115),
    _T("ford-fiesta", "IQDB", "AT", 2008, 2017, 125, hp=105),
    _T("chevrolet-cruze", "F16D4", "MT", 2009, 2015, 125),
    _T("chevrolet-cruze", "F18D4", "AT", 2009, 2015, 138),
    _T("vw-golf", "CAXA", "DCT", 2009, 2013, 175),
    _T("vw-golf", "CDAB", "DCT", 2009, 2013, 190),
    _T("vw-golf", "BSE", "MT", 2004, 2009, 150),
    # --- премиум ---
    _T("bmw-3", "N46B20", "MT", 2005, 2011, 330),
    _T("bmw-3", "N20B20", "AT", 2011, 2018, 380),
    _T("bmw-3", "B58B30", "AT", 2015, 2022, 450),
    _T("bmw-5", "N52B25", "AT", 2003, 2010, 380, chassis="BMW-E60"),
    _T("bmw-5", "N55B30", "AT", 2010, 2016, 480),
    _T("mb-c", "M271", "AT", 2007, 2014, 340),
    _T("mb-c", "M274", "AT", 2014, 2021, 400),
    _T("mb-e", "M272", "AT", 2009, 2016, 420),
    _T("mb-e", "OM651", "AT", 2011, 2016, 440),
    _T("audi-a4", "CDNB", "CVT", 2007, 2015, 330),
    _T("audi-a4", "CDNB", "DCT", 2012, 2018, 360),
    _T("audi-a6", "CGXB", "DCT", 2011, 2018, 450),
    _T("audi-a6", "CDNB", "CVT", 2011, 2018, 400),
    _T("toyota-prado", "2TR-FE", "AT", 2009, 2023, 380),
    _T("toyota-prado", "1GR-FE", "AT", 2009, 2023, 430),
    _T("toyota-prado", "1KD-FTV", "AT", 2009, 2015, 420),
    _T("lexus-rx", "2GR-FE", "AT", 2009, 2015, 460),
    _T("lexus-rx", "1AR-FE", "AT", 2009, 2015, 400),
    _T("volvo-xc60", "D5244T", "AT", 2008, 2017, 400),
    _T("volvo-xc60", "B6304T", "AT", 2010, 2017, 440),
    _T("subaru-wrx", "EJ205", "MT", 2001, 2014, 380),
    _T("subaru-wrx", "EJ257", "MT", 2004, 2014, 440, "WRX STI 2.5 Turbo"),
    _T("mitsubishi-evo", "4G63T", "MT", 2005, 2007, 520, "Evolution IX"),
    _T("mitsubishi-evo", "4B11T", "MT", 2008, 2015, 560, "Evolution X"),
    _T("vw-touareg", "BHK", "AT", 2010, 2018, 440),
    _T("vw-touareg", "CASA", "AT", 2010, 2018, 470),
    _T("jeep-grand-cherokee", "ERB", "AT", 2011, 2021, 430),
    _T("jeep-grand-cherokee", "EZH", "AT", 2011, 2021, 480),
    _T("ford-mustang", "COYOTE50", "MT", 2011, 2023, 470),
    _T("ford-mustang", "ECOBOOST23", "AT", 2015, 2023, 440),
    # --- эпические ---
    _T("bmw-m3", "S54B32", "MT", 2000, 2006, 700, chassis="BMW-E46M"),
    _T("bmw-m3", "S65B40", "DCT", 2007, 2013, 800, chassis="BMW-E9XM"),
    _T("bmw-m3", "S55B30", "DCT", 2014, 2018, 850),
    _T("bmw-m5", "S85B50", "AMT", 2005, 2010, 900),
    _T("bmw-m5", "S63B44", "DCT", 2011, 2023, 950),
    _T("amg-c63", "M156", "AT", 2008, 2014, 800),
    _T("amg-c63", "M177", "AT", 2015, 2023, 900),
    _T("amg-e63", "M156", "AT", 2009, 2013, 880),
    _T("amg-e63", "M177", "AT", 2017, 2023, 980),
    _T("audi-rs6", "BUH", "AT", 2008, 2010, 950),
    _T("audi-rs6", "CRDB", "AT", 2013, 2023, 1000),
    _T("nissan-gtr", "VR38DETT", "DCT", 2008, 2023, 1100),
    _T("toyota-supra", "B58B30", "AT", 2019, 2024, 800),
    _T("corvette-c8", "LT2", "DCT", 2020, 2024, 1000),
    _T("porsche-911", "9A2", "DCT", 2016, 2024, 1100),
    _T("dodge-hellcat", "HELLCAT62", "AT", 2015, 2023, 900),
    # --- легендарные ---
    _T("bugatti-chiron", "W16", "DCT", 2017, 2024, 3000),
    _T("koenigsegg-jesko", "JESKO50", "AMT", 2021, 2024, 3200),
    _T("lamborghini-svj", "L539", "AMT", 2019, 2022, 2200),
    _T("ferrari-sf90", "F154FA", "DCT", 2020, 2024, 2400),
    _T("mclaren-p1", "M838TQ", "DCT", 2014, 2016, 2800),
)

# --- контроль целостности при импорте ----------------------------------------
_ids = [t.catalog_id for t in FLEET]
if len(set(_ids)) != len(_ids):
    raise RuntimeError("catalog_id комплектаций должен быть уникальным")
del _ids

TRIMS_BY_ID: dict[str, Trim] = {t.catalog_id: t for t in FLEET}


def resolve_trim(brand: str, model: str, engine_code: str, transmission: Transmission) -> Trim | None:
    """Находит комплектацию по данным конфигурации автомобиля (с запасными вариантами)."""
    same_model = [t for t in FLEET if t.brand == brand and t.model == model]
    for predicate in (
        lambda t: t.engine_code == engine_code and t.transmission == transmission,
        lambda t: t.engine_code == engine_code,
    ):
        found = [t for t in same_model if predicate(t)]
        if found:
            return found[0]
    return same_model[0] if same_model else None


def tags_for_configuration(
    brand: str, model: str, engine_code: str, transmission: Transmission, volume_cc: int | None = None
) -> Tags:
    """Теги совместимости автомобиля. Для неизвестной модели — безопасные общие значения."""
    trim = resolve_trim(brand, model, engine_code, transmission)
    if trim is not None and trim.engine_code == engine_code:
        return trim.tags
    chassis = trim.chassis if trim is not None else "GENERIC"
    steering = trim.steering if trim is not None else "hyd"
    ac = trim.ac if trim is not None else True
    return build_tags(
        engine_code, _TRANS_TAG[transmission], chassis, steering, ac, volume_cc=volume_cc
    )
