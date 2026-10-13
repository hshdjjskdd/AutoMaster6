"""Сборка и запуск бота."""

from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError, TelegramNetworkError, TelegramUnauthorizedError
from aiogram.types import BotCommand
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import __version__
from app.background import run_refresh_loop
from app.config import ConfigError, Settings, load_settings
from app.database import create_engine, create_session_factory, init_db
from app.game_data.constants import GAME_TITLE
from app.handlers import get_routers
from app.logging_setup import setup_logging
from app.middlewares import DbSessionMiddleware

logger = logging.getLogger(__name__)

BOT_COMMANDS = [
    BotCommand(command="start", description="Начать игру"),
    BotCommand(command="menu", description="Главное меню"),
    BotCommand(command="orders", description="Заказы клиентов"),
    BotCommand(command="workshop", description="Мастерская"),
    BotCommand(command="finance", description="Выручка, расходы, прибыль"),
    BotCommand(command="shop", description="Магазин запчастей"),
    BotCommand(command="stock", description="Склад"),
    BotCommand(command="profile", description="Профиль игрока"),
    BotCommand(command="help", description="Справка"),
]


def build_dispatcher(session_factory: async_sessionmaker[AsyncSession]) -> Dispatcher:
    """Создаёт диспетчер: middleware с сессией БД и все роутеры."""
    dispatcher = Dispatcher()
    dispatcher.update.outer_middleware(DbSessionMiddleware(session_factory))
    for router in get_routers():
        dispatcher.include_router(router)
    return dispatcher


async def run_bot(settings: Settings) -> int:
    """Запускает long polling. Возвращает код выхода процесса."""
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = build_dispatcher(session_factory)

    try:
        await init_db(engine)

        me = await bot.get_me()
        logger.info("%s v%s: бот @%s запущен", GAME_TITLE, __version__, me.username)

        # Long polling не работает, пока на боте висит webhook.
        await bot.delete_webhook(drop_pending_updates=False)
        try:
            await bot.set_my_commands(BOT_COMMANDS)
        except TelegramAPIError as exc:
            logger.warning("Не удалось обновить список команд: %s", exc)

        refresher = asyncio.create_task(run_refresh_loop(bot, session_factory))
        try:
            await dispatcher.start_polling(
                bot, allowed_updates=dispatcher.resolve_used_update_types()
            )
        finally:
            refresher.cancel()
            await asyncio.gather(refresher, return_exceptions=True)
    except TelegramUnauthorizedError:
        logger.critical("Telegram отклонил BOT_TOKEN. Проверьте токен в файле .env.")
        return 1
    except TelegramNetworkError as exc:
        logger.critical("Не удалось связаться с Telegram: %s", exc)
        return 1
    finally:
        await bot.session.close()
        await engine.dispose()

    logger.info("Бот остановлен")
    return 0


def run() -> int:
    """Загружает конфигурацию и запускает бота. Возвращает код выхода."""
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Ошибка конфигурации: {exc}", file=sys.stderr)
        return 1

    setup_logging(settings.log_level)
    try:
        return asyncio.run(run_bot(settings))
    except KeyboardInterrupt:
        logger.info("Остановлено пользователем")
        return 0
    except Exception:
        logger.exception("Критическая ошибка, бот остановлен")
        return 1
