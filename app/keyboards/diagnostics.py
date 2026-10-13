"""Inline-клавиатуры диагностики."""

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.game_data.diagnostic_checks import CHECK_GROUPS
from app.game_data.fault_catalog import CAUSES
from app.keyboards.callbacks import DiagCb
from app.keyboards.orders import WorkshopCb
from app.schemas import CheckOption, CheckRunView, DiagnosticOverview, ToolOption
from app.utils.formatting import format_money

MAX_CONCLUSION = 3


def _fee_label(option: CheckOption) -> str:
    return "бесплатно" if option.fee == 0 else format_money(option.fee)


def _back_to_order(kb: InlineKeyboardBuilder, order_id: int) -> None:
    kb.button(text="⬅️ К заказу", callback_data=WorkshopCb(action="open", order_id=order_id))


def menu_keyboard(overview: DiagnosticOverview) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    oid = overview.order_id
    if overview.can_run:
        for group in CHECK_GROUPS:
            for option in overview.options:
                if option.group != group:
                    continue
                kb.button(
                    text=f"{option.emoji} {option.title} · {option.minutes} мин · {_fee_label(option)}",
                    callback_data=DiagCb(action="info", order_id=oid, arg=option.code),
                )
    kb.adjust(1)
    footer = InlineKeyboardBuilder()
    footer.button(text="📒 Журнал", callback_data=DiagCb(action="journal", order_id=oid))
    footer.button(text="🧰 Инструменты", callback_data=DiagCb(action="tools", order_id=oid))
    if overview.can_run and overview.runs > 0:
        footer.button(text="📝 Заключение", callback_data=DiagCb(action="concl", order_id=oid))
    footer.adjust(2)
    kb.attach(footer)
    back = InlineKeyboardBuilder()
    _back_to_order(back, oid)
    kb.attach(back)
    return kb.as_markup()


def check_info_keyboard(order_id: int, option: CheckOption, runs: int, can_run: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if can_run:
        kb.button(
            text=f"▶️ Выполнить ({_fee_label(option)})",
            callback_data=DiagCb(action="run", order_id=order_id, arg=option.code, n=runs),
        )
    kb.button(text="⬅️ К проверкам", callback_data=DiagCb(action="menu", order_id=order_id))
    kb.adjust(1)
    return kb.as_markup()


def run_result_keyboard(order_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Ещё проверка", callback_data=DiagCb(action="menu", order_id=order_id))
    kb.button(text="📒 Журнал", callback_data=DiagCb(action="journal", order_id=order_id))
    kb.adjust(1)
    return kb.as_markup()


def journal_keyboard(order_id: int, runs: list[CheckRunView]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for run in runs[-10:]:
        kb.button(
            text=f"№{run.run_no} {run.emoji} {run.title}",
            callback_data=DiagCb(action="entry", order_id=order_id, n=run.run_no),
        )
    kb.adjust(1)
    footer = InlineKeyboardBuilder()
    footer.button(text="⬅️ К проверкам", callback_data=DiagCb(action="menu", order_id=order_id))
    kb.attach(footer)
    return kb.as_markup()


def entry_keyboard(order_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ К журналу", callback_data=DiagCb(action="journal", order_id=order_id))
    return kb.as_markup()


def selected_causes(mask: int) -> list[int]:
    return [i for i in range(len(CAUSES)) if mask >> i & 1]


SYSTEMS: tuple[str, ...] = tuple(dict.fromkeys(c.system for c in CAUSES))
_SYSTEM_MENU_THRESHOLD = 12


def system_of(cause_index: int) -> int:
    return SYSTEMS.index(CAUSES[cause_index].system)


def conclusion_keyboard(
    order_id: int, mask: int, allowed: list[int] | None = None, system: int | None = None
) -> InlineKeyboardMarkup:
    """Выбор причин. Показываются только возможные для машины причины (allowed);
    когда их много, сначала выбирается система автомобиля."""
    indices = list(range(len(CAUSES))) if allowed is None else allowed
    kb = InlineKeyboardBuilder()
    by_system = system is None and len(indices) > _SYSTEM_MENU_THRESHOLD
    if by_system:
        for sys_idx, title in enumerate(SYSTEMS):
            members = [i for i in indices if system_of(i) == sys_idx]
            if not members:
                continue
            chosen = sum(1 for i in members if mask >> i & 1)
            mark = f" · выбрано {chosen}" if chosen else ""
            kb.button(
                text=f"{title} ({len(members)}){mark}",
                callback_data=DiagCb(action="concl", order_id=order_id, arg=f"s{sys_idx}", n=mask),
            )
    else:
        for idx in indices:
            if system is not None and system_of(idx) != system:
                continue
            mark = "☑️" if mask >> idx & 1 else "☐"
            kb.button(
                text=f"{mark} {CAUSES[idx].name}",
                callback_data=DiagCb(action="tog", order_id=order_id, arg=str(idx), n=mask),
            )
    kb.adjust(1)
    footer = InlineKeyboardBuilder()
    if system is not None:
        footer.button(
            text="⬅️ К системам", callback_data=DiagCb(action="concl", order_id=order_id, n=mask)
        )
    if mask:
        footer.button(
            text="✅ Записать заключение",
            callback_data=DiagCb(action="concl_ok", order_id=order_id, n=mask),
        )
    footer.button(text="⬅️ К проверкам", callback_data=DiagCb(action="menu", order_id=order_id))
    footer.adjust(1)
    kb.attach(footer)
    return kb.as_markup()


def tools_keyboard(order_id: int, tools: list[ToolOption]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for tool in tools:
        if not tool.owned:
            kb.button(
                text=f"Купить: {tool.title} — {format_money(tool.price)}",
                callback_data=DiagCb(action="buy", order_id=order_id, arg=tool.code),
            )
    kb.button(text="⬅️ К проверкам", callback_data=DiagCb(action="menu", order_id=order_id))
    kb.adjust(1)
    return kb.as_markup()


def done_keyboard(order_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📒 Журнал", callback_data=DiagCb(action="journal", order_id=order_id))
    _back_to_order(kb, order_id)
    kb.adjust(1)
    return kb.as_markup()
