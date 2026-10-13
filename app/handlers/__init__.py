"""Обработчики Telegram-событий."""

from aiogram import Router

from app.handlers import (
    diagnostics,
    errors,
    fallback,
    menu,
    orders,
    profile,
    repair,
    shop,
    start,
    workshop,
)


def get_routers() -> list[Router]:
    """Роутеры в порядке приоритета. fallback обязан идти последним."""
    return [
        errors.router,
        start.router,
        menu.router,
        profile.router,
        orders.router,
        workshop.router,
        diagnostics.router,
        shop.router,
        repair.router,
        fallback.router,
    ]
