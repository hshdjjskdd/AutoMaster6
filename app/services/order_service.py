"""Сервис заказов: жизненный цикл ремонта, диагностика, детали и сдача заказа."""

import logging
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import (
    CarBusy,
    CarNotFound,
    EquipmentNotFound,
    FaultAlreadyRecorded,
    FaultAlreadyResolved,
    FaultNotFound,
    InsufficientStock,
    InvalidOrderState,
    InvalidStatusTransition,
    OrderNotFound,
    OrderNotReady,
    OrderStateConflict,
    PartNotFound,
)
from app.game_data.economy import on_time_bonus
from app.game_data.enums import (
    DiagnosticOutcome,
    FaultSeverity,
    OrderStatus,
    TransactionCategory,
)
from app.game_data.order_flow import (
    DIAGNOSABLE_STATUSES,
    PART_INSTALL_STATUSES,
    can_transition,
)
from app.models import DiagnosticResult, Fault, Order, RepairHistory
from app.models.types import utc_now
from app.repositories import (
    CarRepository,
    FaultRepository,
    FinanceRepository,
    HistoryRepository,
    InventoryRepository,
    OrderRepository,
)
from app.schemas import OrderCompletionResult
from app.services.transaction import atomic

logger = logging.getLogger(__name__)


def reward_idempotency_key(order_id: int) -> str:
    """Постоянный ключ награды за заказ: по заказу награду можно провести только один раз."""
    return f"order_reward:{order_id}"


class OrderService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._orders = OrderRepository(session)
        self._cars = CarRepository(session)
        self._faults = FaultRepository(session)
        self._inventory = InventoryRepository(session)
        self._finance = FinanceRepository(session)
        self._history = HistoryRepository(session)

    # --- создание и чтение ----------------------------------------------

    async def create_order(
        self,
        *,
        player_id: int,
        car_id: int,
        customer_name: str,
        complaint: str,
        reward: int,
        deadline_at: datetime | None = None,
    ) -> Order:
        """Создаёт заказ в статусе NEW.

        Raises:
            CarNotFound: автомобиля нет или он принадлежит другому игроку.
            CarBusy: у автомобиля уже есть незавершённый заказ.
        """
        if reward < 0:
            raise ValueError("Награда не может быть отрицательной")
        try:
            async with atomic(self._session):
                if await self._cars.get(player_id, car_id) is None:
                    raise CarNotFound(car_id)
                order = await self._orders.create(
                    player_id=player_id,
                    car_id=car_id,
                    customer_name=customer_name,
                    complaint=complaint,
                    reward=reward,
                    deadline_at=deadline_at,
                )
        except IntegrityError as exc:
            raise CarBusy(car_id) from exc
        return order

    async def get_order(
        self, player_id: int, order_id: int, *, with_details: bool = False
    ) -> Order:
        """Заказ игрока. Raises: OrderNotFound."""
        order = await self._orders.get(player_id, order_id, with_details=with_details)
        if order is None:
            raise OrderNotFound(order_id)
        return order

    async def list_orders(
        self,
        player_id: int,
        *,
        statuses: list[OrderStatus] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Order]:
        return await self._orders.list_for_player(
            player_id, statuses=statuses, limit=limit, offset=offset
        )

    # --- статус ----------------------------------------------------------

    async def change_status(self, *, player_id: int, order_id: int, new_status: OrderStatus) -> Order:
        """Меняет статус по правилам переходов.

        Статус COMPLETED сюда не допускается: заказ сдаётся через complete_order.

        Raises:
            OrderNotFound, InvalidStatusTransition,
            OrderStateConflict: статус изменился параллельно, операцию надо повторить.
        """
        async with atomic(self._session):
            order = await self._orders.get(player_id, order_id)
            if order is None:
                raise OrderNotFound(order_id)
            if new_status == OrderStatus.COMPLETED or not can_transition(order.status, new_status):
                raise InvalidStatusTransition(order.status, new_status)
            changed = await self._orders.transition_status(
                order_id=order_id,
                player_id=player_id,
                expected=order.status,
                new=new_status,
            )
            if not changed:
                raise OrderStateConflict(order_id)
        return await self.get_order(player_id, order_id)

    async def cancel_order(self, *, player_id: int, order_id: int) -> Order:
        """Отменяет заказ. Списанные на него детали не возвращаются на склад."""
        return await self.change_status(
            player_id=player_id, order_id=order_id, new_status=OrderStatus.CANCELLED
        )

    # --- неисправности и диагностика ------------------------------------

    async def add_fault(
        self,
        *,
        player_id: int,
        order_id: int,
        code: str,
        name: str,
        system: str,
        severity: FaultSeverity,
    ) -> Fault:
        """Вносит неисправность в заказ (статусы: диагностика, ожидание деталей, ремонт).

        Raises: OrderNotFound, InvalidOrderState, FaultAlreadyRecorded.
        """
        try:
            async with atomic(self._session):
                car_id = await self._lock_order(player_id, order_id, DIAGNOSABLE_STATUSES)
                fault = await self._faults.add_fault(
                    order_id=order_id,
                    car_id=car_id,
                    code=code,
                    name=name,
                    system=system,
                    severity=severity,
                )
        except IntegrityError as exc:
            raise FaultAlreadyRecorded(code) from exc
        return fault

    async def record_diagnostic(
        self,
        *,
        player_id: int,
        order_id: int,
        check_name: str,
        outcome: DiagnosticOutcome,
        findings: str = "",
        duration_minutes: int = 0,
        fault_id: int | None = None,
        equipment_code: str | None = None,
    ) -> DiagnosticResult:
        """Сохраняет результат диагностической проверки (статус заказа — «диагностика»).

        Raises: OrderNotFound, InvalidOrderState, FaultNotFound, EquipmentNotFound.
        """
        async with atomic(self._session):
            await self._lock_order(player_id, order_id, {OrderStatus.DIAGNOSTICS})
            if fault_id is not None and await self._faults.get(order_id, fault_id) is None:
                raise FaultNotFound(fault_id)
            equipment_id: int | None = None
            if equipment_code is not None:
                equipment = await self._inventory.get_equipment_by_code(equipment_code)
                if equipment is None:
                    raise EquipmentNotFound(equipment_code)
                equipment_id = equipment.id
            result = await self._faults.add_diagnostic(
                order_id=order_id,
                check_name=check_name,
                outcome=outcome,
                findings=findings,
                duration_minutes=duration_minutes,
                fault_id=fault_id,
                equipment_id=equipment_id,
            )
        return result

    async def resolve_fault(self, *, player_id: int, order_id: int, fault_id: int) -> None:
        """Отмечает неисправность устранённой (статусы: ожидание деталей, ремонт).

        Raises: OrderNotFound, InvalidOrderState, FaultNotFound, FaultAlreadyResolved.
        """
        async with atomic(self._session):
            await self._lock_order(player_id, order_id, PART_INSTALL_STATUSES)
            if not await self._faults.resolve(order_id=order_id, fault_id=fault_id):
                fault = await self._faults.get(order_id, fault_id)
                if fault is None:
                    raise FaultNotFound(fault_id)
                raise FaultAlreadyResolved(fault_id)

    # --- детали ----------------------------------------------------------

    async def install_part(
        self, *, player_id: int, order_id: int, sku: str, quantity: int = 1
    ) -> None:
        """Списывает деталь со склада игрока на заказ одной транзакцией.

        Raises: OrderNotFound, InvalidOrderState, PartNotFound, InsufficientStock.
        """
        if quantity <= 0:
            raise ValueError("Количество должно быть положительным")
        async with atomic(self._session):
            part = await self._inventory.get_part_by_sku(sku)
            if part is None:
                raise PartNotFound(sku)
            await self._lock_order(player_id, order_id, PART_INSTALL_STATUSES)
            if not await self._inventory.take_stock(player_id, part.id, quantity):
                raise InsufficientStock(sku, quantity)
            await self._orders.add_part(
                order_id=order_id,
                part_id=part.id,
                quantity=quantity,
                unit_price=part.base_price,
            )

    # --- сдача заказа ----------------------------------------------------

    async def complete_order(self, *, player_id: int, order_id: int) -> OrderCompletionResult:
        """Сдаёт готовый заказ: статус COMPLETED, награда, запись в историю ремонтов.

        Награда начисляется не более одного раза, даже при повторном или
        параллельном вызове. Три независимые защиты:
          1. условный переход READY -> COMPLETED (выигрывает один вызов);
          2. отметка reward_paid_at в самом заказе;
          3. постоянный ключ журнала order_reward:<id> (уникальный) и уникальная
             запись истории на заказ.
        Все изменения выполняются одной транзакцией.

        Повторный вызов для уже завершённого заказа возвращает already_completed=True
        и ничего не меняет.

        Raises: OrderNotFound, InvalidStatusTransition, OrderNotReady, OrderStateConflict.
        """
        try:
            return await self._complete(player_id=player_id, order_id=order_id)
        except OrderStateConflict:
            # Параллельный вызов успел раньше. Если заказ уже сдан — это не ошибка.
            order = await self._orders.get(player_id, order_id)
            if order is not None and order.status == OrderStatus.COMPLETED:
                return await self._already_completed(player_id, order)
            raise

    async def _complete(self, *, player_id: int, order_id: int) -> OrderCompletionResult:
        async with atomic(self._session):
            order = await self._orders.get(player_id, order_id)
            if order is None:
                raise OrderNotFound(order_id)
            if order.status == OrderStatus.COMPLETED:
                return await self._already_completed(player_id, order)
            if order.status != OrderStatus.READY:
                raise InvalidStatusTransition(order.status, OrderStatus.COMPLETED)
            unresolved = await self._faults.count_unresolved(order_id)
            if unresolved > 0:
                raise OrderNotReady(order_id, unresolved)

            now = utc_now()
            if not await self._orders.complete_if_ready(
                order_id=order_id, player_id=player_id, now=now
            ):
                raise OrderStateConflict(order_id)

            bonus = on_time_bonus(order.reward, order.deadline_at, now)
            total_reward = order.reward + bonus
            reward_paid = 0
            if total_reward > 0:
                _, duplicate = await self._finance.apply_change(
                    player_id=player_id,
                    amount=total_reward,
                    category=TransactionCategory.ORDER_REWARD,
                    idempotency_key=reward_idempotency_key(order_id),
                    order_id=order_id,
                    description=f"Награда за заказ №{order_id}",
                )
                reward_paid = 0 if duplicate else total_reward

            parts_cost = await self._orders.parts_cost(order_id)
            await self._history.create(
                player_id=player_id,
                order_id=order_id,
                car_id=order.car_id,
                summary=order.complaint,
                revenue=total_reward,
                parts_cost=parts_cost,
            )
            balance = await self._finance.get_balance(player_id)
        assert balance is not None
        logger.info("Заказ %s сдан, начислено %s", order_id, reward_paid)
        return OrderCompletionResult(
            order_id=order_id,
            reward_paid=reward_paid,
            parts_cost=parts_cost,
            profit=total_reward - parts_cost,
            balance=balance,
            already_completed=False,
            bonus=bonus if reward_paid else 0,
        )

    async def _already_completed(self, player_id: int, order: Order) -> OrderCompletionResult:
        balance = await self._finance.get_balance(player_id)
        assert balance is not None
        history = await self._history.get_by_order(player_id, order.id)
        return OrderCompletionResult(
            order_id=order.id,
            reward_paid=0,
            parts_cost=history.parts_cost if history else 0,
            profit=history.profit if history else 0,
            balance=balance,
            already_completed=True,
        )

    async def get_repair_history(
        self, player_id: int, *, limit: int = 20, offset: int = 0
    ) -> list[RepairHistory]:
        return await self._history.list_for_player(player_id, limit=limit, offset=offset)

    # --- внутреннее ------------------------------------------------------

    async def _lock_order(
        self, player_id: int, order_id: int, allowed: "frozenset[OrderStatus] | set[OrderStatus]"
    ) -> int:
        """Проверяет, что заказ игрока в одном из допустимых статусов, и фиксирует его.

        Возвращает car_id заказа. Если заказа нет — OrderNotFound, если статус не
        подходит — InvalidOrderState.
        """
        if await self._orders.touch_if_status(
            order_id=order_id, player_id=player_id, statuses=allowed
        ):
            order = await self._orders.get(player_id, order_id)
            assert order is not None
            return order.car_id
        order = await self._orders.get(player_id, order_id)
        if order is None:
            raise OrderNotFound(order_id)
        raise InvalidOrderState(order_id, order.status)
