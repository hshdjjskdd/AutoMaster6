"""Главное меню и справка."""

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app import texts
from app.keyboards import BUTTON_HELP, main_menu_keyboard
from app.services import PlayerService

router = Router(name="menu")
router.message.filter(F.chat.type == ChatType.PRIVATE)


@router.message(Command("menu"))
async def cmd_menu(message: Message, session: AsyncSession) -> None:
    user = message.from_user
    if user is None:
        return

    profile = await PlayerService(session).get_profile(user.id)
    if profile is None:
        await message.answer(texts.NOT_REGISTERED_TEXT)
        return
    await message.answer(texts.MAIN_MENU_TEXT, reply_markup=main_menu_keyboard())


@router.message(Command("help"))
@router.message(F.text == BUTTON_HELP)
async def cmd_help(message: Message) -> None:
    await message.answer(texts.HELP_TEXT)
