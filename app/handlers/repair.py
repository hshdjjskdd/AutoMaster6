"""Ремонт: операции, проверка результата, сдача заказа."""

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app import texts, texts_repair as tr
from app.exceptions import DomainError
from app.keyboards import shop as kb
from app.keyboards.callbacks import RepairCb
from app.services import PlayerService, RepairService

router = Router(name="repair")


async def _edit(callback: CallbackQuery, text: str, markup: InlineKeyboardMarkup | None) -> None:
    if not isinstance(callback.message, Message):
        return
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest:
        pass


@router.callback_query(RepairCb.filter())
async def repair_action(callback: CallbackQuery, callback_data: RepairCb, session: AsyncSession) -> None:
    player_id = await PlayerService(session).get_player_id(callback.from_user.id)
    if player_id is None:
        await callback.answer(texts.NOT_REGISTERED_TEXT, show_alert=True)
        return
    service = RepairService(session)
    oid = callback_data.order_id
    action = callback_data.action
    try:
        if action == "do":
            result = await service.perform_operation(
                player_id=player_id, order_id=oid, op_code=callback_data.arg
            )
            await _edit(callback, tr.render_operation(result), kb.repair_back_keyboard(oid))
        elif action == "verify":
            result_v = await service.verify(player_id=player_id, order_id=oid)
            await _edit(callback, tr.render_verification(result_v), kb.repair_back_keyboard(oid))
        elif action == "finish":
            result_f = await service.finish(player_id=player_id, order_id=oid)
            await _edit(callback, tr.render_finish(result_f), None)
        else:
            overview = await service.get_overview(player_id, oid)
            await _edit(callback, tr.render_repair(overview), kb.repair_keyboard(overview))
    except DomainError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer()
