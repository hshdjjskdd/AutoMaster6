"""Настройка логирования."""

import logging


def setup_logging(level: str) -> None:
    """Включает единый формат логов для всего приложения."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # aiosqlite на уровне DEBUG пишет каждую операцию — это лишний шум.
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
