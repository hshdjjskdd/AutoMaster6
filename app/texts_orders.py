"""Тексты клиентских заказов и мастерской (HTML-разметка Telegram)."""

from datetime import UTC, datetime
from html import escape

from app.game_data.economy import (
    CANCEL_AFTER_START_REPUTATION_PENALTY,
    ON_TIME_BONUS_PERCENT,
    TIER_EMOJI,
    TIER_TITLES,
)
from app.game_data.order_board import format_countdown
from app.game_data.labels import (
    DRIVE_TITLES,
    FUEL_TITLES,
    ORDER_STATUS_TITLES,
    TRANSMISSION_TITLES,
)
from app.game_data.rarity import rarity_emoji
from app.schemas import Board, CarCard, FinanceSummary, OfferCard, RefreshResult, WorkshopOrderCard
from app.utils.formatting import format_money

EMPTY_WORKSHOP_TEXT = (
    "🏭 <b>Мастерская</b>\n\nСейчас в мастерской пусто. "
    "Загляни в «📋 Заказы» и прими предложение клиента."
)


def _badge(brand: str, model: str) -> str:
    """Эмодзи редкости с пробелом (вероятности и текст редкости игроку не показываем)."""
    emoji = rarity_emoji(brand, model)
    return f"{emoji} " if emoji else ""


def _km(value: int) -> str:
    return f"{value:,}".replace(",", " ") + " км"


def render_car(car: CarCard) -> list[str]:
    title = f"{escape(car.brand)} {escape(car.model)}, {car.year}"
    lines = [f"{_badge(car.brand, car.model) or '🚗'} <b>{title}</b>"]
    if car.trim_name:
        lines.append(f"Комплектация: {escape(car.trim_name)}")
    lines += [
        f"Кузов: {escape(car.body_type)}, цвет: {escape(car.color)}",
        f"Двигатель: {escape(car.engine_code)}, {car.engine_volume_cc / 1000:.1f} л, "
        f"{car.power_hp} л.с., {FUEL_TITLES[car.fuel_type]}",
        f"Трансмиссия: {TRANSMISSION_TITLES[car.transmission]}, "
        f"привод: {DRIVE_TITLES[car.drive_type]}",
        f"Пробег: {_km(car.mileage_km)}",
        f"Состояние кузова и узлов: {car.condition_pct}%",
        f"Госномер: <code>{escape(car.plate)}</code>",
        f"VIN: <code>{escape(car.vin)}</code>",
    ]
    return lines


def _symptoms(symptoms: tuple[str, ...]) -> list[str]:
    return ["🔎 <b>Наблюдаемые симптомы:</b>", *(f"• {escape(s)}" for s in symptoms)]


def _hours_left(expires_at: datetime, now: datetime) -> str:
    minutes = int((expires_at - now).total_seconds() // 60)
    if minutes <= 0:
        return "меньше минуты"
    hours, mins = divmod(minutes, 60)
    return f"{hours} ч {mins:02d} мин" if hours else f"{mins} мин"


def tier_label(tier: int) -> str:
    return f"{TIER_EMOJI.get(tier, '🟢')} {TIER_TITLES.get(tier, 'лёгкий')}"


def _short(text: str, limit: int = 140) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def render_board(board: Board, *, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    lines = [
        "🚗 <b>Доступные заказы</b>",
        f"Заказов на доске: {len(board.offers)} из {board.board_size}"
        if board.board_size
        else f"Заказов на доске: {len(board.offers)}",
        f"В мастерской: {board.active_orders} из {board.capacity}",
    ]
    if board.next_refresh_at is not None:
        lines.append(
            f"⏱ Следующее обновление заказов: {format_countdown(board.next_refresh_at, now)}"
        )
    lines.append("")
    if not board.offers:
        lines.append("Клиентов пока нет — загляни после обновления.")
    for idx, offer in enumerate(board.offers, 1):
        car = offer.car
        costs = f" · 🔧 ≈ {format_money(offer.est_cost)}" if offer.est_cost else ""
        lines.append(
            f"<b>{idx}. {_badge(car.brand, car.model)}{escape(car.brand)} {escape(car.model)}, {car.year}</b>\n"
            f"    Сложность: {tier_label(offer.tier)}\n"
            f"    💰 ≈ {format_money(offer.payment)}{costs}\n"
            f"    💬 {escape(_short(offer.complaint))}"
        )
    lines += ["", "Выбери заказ, чтобы увидеть карточку и принять его."]
    return "\n".join(lines)


def render_refresh_notice(result: RefreshResult) -> str:
    counts = {t: result.created_tiers.count(t) for t in sorted(set(result.created_tiers))}
    kinds = ", ".join(f"{TIER_EMOJI[t]} ×{n}" for t, n in counts.items())
    return (
        "🔔 <b>Доска заказов обновилась</b>\n"
        f"Новых заказов: {len(result.created_tiers)} ({kinds})\n"
        f"Всего на доске: {result.available}"
    )


def render_finance(summary: FinanceSummary) -> str:
    return "\n".join(
        [
            "📊 <b>Финансы мастерской</b>",
            f"Сдано заказов: {summary.orders_done}",
            "",
            f"💰 Выручка: <b>{format_money(summary.revenue)}</b>",
            f"🔧 Расходы: <b>{format_money(summary.expenses)}</b> (детали, списанные на заказы)",
            f"📈 Чистая прибыль: <b>{format_money(summary.profit)}</b>",
            "",
            "Чистая прибыль = оплата клиента − расходы на ремонт.",
            f"💳 На счёте: {format_money(summary.balance)}",
        ]
    )


def render_offer(offer: OfferCard, *, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    lines = [
        "📄 <b>Предложение клиента</b>",
        f"👤 Клиент: <b>{escape(offer.customer_name)}</b>",
        "",
        *render_car(offer.car),
        "",
        f"Сложность: <b>{tier_label(offer.tier)}</b>",
        f"💬 <b>Жалоба:</b> «{escape(offer.complaint)}»",
        "",
        *_symptoms(offer.symptoms),
        "",
        f"💰 Оплата за заказ: <b>{format_money(offer.payment)}</b>",
        f"🔧 Ориентировочные расходы на детали: ≈ {format_money(offer.est_cost)} "
        "(зависят от того, что покажет диагностика, и от качества деталей)",
        f"🎁 Премия за сдачу в срок: +{ON_TIME_BONUS_PERCENT}% "
        f"(+{format_money(offer.potential_bonus)})",
        f"⏱ Срок на работу: {offer.deadline_hours} ч с момента приёмки",
        f"⌛ Клиент ждёт ответа ещё: {_hours_left(offer.expires_at, now)}",
    ]
    return "\n".join(lines)


def render_workshop_list(orders: list[WorkshopOrderCard]) -> str:
    lines = ["🏭 <b>Мастерская</b>", f"Машин в работе: {len(orders)}", ""]
    for order in orders:
        car = order.car
        lines.append(
            f"<b>№{order.order_id} {_badge(car.brand, car.model)}{escape(car.brand)} {escape(car.model)}</b> — "
            f"{ORDER_STATUS_TITLES[order.status]}"
        )
    return "\n".join(lines)


def render_workshop_order(order: WorkshopOrderCard, *, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    lines = [
        f"🛠 <b>Заказ №{order.order_id}</b>",
        f"Статус: <b>{ORDER_STATUS_TITLES[order.status]}</b>",
        f"👤 Клиент: {escape(order.customer_name)}",
        "",
        *render_car(order.car),
        "",
        f"Сложность: {tier_label(order.tier)}",
        f"💬 <b>Жалоба:</b> «{escape(order.complaint)}»",
    ]
    if order.symptoms:
        lines += ["", *_symptoms(order.symptoms)]
    lines += ["", f"💰 Оплата: <b>{format_money(order.reward)}</b>"]
    if order.deadline_at is not None:
        left = order.deadline_at - now
        if left.total_seconds() > 0:
            lines.append(
                f"⏱ Срок: до {order.deadline_at.strftime('%d.%m %H:%M')} UTC "
                f"(премия +{format_money(order.potential_bonus)})"
            )
        else:
            lines.append("⏱ Срок вышел — премии за срок не будет")
    lines.append(f"📅 Принят: {order.created_at.strftime('%d.%m.%Y %H:%M')} UTC")
    if order.cancel_penalty is None:
        lines.append("\nОтмена недоступна на этом этапе.")
    elif order.cancel_penalty == 0:
        lines.append("\nОтмена сейчас бесплатна: работа ещё не начата.")
    else:
        lines.append(
            f"\nОтмена сейчас снизит репутацию на {order.cancel_penalty} "
            f"(работа уже начата)."
        )
    return "\n".join(lines)


def render_accepted(order_id: int) -> str:
    return (
        f"✅ Заказ №{order_id} принят. Машина стоит в мастерской.\n"
        "Открой «🏭 Мастерская», чтобы посмотреть заказ."
    )


def render_cancel_confirm(order: WorkshopOrderCard) -> str:
    if order.cancel_penalty == 0:
        note = "Отмена бесплатна."
    else:
        note = (
            f"Репутация снизится на {order.cancel_penalty} "
            f"(штраф за срыв начатой работы: {CANCEL_AFTER_START_REPUTATION_PENALTY})."
        )
    return f"Отменить заказ №{order.order_id}? {note}"
