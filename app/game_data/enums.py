"""Перечисления игровых сущностей. Значения хранятся в БД как строки."""

from enum import StrEnum


class FuelType(StrEnum):
    PETROL = "petrol"
    DIESEL = "diesel"
    HYBRID = "hybrid"
    ELECTRIC = "electric"
    LPG = "lpg"


class Transmission(StrEnum):
    MANUAL = "manual"
    AUTOMATIC = "automatic"
    CVT = "cvt"
    ROBOT = "robot"


class DriveType(StrEnum):
    FWD = "fwd"
    RWD = "rwd"
    AWD = "awd"


class OrderStatus(StrEnum):
    NEW = "new"
    DIAGNOSTICS = "diagnostics"
    AWAITING_PARTS = "awaiting_parts"
    IN_REPAIR = "in_repair"
    READY = "ready"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class OfferStatus(StrEnum):
    """Статус предложения клиента на доске заказов."""

    AVAILABLE = "available"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"


class FaultSeverity(StrEnum):
    MINOR = "minor"
    MODERATE = "moderate"
    SERIOUS = "serious"
    CRITICAL = "critical"


class DiagnosticOutcome(StrEnum):
    FAULT_FOUND = "fault_found"
    NO_FAULT = "no_fault"
    INCONCLUSIVE = "inconclusive"


class TransactionType(StrEnum):
    INCOME = "income"
    EXPENSE = "expense"


class TransactionCategory(StrEnum):
    ORDER_REWARD = "order_reward"
    PART_PURCHASE = "part_purchase"
    EQUIPMENT_PURCHASE = "equipment_purchase"
    PENALTY = "penalty"
    ADJUSTMENT = "adjustment"


# Какой тип операции допустим для категории: +1 — только доход, -1 — только расход,
# None — любой (например, ручная корректировка баланса).
CATEGORY_SIGN: dict[TransactionCategory, int | None] = {
    TransactionCategory.ORDER_REWARD: 1,
    TransactionCategory.PART_PURCHASE: -1,
    TransactionCategory.EQUIPMENT_PURCHASE: -1,
    TransactionCategory.PENALTY: -1,
    TransactionCategory.ADJUSTMENT: None,
}


class PartCategory(StrEnum):
    ENGINE = "engine"
    BRAKES = "brakes"
    SUSPENSION = "suspension"
    ELECTRICS = "electrics"
    FLUIDS = "fluids"
    FILTERS = "filters"
    TRANSMISSION = "transmission"


class EquipmentCategory(StrEnum):
    DIAGNOSTIC = "diagnostic"
    LIFTING = "lifting"
    HAND_TOOLS = "hand_tools"
    POWER_TOOLS = "power_tools"
    SHOP = "shop"
