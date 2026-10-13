"""Глобальный обработчик ошибок: логирует исключение и вежливо отвечает игроку."""

import logging

from aiogram import Router
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from aiogram.types import ErrorEvent

from app import texts

logger = logging.getLogger(__name__)

router = Router(name="errors")


@router.error()
async def handle_error(event: ErrorEvent) -> bool:
    update = event.update
    exception = event.exception

    if isinstance(exception, TelegramForbiddenError):
        # Пользователь заблокировал бота — отвечать некому.
        logger.warning("Нет доступа к чату (update_id=%s): %s", update.update_id, exception)
        return True

    logger.error(
        "Необработанная ошибка (update_id=%s)",
        update.update_id,
        exc_info=(type(exception), exception, exception.__traceback__),
    )

    try:
        if update.message is not None:
            await update.message.answer(texts.ERROR_TEXT)
        elif update.callback_query is not None:
            await update.callback_query.answer(texts.ERROR_TEXT, show_alert=True)
    except TelegramAPIError:
        logger.warning("Не удалось отправить сообщение об ошибке (update_id=%s)", update.update_id)
    return True
