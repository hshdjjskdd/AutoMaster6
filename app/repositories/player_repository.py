"""Репозиторий игроков: только операции с БД, без игровой логики."""

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.game_data.constants import MAX_REPUTATION, MIN_REPUTATION
from app.models import Player
from app.models.types import utc_now


class PlayerRepository:
    """Доступ к таблице players. Транзакцией (commit/rollback) управляет сервис."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_telegram_id(self, telegram_id: int) -> Player | None:
        """Возвращает игрока по Telegram ID или None."""
        result = await self._session.execute(
            select(Player).where(Player.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
        money: int,
        level: int,
        experience: int,
        reputation: int,
    ) -> Player:
        """Добавляет нового игрока и выполняет flush, чтобы получить его id."""
        player = Player(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            money=money,
            level=level,
            experience=experience,
            reputation=reputation,
        )
        self._session.add(player)
        await self._session.flush()
        return player

    async def get_id_by_telegram_id(self, telegram_id: int) -> int | None:
        """Возвращает внутренний id игрока по Telegram ID или None."""
        return await self._session.scalar(
            select(Player.id).where(Player.telegram_id == telegram_id)
        )

    async def get_telegram_id(self, player_id: int) -> int | None:
        """Telegram ID игрока (он же id личного чата) или None."""
        return await self._session.scalar(
            select(Player.telegram_id).where(Player.id == player_id)
        )

    async def get_level(self, player_id: int) -> int | None:
        """Текущий уровень игрока или None, если игрока нет."""
        return await self._session.scalar(select(Player.level).where(Player.id == player_id))

    async def add_experience(self, player_id: int, amount: int) -> int | None:
        """Атомарно прибавляет опыт. Возвращает новое значение или None, если игрока нет."""
        result = await self._session.execute(
            update(Player)
            .where(Player.id == player_id)
            .values(experience=Player.experience + amount, updated_at=utc_now())
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            return None
        return await self._session.scalar(
            select(Player.experience).where(Player.id == player_id)
        )

    async def raise_level_to(self, player_id: int, level: int) -> bool:
        """Поднимает уровень до заданного, если он выше текущего. True — уровень вырос."""
        result = await self._session.execute(
            update(Player)
            .where(Player.id == player_id, Player.level < level)
            .values(level=level, updated_at=utc_now())
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1

    async def change_reputation(self, player_id: int, delta: int) -> int | None:
        """Атомарно меняет репутацию, не выходя за 0..100. Возвращает новое значение."""
        clamped = func.max(
            MIN_REPUTATION, func.min(MAX_REPUTATION, Player.reputation + delta)
        )
        result = await self._session.execute(
            update(Player)
            .where(Player.id == player_id)
            .values(reputation=clamped, updated_at=utc_now())
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            return None
        return await self._session.scalar(
            select(Player.reputation).where(Player.id == player_id)
        )

    async def get_reputation(self, player_id: int) -> int | None:
        """Текущая репутация или None, если игрока нет."""
        return await self._session.scalar(
            select(Player.reputation).where(Player.id == player_id)
        )
