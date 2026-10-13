"""Фоновая задача: вовремя обновляет доски заказов и присылает игрокам уведомления.

Задача ничего не «помнит»: время следующего обновления лежит в БД. Если бот был выключен,
после запуска все просроченные доски обновятся на ближайшем проходе.
"""

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import texts_orders
from app.game_data.economy import NOTIFY_ON_REFRESH, REFRESH_POLL_SECONDS
from app.keyboards.orders import notice_keyboard
from app.services.board_refresher import RefreshNotice, refresh_due_boards

logger = logging.getLogger(__name__)


async def _send(bot: Bot, notice: RefreshNotice) -> None:
    text = texts_orders.render_refresh_notice(notice.result)
    for attempt in range(2):
        try:
            await bot.send_message(notice.telegram_id, text, reply_markup=notice_keyboard())
            return
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after)
        except TelegramAPIError as exc:  # бот заблокирован, чат недоступен и т. п.
            logger.warning("Не удалось уведомить игрока %s: %s", notice.player_id, exc)
            return


async def run_refresh_loop(
    bot: Bot, factory: async_sessionmaker[AsyncSession], poll_seconds: float = REFRESH_POLL_SECONDS
) -> None:
    """Бесконечный цикл проверки. Отменяется при остановке бота."""
    logger.info("Фоновое обновление заказов запущено (проверка раз в %s с)", poll_seconds)
    while True:
        try:
            for notice in await refresh_due_boards(factory):
                if NOTIFY_ON_REFRESH:
                    await _send(bot, notice)
                    await asyncio.sleep(0.05)  # не упираемся в лимиты Telegram
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Сбой фонового обновления заказов")
        await asyncio.sleep(poll_seconds)
