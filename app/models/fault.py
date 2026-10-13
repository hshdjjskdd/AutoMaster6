"""Неисправности автомобиля и результаты диагностики."""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.game_data.enums import DiagnosticOutcome, FaultSeverity
from app.models.base import Base
from app.models.types import UTCDateTime, enum_type, utc_now


class Fault(Base):
    """Неисправность, найденная на автомобиле в рамках заказа."""

    __tablename__ = "faults"
    __table_args__ = (
        UniqueConstraint("order_id", "code", name="uq_faults_order_code"),
        # Решённая неисправность обязана иметь время решения, и наоборот.
        CheckConstraint(
            "(is_resolved = 0 AND resolved_at IS NULL) OR "
            "(is_resolved = 1 AND resolved_at IS NOT NULL)",
            name="resolved_consistency",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), index=True
    )
    car_id: Mapped[int] = mapped_column(ForeignKey("cars.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(128))
    system: Mapped[str] = mapped_column(String(32))
    severity: Mapped[FaultSeverity] = mapped_column(enum_type(FaultSeverity, "fault_severity"))
    is_resolved: Mapped[bool] = mapped_column(default=False)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)


class DiagnosticResult(Base):
    """Результат одной диагностической проверки."""

    __tablename__ = "diagnostic_results"
    __table_args__ = (CheckConstraint("duration_minutes >= 0", name="duration_min"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), index=True
    )
    fault_id: Mapped[int | None] = mapped_column(ForeignKey("faults.id", ondelete="SET NULL"))
    equipment_id: Mapped[int | None] = mapped_column(
        ForeignKey("equipment.id", ondelete="SET NULL")
    )
    check_name: Mapped[str] = mapped_column(String(64))
    outcome: Mapped[DiagnosticOutcome] = mapped_column(
        enum_type(DiagnosticOutcome, "diagnostic_outcome")
    )
    findings: Mapped[str] = mapped_column(Text, default="")
    duration_minutes: Mapped[int] = mapped_column(Integer, default=0)
    performed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
