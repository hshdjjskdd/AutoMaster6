"""Тексты магазина, склада и ремонта (HTML-разметка Telegram)."""

from datetime import UTC, datetime
from html import escape

from app.game_data.labels import ORDER_STATUS_TITLES
from app.game_data.part_catalog import SECTION_EMOJI
from app.schemas import (
    FinishResult,
    OperationResult,
    OrderPartsPlan,
    RepairOverview,
    ShopTypeView,
    StockLine,
    VerificationResult,
)
from app.texts_diagnostics import format_minutes
from app.utils.formatting import format_money

SHOP_HOME_TEXT = (
    "🛒 <b>Магазин запчастей</b>\n\n"
    "Выбери раздел. Каждая деталь продаётся в трёх вариантах: 🥉 бюджетный, "
    "🥈 качественный аналог и 🥇 оригинал. Деталь подбирается под автомобиль заказа — "
    "несовместимую поставить нельзя."
)


def render_shop_home(balance: int) -> str:
    return f"{SHOP_HOME_TEXT}\n\n💰 На счёте: <b>{format_money(balance)}</b>"


def render_section(section: str, balance: int) -> str:
    emoji = SECTION_EMOJI.get(section, "🔩")
    return f"{emoji} <b>{escape(section)}</b>\nВыбери деталь.\n\n💰 На счёте: {format_money(balance)}"


def render_type(view: ShopTypeView) -> str:
    lines = [f"🔩 <b>{escape(view.name)}</b>", f"<i>{escape(view.section)}</i>"]
    if view.car_title:
        lines.append(f"🚗 Под автомобиль заказа №{view.order_id}: {escape(view.car_title)}")
    lines.append(f"✅ Совместимость: {escape(view.fit_label)}")
    if view.models:
        lines.append("Подходит также: " + ", ".join(escape(m) for m in view.models))
    lines.append("")
    for q in view.qualities:
        stock = f" · на складе: {q.stock}" if q.stock else ""
        lines.append(f"{q.emoji} <b>{escape(q.title)}</b> — {format_money(q.price)}{stock}")
        lines.append(f"    <i>{escape(q.note)}</i>")
    lines += ["", f"💰 На счёте: <b>{format_money(view.balance)}</b>"]
    return "\n".join(lines)


def render_inventory(lines: list[StockLine], balance: int) -> str:
    out = ["📦 <b>Склад</b>", ""]
    if not lines:
        out.append("Пусто. Закупись в «🛒 Магазине».")
    section = None
    for line in lines:
        if line.section != section:
            section = line.section
            out.append(f"{SECTION_EMOJI.get(section, '🔩')} <b>{escape(section)}</b>")
        mark = f"{line.quality_emoji} " if line.quality_emoji else ""
        out.append(f"  {mark}{escape(line.name)} — <b>{line.quantity}</b> шт.")
    out += ["", f"💰 На счёте: {format_money(balance)}"]
    return "\n".join(out)


def render_plan(plan: OrderPartsPlan) -> str:
    lines = [f"🧩 <b>Подбор деталей · заказ №{plan.order_id}</b>", f"🚗 {escape(plan.car_title)}", ""]
    if not plan.lines:
        lines.append("Для оставшихся операций детали не нужны (или неисправности ещё не внесены).")
    for item in plan.lines:
        status = "✅ есть" if item.missing == 0 else f"❌ не хватает {item.missing}"
        lines.append(
            f"• {escape(item.part_name)} ×{item.qty} — {status}\n"
            f"    <i>{escape(item.op_title)} · от {format_money(item.unit_price)}</i>"
        )
    lines += ["", f"💰 На счёте: {format_money(plan.balance)}"]
    return "\n".join(lines)


def render_repair(overview: RepairOverview, *, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    lines = [
        f"🛠 <b>Ремонт · заказ №{overview.order_id}</b>",
        f"🚗 {escape(overview.car_title)} · <code>{escape(overview.plate)}</code>",
        f"💬 Жалоба: «{escape(overview.complaint)}»",
        f"Статус: {ORDER_STATUS_TITLES[overview.status]}",
    ]
    if overview.deadline_at is not None:
        left = int((overview.deadline_at - now).total_seconds() // 60)
        lines.append(
            f"⌛ До срока: {format_minutes(left)}" if left > 0 else "⌛ Срок вышел — премии не будет"
        )
    lines.append("")
    if not overview.faults:
        lines.append(
            "Неисправности ещё не внесены. Проведи диагностику и запиши заключение."
        )
    for fault in overview.faults:
        mark = "✅" if fault.resolved else "🔧"
        lines.append(f"{mark} <b>{escape(fault.name)}</b> <i>({escape(fault.system)})</i>")
        for op in fault.ops:
            op_mark = "✔️" if op.done else "▫️"
            lines.append(f"  {op_mark} {escape(op.title)} · {op.minutes} мин")
            if not op.done:
                for need in op.needs:
                    ok = "✅" if need.enough else "❌"
                    lines.append(
                        f"      {ok} {escape(need.name)} ×{need.qty} (на складе: {need.in_stock})"
                    )
    lines.append("")
    if overview.can_finish:
        lines.append("🏁 Результат проверен — заказ можно сдавать клиенту.")
    elif overview.can_verify:
        lines.append("Все внесённые неисправности устранены. Проверь результат тест-драйвом.")
    elif overview.diagnostics_open and overview.faults:
        lines.append(
            "🔁 Жалоба клиента сохранилась: диагностика снова открыта — найди оставшуюся причину."
        )
    lines.append(f"💰 На счёте: {format_money(overview.balance)}")
    return "\n".join(lines)


def render_operation(result: OperationResult) -> str:
    lines = [f"🔧 <b>Выполнено:</b> {escape(result.title)}", f"⏱ −{result.minutes} мин"]
    for part in result.parts:
        lines.append(f"📤 Списано: {escape(part.name)} ×{part.qty}")
    if result.fault_resolved:
        lines.append("✅ Неисправность устранена.")
    if result.all_resolved:
        lines.append("\nВсё внесённое устранено — проверь результат.")
    return "\n".join(lines)


def render_verification(result: VerificationResult) -> str:
    if result.ok:
        return (
            f"🧪 <b>Тест-драйв пройден</b> (−{result.minutes} мин)\n\n"
            "Жалоба клиента устранена. Заказ готов к выдаче."
        )
    return (
        f"🧪 <b>Тест-драйв не пройден</b> (−{result.minutes} мин)\n\n"
        "Симптом остался: ремонт устранил не ту причину. Замененные детали вернуть нельзя. "
        "Диагностика снова открыта — продолжай проверки и запиши новое заключение."
    )


def render_finish(result: FinishResult) -> str:
    if result.already_completed:
        return "🏁 Этот заказ уже сдан — награда была начислена ранее."
    lines = [
        "🏁 <b>Заказ сдан клиенту</b>",
        f"💰 Выручка: <b>{format_money(result.reward_paid)}</b>"
        + (f" (в т. ч. премия {format_money(result.bonus)})" if result.bonus else ""),
        f"🔧 Расходы: {format_money(result.parts_cost)}",
        f"📈 Чистая прибыль: <b>{format_money(result.profit)}</b>",
        f"⭐ Опыт: +{result.experience_gained}",
        f"💳 На счёте: {format_money(result.balance)}",
    ]
    if result.leveled_up and result.level:
        lines.append(f"🎉 Новый уровень: {result.level}!")
    return "\n".join(lines)
