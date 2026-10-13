"""Диагностика через inline-меню: проверки, журнал, инструменты, заключение."""

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app import texts, texts_diagnostics as td
from app.exceptions import DomainError
from app.game_data.fault_catalog import CAUSES
from app.keyboards import diagnostics as kb
from app.keyboards.callbacks import DiagCb
from app.services import DiagnosticService, InventoryService, PlayerService

router = Router(name="diagnostics")


async def _edit(callback: CallbackQuery, text: str, markup: InlineKeyboardMarkup | None) -> None:
    if not isinstance(callback.message, Message):
        return
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest:
        pass  # «message is not modified» — не ошибка для игрока


async def _show_menu(callback: CallbackQuery, service: DiagnosticService, player_id: int, order_id: int) -> None:
    overview = await service.get_overview(player_id, order_id)
    await _edit(callback, td.render_menu(overview), kb.menu_keyboard(overview))


@router.callback_query(DiagCb.filter())
async def diagnostics_action(
    callback: CallbackQuery, callback_data: DiagCb, session: AsyncSession
) -> None:
    player_id = await PlayerService(session).get_player_id(callback.from_user.id)
    if player_id is None:
        await callback.answer(texts.NOT_REGISTERED_TEXT, show_alert=True)
        return
    service = DiagnosticService(session)
    oid = callback_data.order_id
    action = callback_data.action
    notice: str | None = None
    try:
        if action == "menu":
            await _show_menu(callback, service, player_id, oid)
        elif action == "info":
            overview = await service.get_overview(player_id, oid)
            option = await service.get_check_option(player_id, oid, callback_data.arg)
            await _edit(
                callback,
                td.render_check_info(option, runs=overview.runs),
                kb.check_info_keyboard(oid, option, overview.runs, overview.can_run),
            )
        elif action == "run":
            run = await service.run_check(
                player_id=player_id,
                order_id=oid,
                check_code=callback_data.arg,
                expected_runs=callback_data.n,
            )
            await _edit(callback, td.render_run(run, fresh=True), kb.run_result_keyboard(oid))
        elif action == "journal":
            runs = await service.get_journal(player_id, oid)
            await _edit(callback, td.render_journal(oid, runs), kb.journal_keyboard(oid, runs))
        elif action == "entry":
            run = await service.get_run(player_id, oid, callback_data.n)
            await _edit(callback, td.render_run(run), kb.entry_keyboard(oid))
        elif action in ("concl", "tog"):
            mask = callback_data.n
            system: int | None = None
            if action == "tog":
                idx = int(callback_data.arg)
                bit = 1 << idx
                if not mask & bit and len(kb.selected_causes(mask)) >= td.CONCLUSION_LIMIT:
                    await callback.answer(
                        f"Можно выбрать не более {td.CONCLUSION_LIMIT} причин.", show_alert=True
                    )
                    return
                mask ^= bit
                system = kb.system_of(idx)
            elif callback_data.arg.startswith("s"):
                system = int(callback_data.arg[1:])
            allowed = await service.conclusion_causes(player_id, oid)
            await _edit(
                callback,
                td.render_conclusion_form(kb.selected_causes(mask)),
                kb.conclusion_keyboard(oid, mask, allowed, system),
            )
        elif action == "concl_ok":
            codes = [CAUSES[i].code for i in kb.selected_causes(callback_data.n)]
            result = await service.conclude(player_id=player_id, order_id=oid, cause_codes=codes)
            await _edit(callback, td.render_conclusion_done(result), kb.done_keyboard(oid))
        elif action in ("tools", "buy"):
            if action == "buy":
                bought = await InventoryService(session).buy_equipment(
                    player_id=player_id, code=callback_data.arg
                )
                notice = f"Куплено. Остаток: {bought.balance_after} ₽"
            tools = await service.list_tools(player_id)
            await _edit(callback, td.render_tools(tools), kb.tools_keyboard(oid, tools))
        else:
            await callback.answer()
            return
    except DomainError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer(notice)
