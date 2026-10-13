"""Общие типы колонок для новых моделей."""

from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, Enum
from sqlalchemy.types import TypeDecorator


def utc_now() -> datetime:
    """Текущее время в UTC (aware)."""
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """DateTime, который всегда возвращает aware-значения в UTC.

    SQLite не хранит часовой пояс: стандартный DateTime возвращает naive-объекты.
    Этот тип запрещает записывать naive-время и при чтении проставляет UTC.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Нужно aware-время (с часовым поясом), получено naive")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


def enum_type(enum_cls: type[StrEnum], name: str) -> Enum:
    """Колонка-перечисление: строка в БД, CHECK-ограничение и проверка значений."""
    values: Callable[[Any], list[str]] = lambda members: [m.value for m in members]  # noqa: E731
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        length=24,
        create_constraint=True,
        validate_strings=True,
        values_callable=values,
    )
