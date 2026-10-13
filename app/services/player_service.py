"""Сервис игрока: регистрация и получение профиля."""

import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.game_data.constants import (
    MAX_REPUTATION,
    START_EXPERIENCE,
    START_LEVEL,
    START_MONEY,
    START_REPUTATION,
)
from app.game_data.levels import get_level_info, get_next_level_info
from app.game_data.reputation import get_reputation_title
from app.models import Player
from app.repositories import PlayerRepository
from app.schemas import PlayerProfile, RegistrationResult, TelegramUserData

logger = logging.getLogger(__name__)


def _resolve_display_name(player: Player) -> str:
    """Имя для показа: имя в Telegram, иначе username, иначе нейтральная подпись."""
    return player.first_name or player.username or f"Игрок {player.telegram_id}"


class PlayerService:
    """Бизнес-логика игрока. Управляет транзакциями своей сессии."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._players = PlayerRepository(session)

    async def register_or_update(self, user: TelegramUserData) -> RegistrationResult:
        """Регистрирует нового игрока или обновляет данные существующего."""
        player = await self._players.get_by_telegram_id(user.telegram_id)
        if player is not None:
            if self._sync_user_info(player, user):
                await self._session.commit()
            return RegistrationResult(profile=self._build_profile(player), is_new=False)

        try:
            player = await self._players.create(
                telegram_id=user.telegram_id,
                username=user.username,
                first_name=user.first_name,
                money=START_MONEY,
                level=START_LEVEL,
                experience=START_EXPERIENCE,
                reputation=START_REPUTATION,
            )
            await self._session.commit()
        except IntegrityError:
            # Два одновременных /start от одного пользователя: победил первый запрос.
            await self._session.rollback()
            player = await self._players.get_by_telegram_id(user.telegram_id)
            if player is None:
                raise
            return RegistrationResult(profile=self._build_profile(player), is_new=False)

        logger.info("Зарегистрирован новый игрок telegram_id=%s", user.telegram_id)
        return RegistrationResult(profile=self._build_profile(player), is_new=True)

    async def get_player_id(self, telegram_id: int) -> int | None:
        """Внутренний id игрока по Telegram ID или None, если он не зарегистрирован."""
        return await self._players.get_id_by_telegram_id(telegram_id)

    async def get_profile(self, telegram_id: int) -> PlayerProfile | None:
        """Возвращает профиль игрока или None, если он не зарегистрирован."""
        player = await self._players.get_by_telegram_id(telegram_id)
        if player is None:
            return None
        return self._build_profile(player)

    @staticmethod
    def _sync_user_info(player: Player, user: TelegramUserData) -> bool:
        """Обновляет username и имя, если они изменились. Возвращает True при изменениях."""
        changed = False
        if player.username != user.username:
            player.username = user.username
            changed = True
        if user.first_name and player.first_name != user.first_name:
            player.first_name = user.first_name
            changed = True
        return changed

    @staticmethod
    def _build_profile(player: Player) -> PlayerProfile:
        level_info = get_level_info(player.level)
        next_level = get_next_level_info(player.level)
        return PlayerProfile(
            telegram_id=player.telegram_id,
            display_name=_resolve_display_name(player),
            username=player.username,
            money=player.money,
            level=player.level,
            level_title=level_info.title,
            experience=player.experience,
            experience_for_next_level=(
                next_level.experience_required if next_level is not None else None
            ),
            reputation=player.reputation,
            reputation_max=MAX_REPUTATION,
            reputation_title=get_reputation_title(player.reputation),
            registered_at=player.created_at,
        )
