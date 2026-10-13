"""Inline-клавиатуры заказов и мастерской."""

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.game_data.economy import TIER_EMOJI
from app.game_data.enums import OrderStatus
from app.game_data.labels import ORDER_STATUS_TITLES
from app.keyboards.callbacks import DiagCb, RepairCb
from app.schemas import Board, WorkshopOrderCard


class OfferCb(CallbackData, prefix="off"):
    action: str  # open | accept | decline | board
    offer_id: int = 0


class WorkshopCb(CallbackData, prefix="wsh"):
    action: str  # list | open | cancel | cancel_yes
    order_id: int = 0


def board_keyboard(board: Board) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for idx, offer in enumerate(board.offers, 1):
        kb.button(
            text=f"{idx}. {TIER_EMOJI.get(offer.tier, '🟢')} {offer.car.brand} {offer.car.model}",
            callback_data=OfferCb(action="open", offer_id=offer.offer_id),
        )
        kb.button(text="✅ Принять", callback_data=OfferCb(action="accept", offer_id=offer.offer_id))
    kb.button(text="🔄 Обновить", callback_data=OfferCb(action="board"))
    kb.adjust(*([2] * len(board.offers)), 1)
    return kb.as_markup()


def notice_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🚗 Открыть заказы", callback_data=OfferCb(action="board"))
    return kb.as_markup()


def offer_keyboard(offer_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Принять", callback_data=OfferCb(action="accept", offer_id=offer_id))
    kb.button(text="❌ Отказаться", callback_data=OfferCb(action="decline", offer_id=offer_id))
    kb.button(text="⬅️ К списку", callback_data=OfferCb(action="board"))
    kb.adjust(2, 1)
    return kb.as_markup()


def workshop_list_keyboard(orders: list[WorkshopOrderCard]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for order in orders:
        kb.button(
            text=f"№{order.order_id} {order.car.model} — {ORDER_STATUS_TITLES[order.status]}",
            callback_data=WorkshopCb(action="open", order_id=order.order_id),
        )
    kb.adjust(1)
    return kb.as_markup()


def workshop_order_keyboard(order: WorkshopOrderCard) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if order.status in (
        OrderStatus.NEW, OrderStatus.DIAGNOSTICS, OrderStatus.AWAITING_PARTS, OrderStatus.IN_REPAIR
    ):
        kb.button(
            text="🔧 Диагностика",
            callback_data=DiagCb(action="menu", order_id=order.order_id),
        )
    if order.status in (
        OrderStatus.DIAGNOSTICS, OrderStatus.AWAITING_PARTS, OrderStatus.IN_REPAIR, OrderStatus.READY
    ):
        kb.button(
            text="🛠 Ремонт",
            callback_data=RepairCb(action="open", order_id=order.order_id),
        )
    if order.cancel_penalty is not None:
        kb.button(
            text="🚫 Отменить заказ",
            callback_data=WorkshopCb(action="cancel", order_id=order.order_id),
        )
    kb.button(text="⬅️ К мастерской", callback_data=WorkshopCb(action="list"))
    kb.adjust(1)
    return kb.as_markup()


def cancel_confirm_keyboard(order_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Да, отменить", callback_data=WorkshopCb(action="cancel_yes", order_id=order_id))
    kb.button(text="Нет", callback_data=WorkshopCb(action="open", order_id=order_id))
    kb.adjust(2)
    return kb.as_markup()
