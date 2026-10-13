"""История выполненных ремонтов."""

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.types import UTCDateTime, utc_now


class RepairHistory(Base):
    """Итог завершённого заказа. На один заказ — ровно одна запись."""

    __tablename__ = "repair_history"
    __table_args__ = (
        CheckConstraint("revenue >= 0", name="revenue_min"),
        CheckConstraint("parts_cost >= 0", name="parts_cost_min"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), index=True
    )
    # unique=True: повторное завершение заказа не создаст вторую запись.
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), unique=True
    )
    car_id: Mapped[int] = mapped_column(ForeignKey("cars.id", ondelete="CASCADE"), index=True)
    summary: Mapped[str] = mapped_column(Text)
    revenue: Mapped[int] = mapped_column(Integer)
    parts_cost: Mapped[int] = mapped_column(Integer)
    profit: Mapped[int] = mapped_column(Integer)
    completed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
