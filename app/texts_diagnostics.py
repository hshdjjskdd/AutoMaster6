"""Тексты диагностики (HTML-разметка Telegram)."""

from datetime import UTC, datetime
from html import escape

from app.game_data.fault_catalog import CAUSES
from app.game_data.labels import ORDER_STATUS_TITLES
from app.schemas import (
    CheckOption,
    CheckRunView,
    ConclusionResult,
    DiagnosticOverview,
    ReadingView,
    ToolOption,
)
from app.utils.formatting import format_money

FLAG_ICONS = {"ok": "✅", "warn": "⚠️", "bad": "❗", "info": "ℹ️"}
CONCLUSION_LIMIT = 3


def format_minutes(minutes: int) -> str:
    hours, mins = divmod(minutes, 60)
    if hours and mins:
        return f"{hours} ч {mins} мин"
    if hours:
        return f"{hours} ч"
    return f"{mins} мин"


def render_menu(overview: DiagnosticOverview, *, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    lines = [
        f"🔧 <b>Диагностика · заказ №{overview.order_id}</b>",
        f"🚗 {escape(overview.car_title)} · <code>{escape(overview.plate)}</code>",
        f"💬 Жалоба: «{escape(overview.complaint)}»",
        f"Статус: {ORDER_STATUS_TITLES[overview.order_status]}",
        "",
        f"🧾 Проверок выполнено: <b>{overview.runs}</b>",
        f"⏱ Потрачено времени: <b>{format_minutes(overview.minutes_spent)}</b>",
        f"💸 Потрачено денег: <b>{format_money(overview.money_spent)}</b>",
        f"💰 На счёте: {format_money(overview.balance)}",
    ]
    if overview.deadline_at is not None:
        left = int((overview.deadline_at - now).total_seconds() // 60)
        if left > 0:
            lines.append(f"⌛ До срока заказа: {format_minutes(left)}")
        else:
            lines.append("⌛ Срок заказа вышел — премии за срок не будет")
    if overview.concluded:
        lines += ["", "📝 Заключение вынесено — новые проверки недоступны."]
    elif not overview.can_run:
        lines += ["", "Проверки на этом этапе недоступны."]
    elif overview.order_status.value in ("in_repair", "awaiting_parts"):
        lines += ["", "🔁 Диагностика продолжается в ходе ремонта: после неудачной проверки "
                  "жалоба клиента осталась — ищи следующую причину."]
    else:
        lines += [
            "",
            "Симптом не называет поломку: подтверждай версию несколькими проверками. "
            "Каждая проверка занимает время и стоит денег.",
        ]
    return "\n".join(lines)


def render_check_info(option: CheckOption, *, runs: int) -> str:
    lines = [
        f"{option.emoji} <b>{escape(option.title)}</b>",
        f"<i>Группа: {escape(option.group)}</i>",
        "",
        escape(option.description),
        "",
        f"⏱ Время: {option.minutes} мин",
    ]
    if option.tool_title is None:
        lines.append("🧰 Инструмент: не нужен")
    elif option.tool_owned:
        lines.append(f"🧰 Инструмент: {escape(option.tool_title)} — есть в мастерской")
    else:
        lines.append(
            f"🧰 Инструмент: {escape(option.tool_title)} — нет, берёшь в аренду "
            f"(можно купить в «🧰 Инструменты»)"
        )
    lines.append(f"💸 Стоимость: {'бесплатно' if option.fee == 0 else format_money(option.fee)}")
    if option.times_done:
        lines.append(f"🔁 Уже выполнялась: {option.times_done} раз")
    lines += ["", f"💡 {escape(option.interpretation)}"]
    return "\n".join(lines)


def _reading_line(reading: ReadingView) -> list[str]:
    icon = FLAG_ICONS.get(reading.flag, "ℹ️")
    value = f"<b>{escape(reading.value)}</b>"
    if reading.unit:
        value += f" {escape(reading.unit)}"
    line = f"{icon} {escape(reading.label)}: {value}"
    if reading.norm:
        unit = f" {escape(reading.unit)}" if reading.unit else ""
        line += f"  <i>(норма {escape(reading.norm)}{unit})</i>"
    lines = [line]
    if reading.note:
        lines.append(f"    <i>{escape(reading.note)}</i>")
    return lines


def deviations(run: CheckRunView) -> int:
    return sum(1 for r in run.readings if r.flag in ("warn", "bad"))


def render_run(run: CheckRunView, *, fresh: bool = False) -> str:
    header = f"{run.emoji} <b>{escape(run.title)}</b> · попытка №{run.run_no}"
    lines = [header]
    if fresh:
        paid = "бесплатно" if run.cost == 0 else format_money(run.cost)
        lines.append(f"⏱ −{run.minutes} мин · 💸 {paid}")
    if run.tool_title:
        lines.append(
            f"🧰 {escape(run.tool_title)}" + ("" if run.tool_owned else " (аренда)")
        )
    lines.append("")
    for reading in run.readings:
        lines += _reading_line(reading)
    lines.append("")
    n = deviations(run)
    lines.append("Все значения в пределах нормы." if n == 0 else f"Отклонений от нормы: {n}.")
    lines.append(f"💡 {escape(run.interpretation)}")
    return "\n".join(lines)


def render_journal(order_id: int, runs: list[CheckRunView]) -> str:
    lines = [f"📒 <b>Журнал диагностики · заказ №{order_id}</b>", ""]
    if not runs:
        lines.append("Пока пусто. Выполни первую проверку.")
        return "\n".join(lines)
    shown = runs[-10:]
    if len(runs) > len(shown):
        lines.append(f"<i>Показаны последние {len(shown)} из {len(runs)}</i>")
    for run in shown:
        n = deviations(run)
        verdict = "в норме" if n == 0 else f"отклонений: {n}"
        lines.append(
            f"№{run.run_no} {run.emoji} {escape(run.title)} — {verdict} "
            f"({run.minutes} мин, {format_money(run.cost) if run.cost else '0 ₽'})"
        )
    total_min = sum(r.minutes for r in runs)
    total_money = sum(r.cost for r in runs)
    lines += ["", f"Итого: {format_minutes(total_min)}, {format_money(total_money)}",
              "Открой запись, чтобы увидеть измеренные значения."]
    return "\n".join(lines)


def render_tools(tools: list[ToolOption]) -> str:
    lines = ["🧰 <b>Инструменты диагностики</b>", ""]
    for tool in tools:
        if tool.owned:
            lines.append(f"✅ {escape(tool.title)} — есть")
        else:
            level = f", нужен уровень {tool.required_level}" if tool.required_level > 1 else ""
            lines.append(f"▫️ {escape(tool.title)} — {format_money(tool.price)}{level}")
    lines += ["", "Если инструмента нет, проверка выполняется на арендованном оборудовании "
              "за доплату. Свой инструмент платить за аренду не заставляет."]
    return "\n".join(lines)


def render_conclusion_form(selected: list[int]) -> str:
    lines = [
        "📝 <b>Заключение диагностики</b>",
        "",
        f"Выбери причины, которые подтвердили проверки (не более {CONCLUSION_LIMIT}). "
        "После записи новые проверки станут недоступны.",
        "Правильность вывода выяснится при ремонте.",
    ]
    if selected:
        lines += ["", "<b>Выбрано:</b>"]
        lines += [f"• {escape(CAUSES[i].name)}" for i in selected]
    return "\n".join(lines)


def render_conclusion_done(result: ConclusionResult) -> str:
    lines = [f"📝 <b>Заключение по заказу №{result.order_id} записано</b>", ""]
    for fault in result.faults:
        lines.append(f"• {escape(fault.name)} <i>({escape(fault.system)})</i>")
    lines += ["", "Неисправности внесены в заказ. Закупи детали в магазине и переходи к ремонту."]
    return "\n".join(lines)

