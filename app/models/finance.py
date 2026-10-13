"""Журнал финансовых операций."""

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.game_data.enums import TransactionCategory, TransactionType
from app.models.base import Base
from app.models.types import UTCDateTime, enum_type, utc_now


class FinancialTransaction(Base):
    """Одна денежная операция игрока. Записи не изменяются и не удаляются.

    amount хранится со знаком: доход > 0, расход < 0. Уникальный idempotency_key
    не позволяет провести одну и ту же операцию дважды.
    """

    __tablename__ = "financial_transactions"
    __table_args__ = (
        CheckConstraint("amount != 0", name="amount_nonzero"),
        CheckConstraint(
            "(type = 'income' AND amount > 0) OR (type = 'expense' AND amount < 0)",
            name="type_matches_sign",
        ),
        CheckConstraint("balance_after >= 0", name="balance_after_min"),
        Index("ix_financial_transactions_player_created", "player_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), index=True
    )
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), index=True
    )
    type: Mapped[TransactionType] = mapped_column(enum_type(TransactionType, "transaction_type"))
    category: Mapped[TransactionCategory] = mapped_column(
        enum_type(TransactionCategory, "transaction_category")
    )
    amount: Mapped[int] = mapped_column(Integer)
    balance_after: Mapped[int] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(String(255))
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
