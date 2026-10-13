"""Обработка неизвестных команд и любых нераспознанных сообщений.

Роутер подключается последним: сюда попадает только то, что не поймали остальные.
"""

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.types import Message

from app import texts

router = Router(name="fallback")
router.message.filter(F.chat.type == ChatType.PRIVATE)


@router.message(F.text.startswith("/"))
async def unknown_command(message: Message) -> None:
    await message.answer(texts.UNKNOWN_COMMAND_TEXT)


@router.message()
async def unknown_message(message: Message) -> None:
    await message.answer(texts.UNKNOWN_MESSAGE_TEXT)
