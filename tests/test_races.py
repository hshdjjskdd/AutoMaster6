"""Детерминированные гонки: устаревшее чтение + условные UPDATE.

В отличие от asyncio.gather, здесь порядок событий задан явно, поэтому тест
стабильно ловит поломку защиты, а не зависит от планировщика.
"""

from unittest.mock import patch

from app.game_data.enums import OrderStatus, TransactionCategory
from app.models.types import utc_now
from app.repositories import FinanceRepository, InventoryRepository, OrderRepository
from app.services import FinanceService
from tests.base import DatabaseTestCase


class StaleReadTests(DatabaseTestCase):
    async def test_status_change_from_stale_read_is_rejected(self) -> None:
        pid = await self.make_player()
        car = await self.make_car(pid)
        order = await self.make_order(pid, car.id, status=OrderStatus.IN_REPAIR)

        async with self.factory() as s1, self.factory() as s2:
            repo1, repo2 = OrderRepository(s1), OrderRepository(s2)
            seen1 = await repo1.get(pid, order.id)
            seen2 = await repo2.get(pid, order.id)  # обе сессии видят IN_REPAIR
            self.assertEqual((seen1.status, seen2.status), (OrderStatus.IN_REPAIR,) * 2)

            won = await repo1.transition_status(
                order_id=order.id, player_id=pid, expected=seen1.status, new=OrderStatus.READY
            )
            await s1.commit()
            lost = await repo2.transition_status(
                order_id=order.id, player_id=pid, expected=seen2.status,
                new=OrderStatus.AWAITING_PARTS,
            )
            await s2.commit()

        self.assertTrue(won)
        self.assertFalse(lost)
        order_now = await self.scalar("SELECT status FROM orders WHERE id = :i", i=order.id)
        self.assertEqual(order_now, "ready")

    async def test_reward_cas_pays_only_for_one_of_two_stale_readers(self) -> None:
        pid = await self.make_player()
        car = await self.make_car(pid)
        order = await self.make_order(pid, car.id, status=OrderStatus.READY)

        async with self.factory() as s1, self.factory() as s2:
            repo1, repo2 = OrderRepository(s1), OrderRepository(s2)
            self.assertEqual((await repo1.get(pid, order.id)).status, OrderStatus.READY)
            self.assertEqual((await repo2.get(pid, order.id)).status, OrderStatus.READY)
            first = await repo1.complete_if_ready(order_id=order.id, player_id=pid, now=utc_now())
            await s1.commit()
            second = await repo2.complete_if_ready(order_id=order.id, player_id=pid, now=utc_now())
            await s2.commit()
        self.assertEqual((first, second), (True, False))

    async def test_reward_cas_refuses_order_with_reward_already_marked_paid(self) -> None:
        """Вторая линия защиты: отметка reward_paid_at не даёт завершить заказ повторно."""
        from sqlalchemy import text

        pid = await self.make_player()
        car = await self.make_car(pid)
        order = await self.make_order(pid, car.id, status=OrderStatus.READY)
        async with self.factory() as session:
            # Намеренно нарушаем инвариант в обход CHECK: статус READY при отметке выплаты.
            await session.execute(text("PRAGMA ignore_check_constraints = ON"))
            await session.execute(
                text("UPDATE orders SET reward_paid_at = '2026-01-01 00:00:00' WHERE id = :i"),
                {"i": order.id},
            )
            await session.commit()
        async with self.factory() as session:
            done = await OrderRepository(session).complete_if_ready(
                order_id=order.id, player_id=pid, now=utc_now()
            )
        self.assertFalse(done)

    async def test_stock_cannot_be_taken_twice_from_stale_read(self) -> None:
        pid = await self.make_player(money=10_000)
        async with self.factory() as session:
            repo = InventoryRepository(session)
            part = await repo.get_part_by_sku("FLT-OIL")
            await repo.add_stock(pid, part.id, 1)
            await session.commit()

        async with self.factory() as s1, self.factory() as s2:
            r1, r2 = InventoryRepository(s1), InventoryRepository(s2)
            self.assertEqual(await r1.get_stock_quantity(pid, part.id), 1)
            self.assertEqual(await r2.get_stock_quantity(pid, part.id), 1)
            first = await r1.take_stock(pid, part.id, 1)
            await s1.commit()
            second = await r2.take_stock(pid, part.id, 1)
            await s2.commit()
        self.assertEqual((first, second), (True, False))
        self.assertEqual(await self.scalar("SELECT quantity FROM stock_items"), 0)

    async def test_money_cannot_be_overdrawn_from_stale_balance(self) -> None:
        pid = await self.make_player(money=1_000)
        async with self.factory() as s1, self.factory() as s2:
            f1, f2 = FinanceRepository(s1), FinanceRepository(s2)
            self.assertEqual(await f1.get_balance(pid), 1_000)
            self.assertEqual(await f2.get_balance(pid), 1_000)
            await f1.apply_change(
                player_id=pid, amount=-800, category=TransactionCategory.PENALTY,
                idempotency_key="a",
            )
            await s1.commit()
            from app.exceptions import InsufficientFunds

            with self.assertRaises(InsufficientFunds):
                await f2.apply_change(
                    player_id=pid, amount=-800, category=TransactionCategory.PENALTY,
                    idempotency_key="b",
                )
            await s2.rollback()
        self.assertEqual(await self.balance(pid), 200)


class IdempotencyRaceRecoveryTests(DatabaseTestCase):
    async def test_lost_race_on_idempotency_key_rolls_back_money_and_reports_duplicate(self) -> None:
        """Запрос с тем же ключом проскочил проверку, но ключ уже занят победителем.

        Эмулируем: первый вызов get_by_key «не видит» запись (как при гонке), хотя она
        уже закоммичена. UPDATE денег выполнится, затем INSERT упрётся в уникальный
        ключ. Сервис обязан откатить деньги и вернуть результат победителя.
        """
        pid = await self.make_player(money=1_000)
        async with self.factory() as session:
            winner = await FinanceService(session).apply(
                player_id=pid, amount=-300, category=TransactionCategory.PENALTY,
                idempotency_key="race",
            )
        self.assertEqual(await self.balance(pid), 700)

        real_get = FinanceRepository.get_by_key
        calls = {"n": 0}

        async def blind_first_call(self_repo, key):
            calls["n"] += 1
            if calls["n"] == 1:
                return None
            return await real_get(self_repo, key)

        async with self.factory() as session:
            with patch.object(FinanceRepository, "get_by_key", blind_first_call):
                loser = await FinanceService(session).apply(
                    player_id=pid, amount=-300, category=TransactionCategory.PENALTY,
                    idempotency_key="race",
                )

        self.assertTrue(loser.duplicate)
        self.assertEqual(loser.transaction_id, winner.transaction_id)
        self.assertEqual(await self.balance(pid), 700)  # деньги второй раз не списаны
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM financial_transactions"), 1)
