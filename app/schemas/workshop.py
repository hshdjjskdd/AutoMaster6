"""Схемы клиентских заказов: карточки предложений и заказов в мастерской."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.game_data.enums import DriveType, FuelType, OfferStatus, OrderStatus, Transmission


class CarCard(BaseModel):
    model_config = ConfigDict(frozen=True)

    brand: str
    model: str
    trim_name: str | None
    year: int
    body_type: str
    engine_code: str
    engine_volume_cc: int
    power_hp: int
    fuel_type: FuelType
    transmission: Transmission
    drive_type: DriveType
    mileage_km: int
    color: str
    plate: str
    vin: str
    condition_pct: int


class OfferCard(BaseModel):
    model_config = ConfigDict(frozen=True)

    offer_id: int
    status: OfferStatus
    customer_name: str
    car: CarCard
    complaint: str
    symptoms: tuple[str, ...]
    payment: int
    potential_bonus: int
    deadline_hours: int
    expires_at: datetime
    tier: int = 1  # сложность заказа: 1 🟢, 2 🟡, 3 🔴
    est_cost: int = 0  # ориентировочные расходы на детали


class WorkshopOrderCard(BaseModel):
    model_config = ConfigDict(frozen=True)

    order_id: int
    status: OrderStatus
    customer_name: str
    car_id: int
    car: CarCard
    complaint: str
    symptoms: tuple[str, ...]
    reward: int
    potential_bonus: int
    created_at: datetime
    deadline_at: datetime | None
    # None — отменить нельзя; 0 — бесплатно; >0 — штраф к репутации.
    cancel_penalty: int | None
    tier: int = 1
    est_cost: int = 0


class Board(BaseModel):
    model_config = ConfigDict(frozen=True)

    offers: tuple[OfferCard, ...]
    active_orders: int
    capacity: int
    next_refresh_at: datetime | None = None
    board_size: int = 0  # сколько заказов вмещает доска


class RefreshResult(BaseModel):
    """Итог попытки обновить доску."""

    model_config = ConfigDict(frozen=True)

    refreshed: bool  # True — именно этот вызов выполнил обновление
    created_tiers: tuple[int, ...]  # сложности созданных заказов
    available: int  # сколько заказов на доске после обновления
    next_refresh_at: datetime


class FinanceSummary(BaseModel):
    """Итоги по завершённым заказам: выручка, расходы на детали, чистая прибыль."""

    model_config = ConfigDict(frozen=True)

    orders_done: int
    revenue: int
    expenses: int
    profit: int
    balance: int
    active_orders: int


class AcceptResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    offer_id: int
    order_id: int
    car_id: int


class CancelResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    order_id: int
    reputation_penalty: int
    reputation_after: int
