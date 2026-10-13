"""Заказы на ремонт и детали, установленные по заказу."""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.game_data.enums import OrderStatus
from app.models.base import Base
from app.models.car import Car
from app.models.fault import DiagnosticResult, Fault
from app.models.inventory import Part
from app.models.types import UTCDateTime, enum_type, utc_now


class Order(Base):
    """Заказ-наряд: один автомобиль, одна жалоба клиента, один статус ремонта."""

    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("reward >= 0", name="reward_min"),
        # Завершённый заказ обязан иметь время завершения.
        CheckConstraint(
            "status != 'completed' OR completed_at IS NOT NULL",
            name="completed_has_timestamp",
        ),
        # Награда может быть выплачена только по завершённому заказу.
        CheckConstraint(
            "reward_paid_at IS NULL OR status = 'completed'",
            name="reward_only_when_completed",
        ),
        Index("ix_orders_player_status", "player_id", "status"),
        # Один автомобиль — не более одного незавершённого заказа.
        Index(
            "uq_orders_car_active",
            "car_id",
            unique=True,
            sqlite_where=text("status NOT IN ('completed', 'cancelled')"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), index=True
    )
    # Без ondelete (NO ACTION): машину с заказами удалить нельзя, а удаление игрока,
    # каскадно убирающее и машины, и заказы, работает при любом порядке создания таблиц.
    # RESTRICT проверяется немедленно и ломал бы каскад, если cars удаляется раньше orders.
    car_id: Mapped[int] = mapped_column(ForeignKey("cars.id"), index=True)
    status: Mapped[OrderStatus] = mapped_column(
        enum_type(OrderStatus, "order_status"), default=OrderStatus.NEW
    )
    customer_name: Mapped[str] = mapped_column(String(64))
    complaint: Mapped[str] = mapped_column(Text)
    reward: Mapped[int] = mapped_column(Integer, default=0)
    reward_paid_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    deadline_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    car: Mapped[Car] = relationship(lazy="raise")
    faults: Mapped[list[Fault]] = relationship(
        lazy="raise", cascade="all, delete-orphan", passive_deletes=True, order_by="Fault.id"
    )
    diagnostics: Mapped[list[DiagnosticResult]] = relationship(
        lazy="raise",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="DiagnosticResult.id",
    )
    parts: Mapped[list["OrderPart"]] = relationship(
        lazy="raise", cascade="all, delete-orphan", passive_deletes=True, order_by="OrderPart.id"
    )


class OrderPart(Base):
    """Деталь, списанная со склада на заказ, с ценой на момент установки."""

    __tablename__ = "order_parts"
    __table_args__ = (
        UniqueConstraint("order_id", "part_id", name="uq_order_parts_order_part"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_price >= 0", name="unit_price_min"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), index=True
    )
    part_id: Mapped[int] = mapped_column(ForeignKey("parts.id", ondelete="RESTRICT"))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[int] = mapped_column(Integer)
    installed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)

    part: Mapped[Part] = relationship(lazy="raise")
