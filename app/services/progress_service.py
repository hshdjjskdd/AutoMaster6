"""Сервис прогресса игрока: опыт, уровень, репутация."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import PlayerNotFound
from app.game_data.levels import level_for_experience
from app.repositories import PlayerRepository
from app.schemas import ProgressResult
from app.services.transaction import atomic


class ProgressService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._players = PlayerRepository(session)

    async def add_experience(self, player_id: int, amount: int) -> ProgressResult:
        """Начисляет опыт и повышает уровень, если порог пройден. Опыт не уменьшается.

        Raises:
            PlayerNotFound: игрока нет.
            ValueError: amount не положителен.
        """
        if amount <= 0:
            raise ValueError("Опыт начисляется только положительными значениями")
        async with atomic(self._session):
            experience = await self._players.add_experience(player_id, amount)
            if experience is None:
                raise PlayerNotFound(player_id)
            new_level = level_for_experience(experience)
            leveled_up = await self._players.raise_level_to(player_id, new_level)
            level = await self._players.get_level(player_id)
        assert level is not None
        return ProgressResult(experience=experience, level=level, leveled_up=leveled_up)

    async def change_reputation(self, player_id: int, delta: int) -> int:
        """Меняет репутацию на delta, не выходя за границы 0..100. Возвращает новое значение."""
        async with atomic(self._session):
            reputation = await self._players.change_reputation(player_id, delta)
            if reputation is None:
                raise PlayerNotFound(player_id)
        return reputation
