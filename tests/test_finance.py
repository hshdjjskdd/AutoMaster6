"""Деньги: безопасное изменение баланса, журнал, идемпотентность, параллельность."""

import asyncio

from app.exceptions import IdempotencyConflict, InsufficientFunds, PlayerNotFound
from app.game_data.enums import TransactionCategory, TransactionType
from app.services import FinanceService
from tests.base import DatabaseTestCase


class FinanceTests(DatabaseTestCase):
    async def _apply(self, player_id: int, amount: int, key: str | None = None,
                     category: TransactionCategory = TransactionCategory.ADJUSTMENT):
        async with self.factory() as session:
            return await FinanceService(session).apply(
                player_id=player_id, amount=amount, category=category, idempotency_key=key
            )

    async def test_income_and_expense_update_balance_and_ledger(self) -> None:
        player_id = await self.make_player(money=1_000)
        income = await self._apply(player_id, 500, "i1")
        expense = await self._apply(player_id, -200, "e1")
        self.assertEqual((income.balance_after, expense.balance_after), (1_500, 1_300))
        self.assertEqual(await self.balance(player_id), 1_300)

        async with self.factory() as session:
            ledger = await FinanceService(session).get_history(player_id)
        self.assertEqual([(t.type, t.amount, t.balance_after) for t in ledger],
                         [(TransactionType.EXPENSE, -200, 1_300),
                          (TransactionType.INCOME, 500, 1_500)])

    async def test_overdraft_is_rejected_and_changes_nothing(self) -> None:
        player_id = await self.make_player(money=100)
        with self.assertRaises(InsufficientFunds):
            await self._apply(player_id, -101, "big")
        self.assertEqual(await self.balance(player_id), 100)
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM financial_transactions"), 0)

    async def test_exact_balance_can_be_spent(self) -> None:
        player_id = await self.make_player(money=100)
        result = await self._apply(player_id, -100)
        self.assertEqual(result.balance_after, 0)

    async def test_same_key_does_not_apply_twice(self) -> None:
        player_id = await self.make_player(money=1_000)
        first = await self._apply(player_id, 300, "once")
        second = await self._apply(player_id, 300, "once")
        self.assertFalse(first.duplicate)
        self.assertTrue(second.duplicate)
        self.assertEqual(first.transaction_id, second.transaction_id)
        self.assertEqual(await self.balance(player_id), 1_300)
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM financial_transactions"), 1)

    async def test_same_key_with_different_amount_is_a_conflict(self) -> None:
        player_id = await self.make_player(money=1_000)
        await self._apply(player_id, 300, "k")
        with self.assertRaises(IdempotencyConflict):
            await self._apply(player_id, 301, "k")
        self.assertEqual(await self.balance(player_id), 1_300)

    async def test_same_key_for_another_player_is_a_conflict(self) -> None:
        first = await self.make_player(telegram_id=1, money=1_000)
        second = await self.make_player(telegram_id=2, money=1_000)
        await self._apply(first, 300, "shared")
        with self.assertRaises(IdempotencyConflict):
            await self._apply(second, 300, "shared")
        self.assertEqual(await self.balance(second), 1_000)

    async def test_calls_without_key_are_independent(self) -> None:
        player_id = await self.make_player(money=0)
        await self._apply(player_id, 10)
        await self._apply(player_id, 10)
        self.assertEqual(await self.balance(player_id), 20)

    async def test_zero_amount_and_wrong_sign_for_category_are_rejected(self) -> None:
        player_id = await self.make_player(money=1_000)
        with self.assertRaises(ValueError):
            await self._apply(player_id, 0)
        with self.assertRaises(ValueError):
            await self._apply(player_id, -50, category=TransactionCategory.ORDER_REWARD)
        with self.assertRaises(ValueError):
            await self._apply(player_id, 50, category=TransactionCategory.PART_PURCHASE)
        self.assertEqual(await self.balance(player_id), 1_000)

    async def test_unknown_player(self) -> None:
        with self.assertRaises(PlayerNotFound):
            await self._apply(9_999, 10)
        async with self.factory() as session:
            with self.assertRaises(PlayerNotFound):
                await FinanceService(session).get_balance(9_999)

    async def test_database_trigger_blocks_negative_money_even_for_raw_sql(self) -> None:
        from sqlalchemy import text
        from sqlalchemy.exc import IntegrityError

        player_id = await self.make_player(money=10)
        async with self.factory() as session:
            with self.assertRaises(IntegrityError):
                await session.execute(
                    text("UPDATE players SET money = money - 11 WHERE id = :i"), {"i": player_id}
                )
        self.assertEqual(await self.balance(player_id), 10)

    # --- параллельность -----------------------------------------------------

    async def test_concurrent_spending_never_overdraws(self) -> None:
        player_id = await self.make_player(money=5_000)

        async def spend(i: int):
            try:
                await self._apply(player_id, -1_000, f"spend-{i}")
                return True
            except InsufficientFunds:
                return False

        results = await asyncio.gather(*(spend(i) for i in range(12)))
        self.assertEqual(sum(results), 5)
        self.assertEqual(await self.balance(player_id), 0)
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM financial_transactions"), 5)

    async def test_concurrent_same_key_is_applied_exactly_once(self) -> None:
        player_id = await self.make_player(money=0)
        results = await asyncio.gather(
            *(self._apply(player_id, 700, "same") for _ in range(10))
        )
        self.assertEqual(sum(1 for r in results if not r.duplicate), 1)
        self.assertEqual(await self.balance(player_id), 700)
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM financial_transactions"), 1)

    async def test_ledger_balance_after_is_consistent_under_concurrency(self) -> None:
        player_id = await self.make_player(money=0)
        await asyncio.gather(*(self._apply(player_id, 100, f"k{i}") for i in range(15)))
        async with self.factory() as session:
            ledger = await FinanceService(session).get_history(player_id, limit=100)
        self.assertEqual(sorted(t.balance_after for t in ledger), [100 * n for n in range(1, 16)])
        self.assertEqual(await self.balance(player_id), 1_500)
