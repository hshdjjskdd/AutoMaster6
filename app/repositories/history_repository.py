"""Репозиторий истории ремонтов."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RepairHistory


class HistoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        player_id: int,
        order_id: int,
        car_id: int,
        summary: str,
        revenue: int,
        parts_cost: int,
    ) -> RepairHistory:
        """Добавляет запись. IntegrityError, если по заказу запись уже есть."""
        entry = RepairHistory(
            player_id=player_id,
            order_id=order_id,
            car_id=car_id,
            summary=summary,
            revenue=revenue,
            parts_cost=parts_cost,
            profit=revenue - parts_cost,
        )
        self._session.add(entry)
        await self._session.flush()
        return entry

    async def get_by_order(self, player_id: int, order_id: int) -> RepairHistory | None:
        result = await self._session.execute(
            select(RepairHistory)
            .where(RepairHistory.order_id == order_id, RepairHistory.player_id == player_id)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def list_for_player(
        self, player_id: int, *, limit: int = 20, offset: int = 0
    ) -> list[RepairHistory]:
        result = await self._session.execute(
            select(RepairHistory)
            .where(RepairHistory.player_id == player_id)
            .order_by(RepairHistory.id.desc())
            .limit(limit)
            .offset(offset)
            .execution_options(populate_existing=True)
        )
        return list(result.scalars())

    async def totals(self, player_id: int) -> tuple[int, int, int, int]:
        """(завершено заказов, выручка, расходы на детали, чистая прибыль) за всё время."""
        row = (
            await self._session.execute(
                select(
                    func.count(RepairHistory.id),
                    func.coalesce(func.sum(RepairHistory.revenue), 0),
                    func.coalesce(func.sum(RepairHistory.parts_cost), 0),
                    func.coalesce(func.sum(RepairHistory.profit), 0),
                ).where(RepairHistory.player_id == player_id)
            )
        ).one()
        return int(row[0]), int(row[1]), int(row[2]), int(row[3])
