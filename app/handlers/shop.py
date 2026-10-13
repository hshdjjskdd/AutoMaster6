"""Магазин запчастей и склад."""

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app import texts, texts_repair as tr
from app.exceptions import DomainError
from app.game_data.part_catalog import PART_TYPE_BY_CODE, SECTIONS
from app.keyboards import BUTTON_SHOP, BUTTON_STOCK
from app.keyboards import shop as kb
from app.keyboards.callbacks import ShopCb
from app.repositories import FinanceRepository
from app.services import PlayerService, ShopService

router = Router(name="shop")
router.message.filter(F.chat.type == ChatType.PRIVATE)


async def _edit(callback: CallbackQuery, text: str, markup: InlineKeyboardMarkup | None) -> None:
    if not isinstance(callback.message, Message):
        return
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest:
        pass


async def _home(session: AsyncSession, player_id: int) -> tuple[str, InlineKeyboardMarkup]:
    balance = await FinanceRepository(session).get_balance(player_id)
    orders = await ShopService(session).list_orders(player_id)
    return tr.render_shop_home(balance or 0), kb.shop_home_keyboard(bool(orders))


async def _stock(session: AsyncSession, player_id: int) -> tuple[str, InlineKeyboardMarkup]:
    lines = await ShopService(session).inventory(player_id)
    balance = await FinanceRepository(session).get_balance(player_id)
    return tr.render_inventory(lines, balance or 0), kb.stock_keyboard()


@router.message(Command("shop"))
@router.message(F.text == BUTTON_SHOP)
async def show_shop(message: Message, session: AsyncSession) -> None:
    user = message.from_user
    if user is None:
        return
    player_id = await PlayerService(session).get_player_id(user.id)
    if player_id is None:
        await message.answer(texts.NOT_REGISTERED_TEXT)
        return
    text, markup = await _home(session, player_id)
    await message.answer(text, reply_markup=markup)


@router.message(Command("stock"))
@router.message(F.text == BUTTON_STOCK)
async def show_stock(message: Message, session: AsyncSession) -> None:
    user = message.from_user
    if user is None:
        return
    player_id = await PlayerService(session).get_player_id(user.id)
    if player_id is None:
        await message.answer(texts.NOT_REGISTERED_TEXT)
        return
    text, markup = await _stock(session, player_id)
    await message.answer(text, reply_markup=markup)


@router.callback_query(ShopCb.filter())
async def shop_action(callback: CallbackQuery, callback_data: ShopCb, session: AsyncSession) -> None:
    player_id = await PlayerService(session).get_player_id(callback.from_user.id)
    if player_id is None:
        await callback.answer(texts.NOT_REGISTERED_TEXT, show_alert=True)
        return
    service = ShopService(session)
    action = callback_data.action
    notice: str | None = None
    try:
        if action == "sec":
            idx = int(callback_data.a)
            if not 0 <= idx < len(SECTIONS):
                await callback.answer()
                return
            balance = await FinanceRepository(session).get_balance(player_id)
            await _edit(callback, tr.render_section(SECTIONS[idx], balance or 0), kb.section_keyboard(idx))
        elif action in ("type", "buy"):
            ptype = PART_TYPE_BY_CODE.get(callback_data.a)
            if ptype is None:
                await callback.answer()
                return
            order_id = callback_data.order
            if action == "buy":
                result = await service.buy(
                    player_id=player_id,
                    type_code=ptype.code,
                    quality=callback_data.q,
                    quantity=callback_data.n,
                    order_id=order_id,
                    ver=callback_data.ver,
                )
                notice = (
                    "Эта покупка уже проведена, деньги не списаны повторно."
                    if result.duplicate
                    else f"Куплено ×{result.quantity}. Остаток: {result.balance_after} ₽"
                )
            if not ptype.universal and not order_id:
                orders = await service.list_orders(player_id)
                if not orders:
                    await callback.answer(
                        "Деталь подбирается под автомобиль: сначала прими заказ.", show_alert=True
                    )
                    return
                if len(orders) > 1:
                    await _edit(
                        callback,
                        "🚗 <b>Для какого автомобиля подбираем деталь?</b>",
                        kb.order_choice_keyboard(ptype.code, orders),
                    )
                    await callback.answer()
                    return
                order_id = orders[0].order_id
            view = await service.type_view(player_id, ptype.code, order_id)
            await _edit(callback, tr.render_type(view), kb.type_keyboard(view))
        elif action == "stock":
            text, markup = await _stock(session, player_id)
            await _edit(callback, text, markup)
        elif action == "orders":
            orders = await service.list_orders(player_id)
            await _edit(
                callback,
                "🧩 <b>Подбор по заказу</b>\nВыбери заказ — покажу, какие детали нужны и чего не хватает.",
                kb.orders_keyboard(orders),
            )
        elif action == "plan":
            plan = await service.order_plan(player_id, callback_data.order)
            await _edit(callback, tr.render_plan(plan), kb.plan_keyboard(plan))
        else:
            text, markup = await _home(session, player_id)
            await _edit(callback, text, markup)
    except DomainError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer(notice)
