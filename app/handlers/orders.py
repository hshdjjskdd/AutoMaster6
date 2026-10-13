"""Доска клиентских заказов: список, карточка, принятие, отказ."""

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app import texts, texts_orders
from app.exceptions import DomainError
from app.keyboards import BUTTON_FINANCE, BUTTON_ORDERS
from app.keyboards.orders import OfferCb, board_keyboard, offer_keyboard
from app.services import ClientOrderService, EconomyService, PlayerService

router = Router(name="orders")
router.message.filter(F.chat.type == ChatType.PRIVATE)


async def _edit(callback: CallbackQuery, text: str, markup: InlineKeyboardMarkup | None) -> None:
    if not isinstance(callback.message, Message):
        return
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest:
        # «message is not modified» и подобное — не ошибка для игрока.
        pass


@router.message(Command("orders"))
@router.message(F.text == BUTTON_ORDERS)
async def show_board(message: Message, session: AsyncSession) -> None:
    user = message.from_user
    if user is None:
        return
    player_id = await PlayerService(session).get_player_id(user.id)
    if player_id is None:
        await message.answer(texts.NOT_REGISTERED_TEXT)
        return
    board = await ClientOrderService(session).get_board(player_id)
    await message.answer(texts_orders.render_board(board), reply_markup=board_keyboard(board))


@router.callback_query(OfferCb.filter())
async def offer_action(callback: CallbackQuery, callback_data: OfferCb, session: AsyncSession) -> None:
    player_id = await PlayerService(session).get_player_id(callback.from_user.id)
    if player_id is None:
        await callback.answer(texts.NOT_REGISTERED_TEXT, show_alert=True)
        return
    service = ClientOrderService(session)
    try:
        if callback_data.action == "open":
            offer = await service.get_offer(player_id, callback_data.offer_id)
            await _edit(callback, texts_orders.render_offer(offer), offer_keyboard(offer.offer_id))
        elif callback_data.action == "accept":
            result = await service.accept_offer(player_id, callback_data.offer_id)
            await _edit(callback, texts_orders.render_accepted(result.order_id), None)
        elif callback_data.action == "decline":
            await service.decline_offer(player_id, callback_data.offer_id)
            board = await service.get_board(player_id)
            await _edit(callback, texts_orders.render_board(board), board_keyboard(board))
        else:
            board = await service.get_board(player_id)
            await _edit(callback, texts_orders.render_board(board), board_keyboard(board))
    except DomainError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer()


@router.message(Command("finance"))
@router.message(F.text == BUTTON_FINANCE)
async def show_finance(message: Message, session: AsyncSession) -> None:
    user = message.from_user
    if user is None:
        return
    player_id = await PlayerService(session).get_player_id(user.id)
    if player_id is None:
        await message.answer(texts.NOT_REGISTERED_TEXT)
        return
    summary = await EconomyService(session).summary(player_id)
    await message.answer(texts_orders.render_finance(summary))
