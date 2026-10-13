"""Репозиторий денег: атомарное изменение баланса и журнал операций.

Ни один метод здесь не делает commit: транзакцией управляет сервис, чтобы
изменение денег, склада и статуса заказа применялись вместе или не применялись вовсе.
"""

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.game_data.enums import CATEGORY_SIGN, TransactionCategory, TransactionType
from app.models import FinancialTransaction, Player
from app.models.types import utc_now
from app.exceptions import (
    IdempotencyConflict,
    InsufficientFunds,
    PlayerNotFound,
)


class FinanceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_balance(self, player_id: int) -> int | None:
        """Текущий баланс игрока или None, если игрока нет."""
        return await self._session.scalar(select(Player.money).where(Player.id == player_id))

    async def last_transaction_id(self, player_id: int) -> int:
        """Номер последней записи журнала игрока (0, если записей нет).

        Входит в ключ идемпотентности покупок в магазине: экран, показанный до
        покупки, при повторном нажатии даёт тот же ключ, и деньги не списываются дважды.
        """
        value = await self._session.scalar(
            select(func.max(FinancialTransaction.id)).where(
                FinancialTransaction.player_id == player_id
            )
        )
        return int(value or 0)

    async def get_by_key(self, idempotency_key: str) -> FinancialTransaction | None:
        result = await self._session.execute(
            select(FinancialTransaction)
            .where(FinancialTransaction.idempotency_key == idempotency_key)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def list_for_player(
        self, player_id: int, *, limit: int = 20, offset: int = 0
    ) -> list[FinancialTransaction]:
        result = await self._session.execute(
            select(FinancialTransaction)
            .where(FinancialTransaction.player_id == player_id)
            .order_by(FinancialTransaction.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars())

    async def apply_change(
        self,
        *,
        player_id: int,
        amount: int,
        category: TransactionCategory,
        idempotency_key: str,
        order_id: int | None = None,
        description: str | None = None,
    ) -> tuple[FinancialTransaction, bool]:
        """Применяет денежную операцию. Возвращает (запись журнала, это_повтор).

        Защита от двойного начисления: если запись с таким ключом уже есть, деньги не
        трогаются, возвращается существующая запись. Баланс меняется одним условным
        UPDATE, поэтому уйти в минус или потерять часть списания при параллельных
        запросах невозможно.

        Если два запроса с одним ключом пришли одновременно, второй получит
        IntegrityError на уникальном ключе; вызывающий обязан откатить транзакцию.
        """
        if amount == 0:
            raise ValueError("Сумма операции не может быть нулевой")
        allowed_sign = CATEGORY_SIGN[category]
        if allowed_sign is not None and (amount > 0) != (allowed_sign > 0):
            raise ValueError(f"Категория {category.value} не допускает сумму {amount}")

        existing = await self.get_by_key(idempotency_key)
        if existing is not None:
            if (
                existing.player_id != player_id
                or existing.amount != amount
                or existing.category != category
            ):
                raise IdempotencyConflict(idempotency_key)
            return existing, True

        result = await self._session.execute(
            update(Player)
            .where(Player.id == player_id, Player.money + amount >= 0)
            .values(money=Player.money + amount, updated_at=utc_now())
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            if await self.get_balance(player_id) is None:
                raise PlayerNotFound(player_id)
            raise InsufficientFunds(required=-amount)

        balance_after = await self.get_balance(player_id)
        assert balance_after is not None  # строка игрока только что обновлена

        entry = FinancialTransaction(
            player_id=player_id,
            order_id=order_id,
            type=TransactionType.INCOME if amount > 0 else TransactionType.EXPENSE,
            category=category,
            amount=amount,
            balance_after=balance_after,
            description=description,
            idempotency_key=idempotency_key,
        )
        self._session.add(entry)
        await self._session.flush()
        return entry, False
