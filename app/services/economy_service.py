"""Финансовая сводка игрока: выручка, расходы на детали, чистая прибыль."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import PlayerNotFound
from app.repositories import FinanceRepository, HistoryRepository, OrderRepository
from app.schemas import FinanceSummary


class EconomyService:
    """Только чтение: деньги меняются исключительно через FinanceService/OrderService."""

    def __init__(self, session: AsyncSession) -> None:
        self._history = HistoryRepository(session)
        self._finance = FinanceRepository(session)
        self._orders = OrderRepository(session)

    async def summary(self, player_id: int) -> FinanceSummary:
        """Чистая прибыль = оплата клиента (с премией) − детали, списанные на заказы."""
        balance = await self._finance.get_balance(player_id)
        if balance is None:
            raise PlayerNotFound(player_id)
        done, revenue, expenses, profit = await self._history.totals(player_id)
        active = await self._orders.count_active(player_id)
        return FinanceSummary(
            orders_done=done,
            revenue=revenue,
            expenses=expenses,
            profit=profit,
            balance=balance,
            active_orders=active,
        )
