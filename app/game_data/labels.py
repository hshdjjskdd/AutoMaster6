"""Русские названия перечислений для показа игроку."""

from app.game_data.enums import DriveType, FuelType, OfferStatus, OrderStatus, Transmission

FUEL_TITLES: dict[FuelType, str] = {
    FuelType.PETROL: "бензин",
    FuelType.DIESEL: "дизель",
    FuelType.HYBRID: "гибрид",
    FuelType.ELECTRIC: "электро",
    FuelType.LPG: "газ",
}

TRANSMISSION_TITLES: dict[Transmission, str] = {
    Transmission.MANUAL: "механика",
    Transmission.AUTOMATIC: "автомат",
    Transmission.CVT: "вариатор",
    Transmission.ROBOT: "робот",
}

DRIVE_TITLES: dict[DriveType, str] = {
    DriveType.FWD: "передний",
    DriveType.RWD: "задний",
    DriveType.AWD: "полный",
}

ORDER_STATUS_TITLES: dict[OrderStatus, str] = {
    OrderStatus.NEW: "🆕 Принят, ждёт диагностики",
    OrderStatus.DIAGNOSTICS: "🔍 Диагностика",
    OrderStatus.AWAITING_PARTS: "📦 Ожидание запчастей",
    OrderStatus.IN_REPAIR: "🔧 В ремонте",
    OrderStatus.READY: "✅ Готов к выдаче",
    OrderStatus.COMPLETED: "🏁 Завершён",
    OrderStatus.CANCELLED: "🚫 Отменён",
}

OFFER_STATUS_TITLES: dict[OfferStatus, str] = {
    OfferStatus.AVAILABLE: "Доступен",
    OfferStatus.ACCEPTED: "Принят",
    OfferStatus.DECLINED: "Отклонён",
    OfferStatus.EXPIRED: "Клиент не дождался",
}
