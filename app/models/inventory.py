"""Каталог запчастей и оборудования, склад и оборудование игрока."""

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.game_data.enums import EquipmentCategory, PartCategory
from app.models.base import Base
from app.models.types import UTCDateTime, enum_type, utc_now


class Part(Base):
    """Запчасть из каталога."""

    __tablename__ = "parts"
    __table_args__ = (CheckConstraint("base_price > 0", name="base_price_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    category: Mapped[PartCategory] = mapped_column(enum_type(PartCategory, "part_category"))
    base_price: Mapped[int] = mapped_column(Integer)


class StockItem(Base):
    """Остаток запчасти на складе игрока."""

    __tablename__ = "stock_items"
    __table_args__ = (
        UniqueConstraint("player_id", "part_id", name="uq_stock_items_player_part"),
        CheckConstraint("quantity >= 0", name="quantity_min"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), index=True
    )
    part_id: Mapped[int] = mapped_column(ForeignKey("parts.id", ondelete="RESTRICT"))
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)

    part: Mapped[Part] = relationship(lazy="raise")


class Equipment(Base):
    """Оборудование из каталога."""

    __tablename__ = "equipment"
    __table_args__ = (
        CheckConstraint("price >= 0", name="price_min"),
        CheckConstraint("required_level >= 1", name="required_level_min"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    category: Mapped[EquipmentCategory] = mapped_column(
        enum_type(EquipmentCategory, "equipment_category")
    )
    price: Mapped[int] = mapped_column(Integer)
    required_level: Mapped[int] = mapped_column(Integer, default=1)


class PlayerEquipment(Base):
    """Оборудование, купленное игроком. Одна единица каждого вида."""

    __tablename__ = "player_equipment"
    __table_args__ = (
        UniqueConstraint("player_id", "equipment_id", name="uq_player_equipment_pair"),
        CheckConstraint("condition_pct BETWEEN 0 AND 100", name="condition_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), index=True
    )
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipment.id", ondelete="RESTRICT"))
    condition_pct: Mapped[int] = mapped_column(Integer, default=100)
    purchased_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)

    equipment: Mapped[Equipment] = relationship(lazy="raise")
