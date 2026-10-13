"""Inline-клавиатуры магазина, склада и ремонта."""

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.game_data.part_catalog import SECTION_EMOJI, SECTIONS, types_in_section
from app.keyboards.callbacks import DiagCb, RepairCb, ShopCb
from app.keyboards.orders import WorkshopCb
from app.schemas import OrderPartsPlan, RepairOverview, ShopOrderOption, ShopTypeView
from app.utils.formatting import format_money

QUANTITIES = (1, 2, 4)


def shop_home_keyboard(has_orders: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for idx, section in enumerate(SECTIONS):
        kb.button(
            text=f"{SECTION_EMOJI.get(section, '🔩')} {section}",
            callback_data=ShopCb(action="sec", a=str(idx)),
        )
    kb.adjust(2)
    footer = InlineKeyboardBuilder()
    footer.button(text="📦 Склад", callback_data=ShopCb(action="stock"))
    if has_orders:
        footer.button(text="🧩 Подбор по заказу", callback_data=ShopCb(action="orders"))
    footer.adjust(1)
    kb.attach(footer)
    return kb.as_markup()


def section_keyboard(section_idx: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for ptype in types_in_section(SECTIONS[section_idx]):
        kb.button(text=ptype.name, callback_data=ShopCb(action="type", a=ptype.code))
    kb.button(text="⬅️ В магазин", callback_data=ShopCb(action="home"))
    kb.adjust(1)
    return kb.as_markup()


def order_choice_keyboard(type_code: str, orders: list[ShopOrderOption]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for option in orders:
        kb.button(
            text=f"№{option.order_id} {option.car_title}",
            callback_data=ShopCb(action="type", a=type_code, order=option.order_id),
        )
    kb.button(text="⬅️ В магазин", callback_data=ShopCb(action="home"))
    kb.adjust(1)
    return kb.as_markup()


def type_keyboard(view: ShopTypeView) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for q in view.qualities:
        for qty in QUANTITIES:
            kb.button(
                text=f"{q.emoji} ×{qty} · {format_money(q.price * qty)}",
                callback_data=ShopCb(
                    action="buy", a=view.type_code, order=view.order_id, q=q.level, n=qty, ver=view.ver
                ),
            )
    kb.adjust(*([len(QUANTITIES)] * len(view.qualities)))
    footer = InlineKeyboardBuilder()
    footer.button(text="📦 Склад", callback_data=ShopCb(action="stock"))
    footer.button(text="⬅️ В магазин", callback_data=ShopCb(action="home"))
    footer.adjust(2)
    kb.attach(footer)
    return kb.as_markup()


def stock_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🛒 В магазин", callback_data=ShopCb(action="home"))
    return kb.as_markup()


def orders_keyboard(orders: list[ShopOrderOption]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for option in orders:
        kb.button(
            text=f"№{option.order_id} {option.car_title}",
            callback_data=ShopCb(action="plan", order=option.order_id),
        )
    kb.button(text="⬅️ В магазин", callback_data=ShopCb(action="home"))
    kb.adjust(1)
    return kb.as_markup()


def plan_keyboard(plan: OrderPartsPlan) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    seen: set[str] = set()
    for line in plan.lines:
        if line.missing and line.type_code not in seen:
            seen.add(line.type_code)
            kb.button(
                text=f"🛒 {line.part_name}",
                callback_data=ShopCb(action="type", a=line.type_code, order=plan.order_id),
            )
    kb.button(text="🛠 К ремонту", callback_data=RepairCb(action="open", order_id=plan.order_id))
    kb.adjust(1)
    return kb.as_markup()


def repair_keyboard(overview: RepairOverview) -> InlineKeyboardMarkup:
    oid = overview.order_id
    kb = InlineKeyboardBuilder()
    if overview.can_repair:
        for fault in overview.faults:
            for op in fault.ops:
                if not op.done:
                    mark = "🔧" if op.can_perform else "🔒"
                    kb.button(
                        text=f"{mark} {op.title}",
                        callback_data=RepairCb(action="do", order_id=oid, arg=op.code),
                    )
        if overview.faults:
            kb.button(text="🧩 Подбор деталей", callback_data=ShopCb(action="plan", order=oid))
    if overview.can_verify:
        kb.button(text="🧪 Проверить результат", callback_data=RepairCb(action="verify", order_id=oid))
    if overview.can_finish:
        kb.button(text="🏁 Сдать заказ", callback_data=RepairCb(action="finish", order_id=oid))
    if overview.diagnostics_open and overview.can_repair:
        kb.button(text="🔍 Диагностика", callback_data=DiagCb(action="menu", order_id=oid))
    kb.button(text="⬅️ К заказу", callback_data=WorkshopCb(action="open", order_id=oid))
    kb.adjust(1)
    return kb.as_markup()


def repair_back_keyboard(order_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🛠 К ремонту", callback_data=RepairCb(action="open", order_id=order_id))
    kb.adjust(1)
    return kb.as_markup()
