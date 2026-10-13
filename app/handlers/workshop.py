"""Мастерская: активные заказы, карточка заказа, отмена."""

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app import texts, texts_orders
from app.exceptions import DomainError
from app.keyboards import BUTTON_WORKSHOP
from app.keyboards.orders import (
    WorkshopCb,
    cancel_confirm_keyboard,
    workshop_list_keyboard,
    workshop_order_keyboard,
)
from app.services import ClientOrderService, PlayerService

router = Router(name="workshop")
router.message.filter(F.chat.type == ChatType.PRIVATE)


async def _edit(callback: CallbackQuery, text: str, markup: InlineKeyboardMarkup | None) -> None:
    if not isinstance(callback.message, Message):
        return
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest:
        pass


async def _render_list(service: ClientOrderService, player_id: int) -> tuple[str, InlineKeyboardMarkup | None]:
    orders = await service.list_workshop(player_id)
    if not orders:
        return texts_orders.EMPTY_WORKSHOP_TEXT, None
    return texts_orders.render_workshop_list(orders), workshop_list_keyboard(orders)


@router.message(Command("workshop"))
@router.message(F.text == BUTTON_WORKSHOP)
async def show_workshop(message: Message, session: AsyncSession) -> None:
    user = message.from_user
    if user is None:
        return
    player_id = await PlayerService(session).get_player_id(user.id)
    if player_id is None:
        await message.answer(texts.NOT_REGISTERED_TEXT)
        return
    text, markup = await _render_list(ClientOrderService(session), player_id)
    await message.answer(text, reply_markup=markup)


@router.callback_query(WorkshopCb.filter())
async def workshop_action(
    callback: CallbackQuery, callback_data: WorkshopCb, session: AsyncSession
) -> None:
    player_id = await PlayerService(session).get_player_id(callback.from_user.id)
    if player_id is None:
        await callback.answer(texts.NOT_REGISTERED_TEXT, show_alert=True)
        return
    service = ClientOrderService(session)
    order_id = callback_data.order_id
    notice: str | None = None
    try:
        if callback_data.action == "open":
            order = await service.get_workshop_order(player_id, order_id)
            await _edit(
                callback, texts_orders.render_workshop_order(order), workshop_order_keyboard(order)
            )
        elif callback_data.action == "cancel":
            order = await service.get_workshop_order(player_id, order_id)
            if order.cancel_penalty is None:
                await callback.answer("Отмена на этом этапе недоступна.", show_alert=True)
                return
            await _edit(
                callback, texts_orders.render_cancel_confirm(order), cancel_confirm_keyboard(order_id)
            )
        elif callback_data.action == "cancel_yes":
            result = await service.cancel_order(player_id, order_id)
            notice = (
                f"Заказ №{order_id} отменён."
                if not result.reputation_penalty
                else f"Заказ №{order_id} отменён. Репутация −{result.reputation_penalty}."
            )
            text, markup = await _render_list(service, player_id)
            await _edit(callback, text, markup)
        else:
            text, markup = await _render_list(service, player_id)
            await _edit(callback, text, markup)
    except DomainError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer(notice)
