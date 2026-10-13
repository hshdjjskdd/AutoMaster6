"""Профиль игрока."""

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app import texts
from app.keyboards import BUTTON_PROFILE
from app.services import PlayerService

router = Router(name="profile")
router.message.filter(F.chat.type == ChatType.PRIVATE)


@router.message(Command("profile"))
@router.message(F.text == BUTTON_PROFILE)
async def show_profile(message: Message, session: AsyncSession) -> None:
    user = message.from_user
    if user is None:
        return

    profile = await PlayerService(session).get_profile(user.id)
    if profile is None:
        await message.answer(texts.NOT_REGISTERED_TEXT)
        return
    await message.answer(texts.render_profile(profile))
