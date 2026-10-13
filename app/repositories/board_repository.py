"""Репозиторий состояния доски заказов (время обновления, серия пустых обновлений)."""

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OrderBoardState


class BoardRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ensure(self, player_id: int, now: datetime) -> None:
        """Создаёт строку состояния, если её нет (обновление сразу «просрочено»).

        INSERT OR IGNORE: параллельные вызовы не создают дубликатов и не падают.
        Это запись, поэтому она же берёт блокировку БД в начале транзакции.
        """
        await self._session.execute(
            sqlite_insert(OrderBoardState)
            .values(
                player_id=player_id, next_refresh_at=now, empty_streak=0, refresh_count=0
            )
            .on_conflict_do_nothing(index_elements=["player_id"])
        )

    async def claim_due(self, player_id: int, now: datetime, next_at: datetime) -> bool:
        """Compare-and-swap: переносит next_refresh_at вперёд, только если время пришло.

        True получает ровно один из одновременных вызовов — он и выдаёт заказы.
        """
        result = await self._session.execute(
            update(OrderBoardState)
            .where(OrderBoardState.player_id == player_id, OrderBoardState.next_refresh_at <= now)
            .values(next_refresh_at=next_at)
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1

    async def get(self, player_id: int) -> OrderBoardState | None:
        result = await self._session.execute(
            select(OrderBoardState)
            .where(OrderBoardState.player_id == player_id)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def finish_refresh(
        self, *, player_id: int, now: datetime, empty_streak: int
    ) -> None:
        await self._session.execute(
            update(OrderBoardState)
            .where(OrderBoardState.player_id == player_id)
            .values(
                last_refresh_at=now,
                empty_streak=empty_streak,
                refresh_count=OrderBoardState.refresh_count + 1,
            )
            .execution_options(synchronize_session=False)
        )

    async def list_due(self, now: datetime, limit: int = 200) -> list[int]:
        """Игроки, у которых пришло время обновления (старые — первыми)."""
        result = await self._session.execute(
            select(OrderBoardState.player_id)
            .where(OrderBoardState.next_refresh_at <= now)
            .order_by(OrderBoardState.next_refresh_at)
            .limit(limit)
        )
        return list(result.scalars())
