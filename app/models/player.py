"""Модель игрока."""

from datetime import UTC, datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.game_data.constants import (
    MAX_REPUTATION,
    MIN_REPUTATION,
    START_EXPERIENCE,
    START_LEVEL,
    START_MONEY,
    START_REPUTATION,
)
from app.models.base import Base


def utc_now() -> datetime:
    """Текущее время в UTC."""
    return datetime.now(UTC)


class Player(Base):
    """Игрок: один Telegram-аккаунт — одна мастерская."""

    __tablename__ = "players"
    __table_args__ = (
        CheckConstraint("level >= 1", name="level_min"),
        CheckConstraint("experience >= 0", name="experience_min"),
        CheckConstraint(
            f"reputation BETWEEN {MIN_REPUTATION} AND {MAX_REPUTATION}",
            name="reputation_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))

    money: Mapped[int] = mapped_column(Integer, default=START_MONEY)
    level: Mapped[int] = mapped_column(Integer, default=START_LEVEL)
    experience: Mapped[int] = mapped_column(Integer, default=START_EXPERIENCE)
    reputation: Mapped[int] = mapped_column(Integer, default=START_REPUTATION)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    def __repr__(self) -> str:
        return f"Player(id={self.id!r}, telegram_id={self.telegram_id!r})"
