"""Обновление досок всех игроков, у которых пришло время (для фоновой задачи)."""

import logging
import random
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.types import utc_now
from app.repositories import BoardRepository, PlayerRepository
from app.schemas import RefreshResult
from app.services.client_order_service import ClientOrderService

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RefreshNotice:
    """Кого и о чём уведомить после обновления."""

    player_id: int
    telegram_id: int
    result: RefreshResult


async def refresh_due_boards(
    factory: async_sessionmaker[AsyncSession],
    *,
    now: datetime | None = None,
    rng: random.Random | None = None,
    limit: int = 200,
) -> list[RefreshNotice]:
    """Обновляет доски, чьё время пришло. Возвращает уведомления для тех, у кого появились заказы.

    Каждый игрок обрабатывается в своей транзакции; сбой одного не мешает остальным.
    Повторный или параллельный вызов не создаёт дублей (см. refresh_if_due).
    """
    now = now or utc_now()
    async with factory() as session:
        due = await BoardRepository(session).list_due(now, limit)
    notices: list[RefreshNotice] = []
    for player_id in due:
        try:
            async with factory() as session:
                result = await ClientOrderService(session, rng).refresh_if_due(player_id, now=now)
                if not (result.refreshed and result.created_tiers):
                    continue
                telegram_id = await PlayerRepository(session).get_telegram_id(player_id)
        except Exception:
            logger.exception("Не удалось обновить доску игрока %s", player_id)
            continue
        if telegram_id is not None:
            notices.append(RefreshNotice(player_id, telegram_id, result))
    return notices
