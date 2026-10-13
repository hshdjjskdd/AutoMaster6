"""Автомобили и их технические конфигурации."""

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.game_data.enums import DriveType, FuelType, Transmission
from app.models.base import Base
from app.models.types import UTCDateTime, enum_type, utc_now


class CarConfiguration(Base):
    """Техническая конфигурация: марка, модель, двигатель, трансмиссия, привод.

    Справочник: одна конфигурация используется многими автомобилями.
    """

    __tablename__ = "car_configurations"
    __table_args__ = (
        UniqueConstraint(
            "brand",
            "model",
            "year",
            "engine_code",
            "transmission",
            "drive_type",
            name="uq_car_configurations_identity",
        ),
        CheckConstraint("year BETWEEN 1950 AND 2100", name="year_range"),
        CheckConstraint("engine_volume_cc >= 0", name="volume_min"),
        CheckConstraint("power_hp > 0", name="power_min"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    brand: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(64))
    year: Mapped[int] = mapped_column(Integer)
    body_type: Mapped[str] = mapped_column(String(32))
    engine_code: Mapped[str] = mapped_column(String(32))
    engine_volume_cc: Mapped[int] = mapped_column(Integer)
    power_hp: Mapped[int] = mapped_column(Integer)
    fuel_type: Mapped[FuelType] = mapped_column(enum_type(FuelType, "fuel_type"))
    transmission: Mapped[Transmission] = mapped_column(enum_type(Transmission, "transmission"))
    drive_type: Mapped[DriveType] = mapped_column(enum_type(DriveType, "drive_type"))


class Car(Base):
    """Конкретный автомобиль, который приезжает в мастерскую игрока."""

    __tablename__ = "cars"
    __table_args__ = (
        CheckConstraint("mileage_km >= 0", name="mileage_min"),
        CheckConstraint("condition_pct BETWEEN 0 AND 100", name="condition_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), index=True
    )
    configuration_id: Mapped[int] = mapped_column(
        ForeignKey("car_configurations.id", ondelete="RESTRICT"), index=True
    )
    vin: Mapped[str] = mapped_column(String(17), unique=True)
    plate: Mapped[str] = mapped_column(String(16))
    mileage_km: Mapped[int] = mapped_column(Integer, default=0)
    color: Mapped[str] = mapped_column(String(32))
    condition_pct: Mapped[int] = mapped_column(Integer, default=100)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)

    configuration: Mapped[CarConfiguration] = relationship(lazy="raise")
