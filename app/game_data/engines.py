"""Справочник двигателей: от них зависят свечи, ГРМ, зажигание и применимые неисправности.

Значения игровые и приближённые (не заводские данные). Теги двигателя определяют, какие
детали подходят автомобилю и какие неисправности на нём возможны.
"""

from dataclasses import dataclass

from app.game_data.enums import FuelType

CARB = "carb"  # карбюратор, электронного блока управления нет
MPI = "mpi"  # распределённый впрыск
GDI = "gdi"  # непосредственный впрыск
DIESEL = "diesel"

DISTRIBUTOR = "distributor"  # трамблёр
MODULE = "module"  # модуль зажигания на все цилиндры + провода
COIL = "coil"  # катушка на каждой свече
GLOW = "glow"  # дизель: свечи накала

BELT = "belt"
CHAIN = "chain"


@dataclass(frozen=True, slots=True)
class EngineSpec:
    code: str
    name: str
    volume_cc: int
    power_hp: int
    fuel_type: FuelType
    injection: str
    ignition: str
    timing: str
    turbo: bool
    plug: str  # группа свечей (для совместимости деталей)
    plug_gap_mm: float
    cylinders: int
    fuel_bar: float  # рабочее давление питания (для карбюратора — давление насоса)
    compression_bar: float

    @property
    def has_ecu(self) -> bool:
        return self.injection != CARB


def _e(
    code: str, name: str, cc: int, hp: int, injection: str, ignition: str, timing: str,
    plug: str, gap: float, *, fuel: FuelType = FuelType.PETROL, turbo: bool = False,
    cyl: int = 4, bar: float | None = None, comp: float | None = None,
) -> EngineSpec:
    default_bar = {CARB: 0.3, MPI: 3.5, GDI: 5.0, DIESEL: 4.5}[injection]
    if comp is None:
        comp = 28.0 if injection == DIESEL else (10.5 if turbo else 12.0)
    return EngineSpec(
        code, name, cc, hp, fuel, injection, ignition, timing, turbo, plug, gap, cyl,
        bar if bar is not None else default_bar, comp,
    )


_ENGINE_LIST: tuple[EngineSpec, ...] = (
    # ВАЗ классика (цепь ГРМ, карбюратор, трамблёр)
    _e("2101", "1.2 карб.", 1198, 64, CARB, DISTRIBUTOR, CHAIN, "P-VAZ-CL", 0.7, comp=10.5),
    _e("2103", "1.5 карб.", 1452, 71, CARB, DISTRIBUTOR, CHAIN, "P-VAZ-CL", 0.7, comp=11.0),
    _e("2105", "1.3 карб.", 1294, 64, CARB, DISTRIBUTOR, CHAIN, "P-VAZ-CL", 0.7, comp=10.5),
    _e("2106", "1.6 карб.", 1569, 75, CARB, DISTRIBUTOR, CHAIN, "P-VAZ-CL", 0.7, comp=11.0),
    _e("21213", "1.7 карб. (Нива)", 1690, 79, CARB, DISTRIBUTOR, CHAIN, "P-VAZ-CL", 0.7, comp=11.0),
    _e("21214", "1.7 впрыск (Нива)", 1690, 83, MPI, MODULE, CHAIN, "P-VAZ-8V", 1.0, comp=11.5, bar=3.0),
    _e("2123", "1.7 впрыск (Шевроле Нива)", 1690, 80, MPI, MODULE, CHAIN, "P-VAZ-8V", 1.0, comp=11.5, bar=3.0),
    # ВАЗ переднеприводные (ремень ГРМ)
    _e("2108", "1.3 карб.", 1288, 64, CARB, DISTRIBUTOR, BELT, "P-VAZ-CL", 0.7, comp=10.5),
    _e("21083", "1.5 карб.", 1499, 72, CARB, DISTRIBUTOR, BELT, "P-VAZ-CL", 0.7, comp=11.0),
    _e("2111", "1.5 8V", 1499, 78, MPI, MODULE, BELT, "P-VAZ-8V", 1.0, bar=3.0, comp=11.5),
    _e("21114", "1.6 8V", 1596, 81, MPI, MODULE, BELT, "P-VAZ-8V", 1.0, bar=3.0, comp=11.5),
    _e("21124", "1.6 16V", 1599, 89, MPI, MODULE, BELT, "P-VAZ-16V", 1.1, bar=3.0, comp=12.0),
    _e("21126", "1.6 16V (Приора)", 1597, 98, MPI, MODULE, BELT, "P-VAZ-16V", 1.1, bar=3.0, comp=12.0),
    _e("11183", "1.6 8V (Калина)", 1596, 81, MPI, MODULE, BELT, "P-VAZ-8V", 1.0, bar=3.0, comp=11.5),
    _e("11186", "1.6 8V (Гранта)", 1596, 87, MPI, MODULE, BELT, "P-VAZ-8V", 1.0, bar=3.0, comp=11.5),
    _e("11189", "1.6 8V 98 л.с.", 1596, 98, MPI, MODULE, BELT, "P-VAZ-8V", 1.0, bar=3.0, comp=11.5),
    _e("21127", "1.6 16V 106 л.с.", 1596, 106, MPI, MODULE, BELT, "P-VAZ-16V", 1.1, bar=3.0, comp=12.0),
    _e("21129", "1.6 16V (Веста)", 1596, 106, MPI, MODULE, BELT, "P-VAZ-16V", 1.1, bar=3.0, comp=12.0),
    _e("21179", "1.8 16V (Веста)", 1774, 122, MPI, MODULE, BELT, "P-VAZ-16V", 1.1, bar=3.0, comp=12.0),
    # Renault / Nissan
    _e("K7M", "1.6 8V", 1598, 84, MPI, MODULE, BELT, "P-REN-8V", 0.9, bar=3.5, comp=11.5),
    _e("K4M", "1.6 16V", 1598, 102, MPI, COIL, BELT, "P-REN-16V", 1.0, bar=3.5, comp=12.5),
    _e("H4M", "1.6 16V", 1598, 114, MPI, COIL, CHAIN, "P-REN-16V", 1.0, bar=3.5, comp=12.5),
    _e("F4R", "2.0 16V", 1998, 135, MPI, COIL, BELT, "P-REN-16V", 1.0, bar=3.5, comp=12.5),
    _e("K9K", "1.5 dCi", 1461, 90, DIESEL, GLOW, BELT, "GLOW-K9K", 0.0, fuel=FuelType.DIESEL),
    _e("QG16", "1.6 16V", 1596, 107, MPI, COIL, CHAIN, "P-NIS-16V", 1.1, bar=3.5, comp=12.5),
    _e("HR16DE", "1.6 16V", 1598, 117, MPI, COIL, CHAIN, "P-NIS-16V", 1.1, bar=3.5, comp=12.5),
    _e("MR20DE", "2.0 16V", 1997, 141, MPI, COIL, CHAIN, "P-NIS-16V", 1.1, bar=3.5, comp=12.5),
    _e("QR25DE", "2.5 16V", 2488, 169, MPI, COIL, CHAIN, "P-NIS-16V", 1.1, bar=3.5, comp=12.5),
    # Hyundai / Kia
    _e("G4FA", "1.4 16V", 1396, 107, MPI, COIL, CHAIN, "P-HK-14", 1.0, bar=3.8, comp=12.5),
    _e("G4FC", "1.6 16V", 1591, 123, MPI, COIL, CHAIN, "P-HK-16", 1.0, bar=3.8, comp=12.5),
    _e("G4NA", "2.0 16V", 1999, 150, MPI, COIL, CHAIN, "P-HK-20", 1.0, bar=3.8, comp=12.5),
    _e("G4KE", "2.4 16V", 2359, 175, MPI, COIL, CHAIN, "P-HK-24", 1.0, bar=3.8, comp=12.5),
    # Volkswagen group
    _e("BSE", "1.6 8V", 1595, 102, MPI, COIL, BELT, "P-VW-16", 0.8, bar=3.7, comp=12.0),
    _e("CFNB", "1.6 8V", 1598, 85, MPI, COIL, BELT, "P-VW-16", 0.8, bar=3.7, comp=11.5),
    _e("CFNA", "1.6 16V", 1598, 105, MPI, COIL, BELT, "P-VW-16", 0.8, bar=3.7, comp=12.0),
    _e("CWVA", "1.6 16V", 1598, 110, MPI, COIL, BELT, "P-VW-16", 0.8, bar=3.7, comp=12.0),
    _e("CDAB", "1.8 TSI", 1798, 152, GDI, COIL, CHAIN, "P-VW-TSI", 0.7, turbo=True, comp=10.5),
    _e("CAXA", "1.4 TSI", 1390, 122, GDI, COIL, CHAIN, "P-VW-TSI", 0.7, turbo=True, comp=10.5),
    # Toyota
    _e("4ZZ-FE", "1.4 16V", 1398, 97, MPI, COIL, CHAIN, "P-TOY", 1.1, bar=3.4, comp=12.5),
    _e("1ZR-FE", "1.6 16V", 1598, 124, MPI, COIL, CHAIN, "P-TOY", 1.1, bar=3.4, comp=12.5),
    _e("2ZR-FE", "1.8 16V", 1798, 140, MPI, COIL, CHAIN, "P-TOY", 1.1, bar=3.4, comp=12.5),
    _e("2AZ-FE", "2.4 16V", 2362, 167, MPI, COIL, CHAIN, "P-TOY", 1.1, bar=3.4, comp=12.5),
    _e("2AR-FE", "2.5 16V", 2494, 181, MPI, COIL, CHAIN, "P-TOY", 1.1, bar=3.4, comp=12.5),
    # Ford / Chevrolet / Daewoo / Opel / Suzuki
    _e("HWDA", "1.6 16V", 1596, 100, MPI, COIL, BELT, "P-FORD", 1.3, bar=3.8, comp=12.0),
    _e("QQDB", "1.8 16V", 1798, 125, MPI, COIL, BELT, "P-FORD", 1.3, bar=3.8, comp=12.0),
    _e("IQDB", "1.6 Ti-VCT", 1596, 125, MPI, COIL, CHAIN, "P-FORD", 1.3, bar=3.8, comp=12.0),
    _e("F14D3", "1.4 16V", 1399, 95, MPI, COIL, BELT, "P-GM-16", 1.0, bar=3.5, comp=12.0),
    _e("F16D3", "1.6 16V", 1598, 109, MPI, COIL, BELT, "P-GM-16", 1.0, bar=3.5, comp=12.0),
    _e("F18D3", "1.8 16V", 1796, 122, MPI, COIL, BELT, "P-GM-16", 1.0, bar=3.5, comp=12.0),
    _e("B15D2", "1.5 16V", 1485, 105, MPI, COIL, BELT, "P-GM-16", 1.0, bar=3.5, comp=12.0),
    _e("A15SMS", "1.5 8V", 1498, 80, MPI, MODULE, BELT, "P-DAEWOO", 0.9, bar=3.0, comp=11.5),
    _e("F8CV", "0.8 6V", 796, 52, MPI, MODULE, BELT, "P-DAEWOO", 0.8, cyl=3, bar=3.0, comp=11.0),
    _e("B10S1", "1.0 6V", 995, 63, MPI, MODULE, BELT, "P-DAEWOO", 0.8, cyl=3, bar=3.0, comp=11.5),
    _e("A16XER", "1.6 16V", 1598, 115, MPI, COIL, CHAIN, "P-GM-16", 1.0, bar=3.5, comp=12.5),
    _e("M16A", "1.6 16V", 1586, 106, MPI, COIL, CHAIN, "P-SUZ", 0.9, bar=3.4, comp=12.5),
    _e("J24B", "2.4 16V", 2393, 166, MPI, COIL, CHAIN, "P-SUZ", 0.9, bar=3.4, comp=12.5),
    # Mazda / Mitsubishi / Honda
    _e("Z6", "1.6 16V", 1598, 105, MPI, COIL, BELT, "P-MAZ", 1.1, bar=3.5, comp=12.5),
    _e("LF-VE", "2.0 16V", 1999, 150, MPI, COIL, CHAIN, "P-MAZ", 1.1, bar=3.5, comp=12.5),
    _e("PE-VPS", "2.0 SkyActiv", 1998, 150, GDI, COIL, CHAIN, "P-MAZ", 0.8, comp=14.0),
    _e("L5-VE", "2.5 16V", 2488, 170, MPI, COIL, CHAIN, "P-MAZ", 1.1, bar=3.5, comp=12.5),
    _e("4A91", "1.5 16V", 1499, 109, MPI, COIL, CHAIN, "P-MIT", 1.0, bar=3.5, comp=12.5),
    _e("4B11", "2.0 16V", 1998, 150, MPI, COIL, CHAIN, "P-MIT", 1.0, bar=3.5, comp=12.5),
    _e("4B12", "2.4 16V", 2359, 170, MPI, COIL, CHAIN, "P-MIT", 1.0, bar=3.5, comp=12.5),
    _e("R18A", "1.8 16V", 1799, 140, MPI, COIL, CHAIN, "P-HON", 1.0, bar=3.5, comp=12.5),
    _e("R20A", "2.0 16V", 1997, 150, MPI, COIL, CHAIN, "P-HON", 1.0, bar=3.5, comp=12.5),
    _e("K24Z", "2.4 16V", 2354, 190, MPI, COIL, CHAIN, "P-HON", 1.0, bar=3.5, comp=12.5),
    # Китай
    _e("SQR481FC", "1.8 16V", 1799, 132, MPI, COIL, CHAIN, "P-CHERY", 0.9, bar=3.5, comp=12.0),
    _e("SQR484F", "2.0 16V", 1971, 136, MPI, COIL, CHAIN, "P-CHERY", 0.9, bar=3.5, comp=12.0),
    _e("SQRE4T15C", "1.5 Turbo", 1498, 147, GDI, COIL, CHAIN, "P-CHERY-T", 0.7, turbo=True, comp=10.5),
    _e("JLH-3G15TD", "1.5 Turbo (3 цил.)", 1477, 150, GDI, COIL, CHAIN, "P-GEELY-T", 0.7,
       turbo=True, cyl=3, comp=10.5),
    _e("JL-4G18", "1.8 16V", 1792, 126, MPI, COIL, CHAIN, "P-GEELY", 0.9, bar=3.5, comp=12.0),
    _e("JL-4G15", "1.5 16V", 1497, 94, MPI, COIL, CHAIN, "P-GEELY", 0.9, bar=3.5, comp=12.0),
    _e("GW4B15A", "1.5 Turbo", 1497, 143, GDI, COIL, CHAIN, "P-HAVAL-T", 0.7, turbo=True, comp=10.5),
    _e("GW4C20", "2.0 Turbo", 1967, 190, GDI, COIL, CHAIN, "P-HAVAL-T", 0.7, turbo=True, comp=10.5),
    _e("JL473ZQ2", "1.5 Turbo", 1499, 143, GDI, COIL, CHAIN, "P-CHANGAN-T", 0.7, turbo=True, comp=10.5),
    _e("JL478QEE", "1.6 16V", 1597, 113, MPI, COIL, CHAIN, "P-CHANGAN", 0.9, bar=3.5, comp=12.0),
    # ГАЗ / УАЗ
    _e("ZMZ-402", "2.4 карб.", 2445, 100, CARB, DISTRIBUTOR, CHAIN, "P-ZMZ", 0.8, comp=9.5),
    _e("ZMZ-4062", "2.3 16V", 2287, 150, MPI, MODULE, CHAIN, "P-ZMZ", 0.8, bar=3.0, comp=11.5),
    _e("ZMZ-4216", "2.9 16V", 2890, 106, MPI, COIL, CHAIN, "P-ZMZ", 0.8, bar=3.0, comp=10.5),
    _e("ZMZ-409", "2.7 16V", 2693, 128, MPI, MODULE, CHAIN, "P-ZMZ", 0.8, bar=3.0, comp=10.5),
    _e("ZMZ-514", "2.2 диз.", 2235, 114, DIESEL, GLOW, BELT, "GLOW-ZMZ", 0.0, fuel=FuelType.DIESEL),
    _e("ISF28", "2.8 Cummins диз.", 2776, 120, DIESEL, GLOW, CHAIN, "GLOW-ISF", 0.0, fuel=FuelType.DIESEL),
    # --- GM (Cruze) ---
    _e("F16D4", "1.6 16V", 1598, 124, MPI, COIL, BELT, "P-GM-F", 1.1),
    _e("F18D4", "1.8 16V", 1796, 141, MPI, COIL, BELT, "P-GM-F", 1.1),
    # --- BMW / Mini-класс премиум ---
    _e("N46B20", "2.0 Valvetronic", 1995, 150, MPI, COIL, CHAIN, "P-BMW-N", 0.8),
    _e("N52B25", "2.5 R6", 2497, 218, MPI, COIL, CHAIN, "P-BMW-N", 0.8, cyl=6),
    _e("N20B20", "2.0 Turbo", 1997, 184, GDI, COIL, CHAIN, "P-BMW-T", 0.7, turbo=True),
    _e("N55B30", "3.0 R6 Turbo", 2979, 306, GDI, COIL, CHAIN, "P-BMW-T", 0.7, turbo=True, cyl=6),
    _e("B58B30", "3.0 R6 Turbo", 2998, 340, GDI, COIL, CHAIN, "P-BMW-T", 0.7, turbo=True, cyl=6),
    _e("S54B32", "3.2 R6 M", 3246, 343, MPI, COIL, CHAIN, "P-BMW-M", 0.7, cyl=6, comp=12.5),
    _e("S65B40", "4.0 V8 M", 3999, 420, MPI, COIL, CHAIN, "P-BMW-M", 0.7, cyl=8, comp=12.5),
    _e("S55B30", "3.0 R6 Twin Turbo M", 2979, 431, GDI, COIL, CHAIN, "P-BMW-T", 0.7, turbo=True, cyl=6),
    _e("S85B50", "5.0 V10 M", 4999, 507, MPI, COIL, CHAIN, "P-BMW-M", 0.7, cyl=10, comp=12.5),
    _e("S63B44", "4.4 V8 Twin Turbo M", 4395, 560, GDI, COIL, CHAIN, "P-BMW-T", 0.7, turbo=True, cyl=8),
    # --- Mercedes-Benz / AMG ---
    _e("M271", "1.8 Kompressor", 1796, 184, MPI, COIL, CHAIN, "P-MB-M", 0.8, turbo=True),
    _e("M272", "3.5 V6", 3498, 272, MPI, COIL, CHAIN, "P-MB-M", 0.8, cyl=6),
    _e("M274", "2.0 Turbo", 1991, 211, GDI, COIL, CHAIN, "P-MB-T", 0.7, turbo=True),
    _e("OM651", "2.1 Diesel", 2143, 170, DIESEL, GLOW, CHAIN, "GLOW-MB", 0.0, fuel=FuelType.DIESEL, turbo=True),
    _e("M156", "6.2 V8 AMG", 6208, 457, MPI, COIL, CHAIN, "P-MB-AMG", 0.7, cyl=8, comp=11.5),
    _e("M177", "4.0 V8 Biturbo AMG", 3982, 510, GDI, COIL, CHAIN, "P-MB-AMG", 0.7, turbo=True, cyl=8),
    # --- Audi ---
    _e("CDNB", "2.0 TFSI", 1984, 211, GDI, COIL, CHAIN, "P-AUDI-T", 0.7, turbo=True),
    _e("CGXB", "3.0 TFSI V6", 2995, 300, GDI, COIL, CHAIN, "P-AUDI-T", 0.7, turbo=True, cyl=6),
    _e("BUH", "5.0 V10 Biturbo", 4991, 580, GDI, COIL, CHAIN, "P-AUDI-T", 0.7, turbo=True, cyl=10),
    _e("CRDB", "4.0 V8 TFSI Biturbo", 3993, 560, GDI, COIL, CHAIN, "P-AUDI-T", 0.7, turbo=True, cyl=8),
    # --- Toyota / Lexus ---
    _e("2TR-FE", "2.7 16V", 2694, 163, MPI, COIL, CHAIN, "P-TOY-2TR", 1.0),
    _e("1AR-FE", "2.7 16V (RX)", 2672, 182, MPI, COIL, CHAIN, "P-TOY-AR", 1.0),
    _e("1GR-FE", "4.0 V6", 3956, 249, MPI, COIL, CHAIN, "P-TOY-V6", 1.0, cyl=6),
    _e("1KD-FTV", "3.0 D-4D", 2982, 173, DIESEL, GLOW, CHAIN, "GLOW-TOY", 0.0, fuel=FuelType.DIESEL, turbo=True),
    _e("2GR-FE", "3.5 V6", 3456, 277, MPI, COIL, CHAIN, "P-TOY-V6", 1.0, cyl=6),
    # --- Volvo / Subaru / Mitsubishi ---
    _e("B6304T", "3.0 T6", 2953, 304, GDI, COIL, CHAIN, "P-VOLVO-T", 0.7, turbo=True, cyl=6),
    _e("D5244T", "2.4 D5", 2400, 215, DIESEL, GLOW, BELT, "GLOW-VOLVO", 0.0, fuel=FuelType.DIESEL, turbo=True, cyl=5),
    _e("EJ205", "2.0 Turbo (WRX)", 1994, 227, MPI, COIL, BELT, "P-SUB-T", 0.7, turbo=True),
    _e("EJ257", "2.5 Turbo (STI)", 2457, 300, MPI, COIL, BELT, "P-SUB-T", 0.7, turbo=True),
    _e("4G63T", "2.0 Turbo (Evo IX)", 1997, 280, MPI, COIL, BELT, "P-MIT-T", 0.7, turbo=True),
    _e("4B11T", "2.0 Turbo (Evo X)", 1998, 295, MPI, COIL, CHAIN, "P-MIT-T", 0.7, turbo=True),
    # --- Volkswagen Touareg / Jeep / Ford ---
    _e("BHK", "3.6 V6 FSI", 3597, 280, GDI, COIL, CHAIN, "P-VW-V6", 0.8, cyl=6),
    _e("CASA", "3.0 V6 TDI", 2967, 240, DIESEL, GLOW, CHAIN, "GLOW-VW", 0.0, fuel=FuelType.DIESEL, turbo=True, cyl=6),
    _e("ERB", "3.6 Pentastar V6", 3604, 286, MPI, COIL, CHAIN, "P-CHR-V6", 0.9, cyl=6),
    _e("EZH", "5.7 HEMI V8", 5654, 352, MPI, COIL, CHAIN, "P-CHR-V8", 0.9, cyl=8, comp=10.5),
    _e("COYOTE50", "5.0 V8 Coyote", 4951, 421, MPI, COIL, CHAIN, "P-FORD-V8", 0.9, cyl=8, comp=12.0),
    _e("ECOBOOST23", "2.3 EcoBoost", 2261, 317, GDI, COIL, CHAIN, "P-FORD-T", 0.7, turbo=True),
    # --- суперкары и гиперкары ---
    _e("VR38DETT", "3.8 V6 Twin Turbo", 3799, 570, GDI, COIL, CHAIN, "P-NIS-GTR", 0.7, turbo=True, cyl=6),
    _e("LT2", "6.2 V8 (C8)", 6162, 495, GDI, COIL, CHAIN, "P-GM-V8", 0.8, cyl=8, comp=11.5),
    _e("9A2", "3.0 Flat-6 Twin Turbo", 2981, 385, GDI, COIL, CHAIN, "P-POR-T", 0.7, turbo=True, cyl=6),
    _e("HELLCAT62", "6.2 V8 Supercharged", 6166, 717, MPI, COIL, CHAIN, "P-CHR-V8", 0.8, turbo=True, cyl=8),
    _e("W16", "8.0 W16 Quad Turbo", 7993, 1500, GDI, COIL, CHAIN, "P-BUG-W16", 0.6, turbo=True, cyl=16),
    _e("JESKO50", "5.0 V8 Twin Turbo", 5000, 1280, GDI, COIL, CHAIN, "P-KOE-V8", 0.6, turbo=True, cyl=8),
    _e("L539", "6.5 V12", 6498, 770, GDI, COIL, CHAIN, "P-LAM-V12", 0.7, cyl=12, comp=12.5),
    _e("F154FA", "4.0 V8 Twin Turbo Hybrid", 3990, 780, GDI, COIL, CHAIN, "P-FER-V8", 0.6, turbo=True, cyl=8),
    _e("M838TQ", "3.8 V8 Twin Turbo Hybrid", 3799, 737, GDI, COIL, CHAIN, "P-MCL-V8", 0.6, turbo=True, cyl=8),
)

ENGINES: dict[str, EngineSpec] = {e.code: e for e in _ENGINE_LIST}
if len(ENGINES) != len(_ENGINE_LIST):
    raise RuntimeError("Коды двигателей должны быть уникальными")
