"""Допустимые переходы статусов заказа.

Статус COMPLETED нельзя выставить обычной сменой статуса: завершение заказа
выплачивает награду и пишет историю, поэтому оно выполняется отдельной операцией
OrderService.complete_order.
"""

from app.game_data.enums import OrderStatus

ALLOWED_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.NEW: frozenset({OrderStatus.DIAGNOSTICS, OrderStatus.CANCELLED}),
    OrderStatus.DIAGNOSTICS: frozenset(
        {OrderStatus.AWAITING_PARTS, OrderStatus.IN_REPAIR, OrderStatus.CANCELLED}
    ),
    OrderStatus.AWAITING_PARTS: frozenset({OrderStatus.IN_REPAIR, OrderStatus.CANCELLED}),
    OrderStatus.IN_REPAIR: frozenset(
        {OrderStatus.AWAITING_PARTS, OrderStatus.READY, OrderStatus.CANCELLED}
    ),
    OrderStatus.READY: frozenset({OrderStatus.IN_REPAIR, OrderStatus.COMPLETED}),
    OrderStatus.COMPLETED: frozenset(),
    OrderStatus.CANCELLED: frozenset(),
}

TERMINAL_STATUSES: frozenset[OrderStatus] = frozenset(
    {OrderStatus.COMPLETED, OrderStatus.CANCELLED}
)

# Заказы, которые сейчас находятся в мастерской и занимают в ней место.
ACTIVE_STATUSES: frozenset[OrderStatus] = frozenset(
    status for status in OrderStatus if status not in TERMINAL_STATUSES
)

# Статусы, в которых можно вносить неисправности и результаты диагностики.
DIAGNOSABLE_STATUSES: frozenset[OrderStatus] = frozenset(
    {OrderStatus.DIAGNOSTICS, OrderStatus.AWAITING_PARTS, OrderStatus.IN_REPAIR}
)

# Статусы, в которых со склада можно списать деталь на заказ.
PART_INSTALL_STATUSES: frozenset[OrderStatus] = frozenset(
    {OrderStatus.AWAITING_PARTS, OrderStatus.IN_REPAIR}
)


def can_transition(current: OrderStatus, new: OrderStatus) -> bool:
    """True, если переход current -> new разрешён правилами."""
    return new in ALLOWED_TRANSITIONS[current]
