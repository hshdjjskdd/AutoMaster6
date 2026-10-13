"""Форматирование чисел и индикаторов для сообщений."""

from app.game_data.constants import CURRENCY_SYMBOL

_NBSP = " "


def format_money(amount: int) -> str:
    """15000 -> '15 000 ₽' (неразрывные пробелы, чтобы сумма не переносилась)."""
    grouped = f"{amount:,}".replace(",", _NBSP)
    return f"{grouped}{_NBSP}{CURRENCY_SYMBOL}"


def progress_bar(value: int, maximum: int, length: int = 10) -> str:
    """Текстовая шкала: progress_bar(50, 100) -> '█████░░░░░'."""
    if maximum <= 0:
        raise ValueError("maximum должен быть положительным числом")
    if length <= 0:
        raise ValueError("length должен быть положительным числом")
    ratio = max(0.0, min(value / maximum, 1.0))
    filled = int(ratio * length + 0.5)
    return "█" * filled + "░" * (length - filled)
