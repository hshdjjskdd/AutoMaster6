"""Репозиторий ремонтных операций."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RepairOperation
from app.models.types import utc_now


class RepairRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_operation(
        self, *, order_id: int, player_id: int, fault_id: int, op_code: str, minutes: int,
        parts_json: str,
    ) -> RepairOperation:
        """Записывает операцию. IntegrityError, если она уже выполнена для заказа."""
        op = RepairOperation(
            order_id=order_id,
            player_id=player_id,
            fault_id=fault_id,
            op_code=op_code,
            minutes=minutes,
            parts_json=parts_json,
            performed_at=utc_now(),
        )
        self._session.add(op)
        await self._session.flush()
        return op

    async def list_for_order(self, order_id: int) -> list[RepairOperation]:
        result = await self._session.execute(
            select(RepairOperation)
            .where(RepairOperation.order_id == order_id)
            .order_by(RepairOperation.id)
            .execution_options(populate_existing=True)
        )
        return list(result.scalars())
