"""Репозиторий заказов.

Все изменения статуса выполняются условными UPDATE (compare-and-swap): строка меняется
только если заказ всё ещё в ожидаемом статусе. При параллельных запросах побеждает
ровно один, остальные получают False.
"""

from collections.abc import Collection
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.game_data.enums import OrderStatus
from app.game_data.order_flow import ACTIVE_STATUSES
from app.models import Order, OrderPart
from app.models.types import utc_now


class OrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        player_id: int,
        car_id: int,
        customer_name: str,
        complaint: str,
        reward: int,
        deadline_at: datetime | None,
    ) -> Order:
        """Создаёт заказ в статусе NEW. IntegrityError, если у машины уже есть активный заказ."""
        order = Order(
            player_id=player_id,
            car_id=car_id,
            status=OrderStatus.NEW,
            customer_name=customer_name,
            complaint=complaint,
            reward=reward,
            deadline_at=deadline_at,
        )
        self._session.add(order)
        await self._session.flush()
        return order

    async def get(
        self, player_id: int, order_id: int, *, with_details: bool = False
    ) -> Order | None:
        """Заказ игрока. with_details подгружает автомобиль, неисправности, диагностику, детали."""
        stmt = (
            select(Order)
            .where(Order.id == order_id, Order.player_id == player_id)
            .execution_options(populate_existing=True)
        )
        if with_details:
            stmt = stmt.options(
                selectinload(Order.car),
                selectinload(Order.faults),
                selectinload(Order.diagnostics),
                selectinload(Order.parts).selectinload(OrderPart.part),
            )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_for_player(
        self,
        player_id: int,
        *,
        statuses: Collection[OrderStatus] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Order]:
        stmt = select(Order).where(Order.player_id == player_id)
        if statuses:
            stmt = stmt.where(Order.status.in_(list(statuses)))
        stmt = (
            stmt.order_by(Order.id.desc())
            .limit(limit)
            .offset(offset)
            .execution_options(populate_existing=True)
        )
        return list((await self._session.execute(stmt)).scalars())

    async def set_deadline(self, *, order_id: int, player_id: int, deadline_at: datetime) -> None:
        await self._session.execute(
            update(Order)
            .where(Order.id == order_id, Order.player_id == player_id)
            .values(deadline_at=deadline_at, updated_at=utc_now())
            .execution_options(synchronize_session=False)
        )

    async def count_active(self, player_id: int) -> int:
        """Сколько заказов игрока сейчас в мастерской (не завершены и не отменены)."""
        total = await self._session.scalar(
            select(func.count())
            .select_from(Order)
            .where(Order.player_id == player_id, Order.status.in_(list(ACTIVE_STATUSES)))
        )
        return int(total or 0)

    async def transition_status(
        self, *, order_id: int, player_id: int, expected: OrderStatus, new: OrderStatus
    ) -> bool:
        """Меняет статус, только если он сейчас равен expected. True — переход выполнен."""
        result = await self._session.execute(
            update(Order)
            .where(Order.id == order_id, Order.player_id == player_id, Order.status == expected)
            .values(status=new, updated_at=utc_now())
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1

    async def touch_if_status(
        self, *, order_id: int, player_id: int, statuses: Collection[OrderStatus]
    ) -> bool:
        """Проверяет статус заказа и «захватывает» строку на запись.

        Выполняется как UPDATE, поэтому параллельная смена статуса не может
        проскочить между проверкой и дальнейшими изменениями в той же транзакции.
        """
        result = await self._session.execute(
            update(Order)
            .where(
                Order.id == order_id,
                Order.player_id == player_id,
                Order.status.in_(list(statuses)),
            )
            .values(updated_at=utc_now())
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1

    async def complete_if_ready(self, *, order_id: int, player_id: int, now: datetime) -> bool:
        """READY -> COMPLETED с отметкой о выплате награды.

        Условие reward_paid_at IS NULL — вторая линия защиты: заказ с уже выплаченной
        наградой завершить повторно нельзя. True — заказ завершён именно этим вызовом.
        """
        result = await self._session.execute(
            update(Order)
            .where(
                Order.id == order_id,
                Order.player_id == player_id,
                Order.status == OrderStatus.READY,
                Order.reward_paid_at.is_(None),
            )
            .values(
                status=OrderStatus.COMPLETED,
                completed_at=now,
                reward_paid_at=now,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1

    async def add_part(self, *, order_id: int, part_id: int, quantity: int, unit_price: int) -> None:
        """Записывает установленную деталь. Повторная установка суммирует количество."""
        stmt = sqlite_insert(OrderPart).values(
            order_id=order_id,
            part_id=part_id,
            quantity=quantity,
            unit_price=unit_price,
            installed_at=utc_now(),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["order_id", "part_id"],
            set_={"quantity": OrderPart.quantity + stmt.excluded.quantity},
        )
        await self._session.execute(stmt)

    async def parts_cost(self, order_id: int) -> int:
        """Суммарная стоимость деталей заказа."""
        total = await self._session.scalar(
            select(func.coalesce(func.sum(OrderPart.quantity * OrderPart.unit_price), 0)).where(
                OrderPart.order_id == order_id
            )
        )
        return int(total or 0)
