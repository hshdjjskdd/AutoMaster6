"""Выполненные ремонтные операции заказа (этап 5)."""

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.types import UTCDateTime, utc_now


class RepairOperation(Base):
    """Одна выполненная операция ремонта.

    Уникальность (order_id, op_code) гарантирует «ровно один раз»: повторное нажатие
    кнопки или параллельный запрос не спишет детали повторно.
    """

    __tablename__ = "repair_operations"
    __table_args__ = (
        UniqueConstraint("order_id", "op_code", name="uq_repair_operations_order_op"),
        CheckConstraint("minutes >= 0", name="minutes_min"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), index=True
    )
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), index=True
    )
    fault_id: Mapped[int] = mapped_column(ForeignKey("faults.id", ondelete="CASCADE"))
    op_code: Mapped[str] = mapped_column(String(32))
    minutes: Mapped[int] = mapped_column(Integer, default=0)
    # Какие детали списаны: JSON [{"sku": ..., "name": ..., "qty": ..., "price": ...}].
    parts_json: Mapped[str] = mapped_column(Text, default="[]")
    performed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
