"""Диагностика заказа: сессия, скрытые реальные неисправности и журнал проверок."""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.types import UTCDateTime, utc_now


class DiagnosticSession(Base):
    """Сводка диагностики заказа: потраченные время и деньги, завершено ли заключение."""

    __tablename__ = "diagnostic_sessions"
    __table_args__ = (
        CheckConstraint("minutes_spent >= 0", name="minutes_min"),
        CheckConstraint("money_spent >= 0", name="money_min"),
    )

    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), primary_key=True
    )
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), index=True
    )
    minutes_spent: Mapped[int] = mapped_column(Integer, default=0)
    money_spent: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    concluded_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class HiddenFault(Base):
    """Реальная неисправность автомобиля. Игрок её не видит — только измерения."""

    __tablename__ = "hidden_faults"
    __table_args__ = (UniqueConstraint("order_id", "cause_code", name="uq_hidden_faults_order_cause"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), index=True
    )
    cause_code: Mapped[str] = mapped_column(String(16))
    detail: Mapped[str] = mapped_column(String(32), default="")


class DiagnosticCheckRun(Base):
    """Одна выполненная проверка с измеренными значениями (журнал диагностики)."""

    __tablename__ = "diagnostic_check_runs"
    __table_args__ = (
        UniqueConstraint("order_id", "run_no", name="uq_diagnostic_check_runs_order_run"),
        CheckConstraint("run_no >= 1", name="run_no_min"),
        CheckConstraint("minutes >= 0", name="minutes_min"),
        CheckConstraint("cost >= 0", name="cost_min"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), index=True
    )
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), index=True
    )
    run_no: Mapped[int] = mapped_column(Integer)
    check_code: Mapped[str] = mapped_column(String(24))
    tool_code: Mapped[str | None] = mapped_column(String(32))
    tool_owned: Mapped[bool] = mapped_column(Boolean, default=False)
    minutes: Mapped[int] = mapped_column(Integer)
    cost: Mapped[int] = mapped_column(Integer, default=0)
    readings_json: Mapped[str] = mapped_column(Text)
    interpretation: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
