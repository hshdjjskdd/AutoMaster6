"""Сервис финансов: безопасное изменение денег и журнал операций."""

from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import PlayerNotFound
from app.game_data.enums import TransactionCategory
from app.models import FinancialTransaction
from app.repositories import FinanceRepository
from app.schemas import LedgerResult
from app.services.transaction import atomic


def _to_result(entry: FinancialTransaction, *, duplicate: bool) -> LedgerResult:
    return LedgerResult(
        transaction_id=entry.id,
        amount=entry.amount,
        balance_after=entry.balance_after,
        duplicate=duplicate,
    )


class FinanceService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._finance = FinanceRepository(session)

    async def apply(
        self,
        *,
        player_id: int,
        amount: int,
        category: TransactionCategory,
        idempotency_key: str | None = None,
        order_id: int | None = None,
        description: str | None = None,
    ) -> LedgerResult:
        """Проводит денежную операцию (amount > 0 — доход, < 0 — расход).

        idempotency_key делает операцию повторяемой без последствий: вызов с тем же
        ключом ничего не меняет и возвращает результат первого вызова с duplicate=True.
        Для операций, которые могут прийти дважды (нажатие кнопки, повторная
        доставка обновления), ключ нужно передавать обязательно. Без ключа каждая
        операция считается самостоятельной.

        Raises:
            InsufficientFunds: расход больше баланса.
            PlayerNotFound: игрока нет.
            IdempotencyConflict: ключ уже использован для другой операции.
        """
        key = idempotency_key or f"auto:{uuid4().hex}"
        try:
            async with atomic(self._session):
                entry, duplicate = await self._finance.apply_change(
                    player_id=player_id,
                    amount=amount,
                    category=category,
                    idempotency_key=key,
                    order_id=order_id,
                    description=description,
                )
        except IntegrityError:
            # Параллельный запрос с тем же ключом успел раньше: транзакция откачена,
            # деньги не изменены, возвращаем результат победителя.
            existing = await self._finance.get_by_key(key)
            if existing is None:
                raise
            return _to_result(existing, duplicate=True)
        return _to_result(entry, duplicate=duplicate)

    async def get_balance(self, player_id: int) -> int:
        balance = await self._finance.get_balance(player_id)
        if balance is None:
            raise PlayerNotFound(player_id)
        return balance

    async def get_history(
        self, player_id: int, *, limit: int = 20, offset: int = 0
    ) -> list[FinancialTransaction]:
        return await self._finance.list_for_player(player_id, limit=limit, offset=offset)
