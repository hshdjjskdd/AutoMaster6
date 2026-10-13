"""Команда /start: регистрация игрока и показ главного меню."""

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app import texts
from app.keyboards import main_menu_keyboard
from app.schemas import TelegramUserData
from app.services import PlayerService

router = Router(name="start")
router.message.filter(F.chat.type == ChatType.PRIVATE)


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession) -> None:
    user = message.from_user
    if user is None:
        return

    result = await PlayerService(session).register_or_update(
        TelegramUserData(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
        )
    )
    text = (
        texts.render_welcome_new(result.profile)
        if result.is_new
        else texts.render_welcome_back(result.profile)
    )
    await message.answer(text, reply_markup=main_menu_keyboard())
