"""Результаты операций сервисов."""

from pydantic import BaseModel, ConfigDict


class LedgerResult(BaseModel):
    """Итог денежной операции."""

    model_config = ConfigDict(frozen=True)

    transaction_id: int
    amount: int
    balance_after: int
    # True, если операция с таким ключом уже была проведена ранее и повторно не применялась.
    duplicate: bool


class PurchaseResult(BaseModel):
    """Итог покупки детали или оборудования."""

    model_config = ConfigDict(frozen=True)

    item_code: str
    quantity: int
    total_price: int
    balance_after: int
    duplicate: bool


class OrderCompletionResult(BaseModel):
    """Итог сдачи заказа."""

    model_config = ConfigDict(frozen=True)

    order_id: int
    reward_paid: int
    parts_cost: int
    profit: int
    balance: int
    # True, если заказ уже был завершён раньше: награда повторно не начислялась.
    already_completed: bool
    # Премия за сдачу в срок (входит в reward_paid).
    bonus: int = 0


class ProgressResult(BaseModel):
    """Итог изменения опыта игрока."""

    model_config = ConfigDict(frozen=True)

    experience: int
    level: int
    leveled_up: bool
