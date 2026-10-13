"""Схемы магазина, склада и ремонта (этап 5)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.game_data.enums import OrderStatus


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class NeedView(_Frozen):
    type_code: str
    name: str
    qty: int
    in_stock: int  # сколько подходящих деталей (любого качества) на складе

    @property
    def enough(self) -> bool:
        return self.in_stock >= self.qty


class OperationView(_Frozen):
    code: str
    title: str
    minutes: int
    done: bool
    needs: tuple[NeedView, ...]

    @property
    def can_perform(self) -> bool:
        return not self.done and all(n.enough for n in self.needs)


class FaultRepairView(_Frozen):
    fault_id: int
    code: str
    name: str
    system: str
    resolved: bool
    ops: tuple[OperationView, ...]


class RepairOverview(_Frozen):
    order_id: int
    status: OrderStatus
    car_title: str
    plate: str
    complaint: str
    faults: tuple[FaultRepairView, ...]
    balance: int
    deadline_at: datetime | None
    diagnostics_open: bool  # можно ли продолжить диагностику (после неудачной проверки)

    @property
    def all_resolved(self) -> bool:
        return bool(self.faults) and all(f.resolved for f in self.faults)

    @property
    def can_repair(self) -> bool:
        return self.status in (
            OrderStatus.DIAGNOSTICS, OrderStatus.AWAITING_PARTS, OrderStatus.IN_REPAIR
        )

    @property
    def can_verify(self) -> bool:
        return self.status == OrderStatus.IN_REPAIR and self.all_resolved

    @property
    def can_finish(self) -> bool:
        return self.status == OrderStatus.READY


class UsedPart(_Frozen):
    sku: str
    name: str
    qty: int
    price: int


class OperationResult(_Frozen):
    order_id: int
    op_code: str
    title: str
    minutes: int
    parts: tuple[UsedPart, ...]
    fault_resolved: bool
    all_resolved: bool


class VerificationResult(_Frozen):
    order_id: int
    ok: bool
    complaint_remains: bool
    minutes: int


class FinishResult(_Frozen):
    order_id: int
    reward_paid: int
    bonus: int
    parts_cost: int
    profit: int
    balance: int
    experience_gained: int
    level: int | None
    leveled_up: bool
    already_completed: bool


class QualityView(_Frozen):
    sku: str
    level: int
    title: str
    emoji: str
    note: str
    price: int
    stock: int


class ShopTypeView(_Frozen):
    type_code: str
    name: str
    section: str
    universal: bool
    fit_label: str  # «двигатель K4M» / «универсальная»
    models: tuple[str, ...]
    qualities: tuple[QualityView, ...]
    balance: int
    ver: int  # номер последней записи журнала: защита от двойного нажатия
    order_id: int
    car_title: str | None


class ShopOrderOption(_Frozen):
    order_id: int
    car_title: str


class StockLine(_Frozen):
    sku: str
    name: str
    quantity: int
    section: str
    quality_emoji: str


class PlanLine(_Frozen):
    fault_name: str
    op_title: str
    type_code: str
    part_name: str
    qty: int
    in_stock: int
    unit_price: int  # цена качественного аналога

    @property
    def missing(self) -> int:
        return max(0, self.qty - self.in_stock)


class OrderPartsPlan(_Frozen):
    order_id: int
    car_title: str
    lines: tuple[PlanLine, ...]
    balance: int
