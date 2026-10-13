"""Состояние доски заказов игрока: когда следующее обновление и «жалость»."""

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.types import UTCDateTime


class OrderBoardState(Base):
    """Одна строка на игрока. Время обновления живёт в БД, а не в памяти процесса."""

    __tablename__ = "order_board_state"
    __table_args__ = (
        CheckConstraint("empty_streak >= 0", name="empty_streak_min"),
        CheckConstraint("refresh_count >= 0", name="refresh_count_min"),
    )

    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), primary_key=True
    )
    next_refresh_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    last_refresh_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # Сколько обновлений подряд не создали ни одного заказа (для «жалости»).
    empty_streak: Mapped[int] = mapped_column(Integer, default=0)
    # Сколько обновлений уже выполнено (0 — стартовая доска ещё не выдана).
    refresh_count: Mapped[int] = mapped_column(Integer, default=0)
