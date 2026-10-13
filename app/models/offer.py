"""Предложения клиентов на доске заказов."""

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.game_data.enums import OfferStatus
from app.models.base import Base
from app.models.car import CarConfiguration
from app.models.types import UTCDateTime, enum_type, utc_now


class ClientOffer(Base):
    """Предложение клиента. Автомобиль и заказ создаются только при принятии."""

    __tablename__ = "client_offers"
    __table_args__ = (
        CheckConstraint("payment >= 0", name="payment_min"),
        CheckConstraint("mileage_km >= 0", name="mileage_min"),
        Index("ix_client_offers_player_status", "player_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[OfferStatus] = mapped_column(
        enum_type(OfferStatus, "offer_status"), default=OfferStatus.AVAILABLE
    )
    configuration_id: Mapped[int] = mapped_column(ForeignKey("car_configurations.id"))
    trim_name: Mapped[str] = mapped_column(String(64))
    vin: Mapped[str] = mapped_column(String(17))
    plate: Mapped[str] = mapped_column(String(16))
    mileage_km: Mapped[int] = mapped_column(Integer)
    color: Mapped[str] = mapped_column(String(32))
    condition_pct: Mapped[int] = mapped_column(Integer)
    customer_name: Mapped[str] = mapped_column(String(64))
    scenario_code: Mapped[str] = mapped_column(String(32))
    complaint: Mapped[str] = mapped_column(Text)
    symptoms: Mapped[str] = mapped_column(Text)  # по одному симптому в строке
    payment: Mapped[int] = mapped_column(Integer)
    deadline_hours: Mapped[int] = mapped_column(Integer)
    # Этап 6: сложность заказа (1 🟢, 2 🟡, 3 🔴), запланированные скрытые неисправности
    # (JSON [[причина, сценарий], ...]; пусто у старых предложений) и смета деталей.
    tier: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    planned_faults: Mapped[str] = mapped_column(Text, default="", server_default="")
    est_cost: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), index=True
    )

    configuration: Mapped[CarConfiguration] = relationship(lazy="raise")
