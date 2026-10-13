"""Этап 6 с БД: обновление доски раз в 2 часа, перезапуск, гонки, экономика заказа.

Требуют SQLAlchemy/aiosqlite (как и остальные тесты с БД).
"""

import asyncio
import random
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.database import SCHEMA_VERSION
from app.exceptions import InsufficientFunds, InvalidOrderState, OfferUnavailable
from app.game_data.economy import BOARD_SIZE, INITIAL_OFFERS, OFFER_LIFETIME_HOURS, REFRESH_INTERVAL_HOURS
from app.game_data.enums import OrderStatus
from app.game_data.order_planner import parse_plan
from app.game_data.repair_catalog import ops_for_cause
from app.repositories import DiagnosticRepository
from app.services import ClientOrderService, EconomyService
from app.services.board_refresher import refresh_due_boards
from tests.test_shop_repair import ShopRepairCase

T0 = datetime.now(UTC)
INTERVAL = timedelta(hours=REFRESH_INTERVAL_HOURS)


class DynamicBoardTests(ShopRepairCase):
    async def refresh(self, pid: int, now: datetime, seed: int = 1):  # type: ignore[no-untyped-def]
        async with self.factory() as session:
            return await ClientOrderService(session, random.Random(seed)).refresh_if_due(pid, now=now)

    async def board(self, pid: int, now: datetime | None = None, seed: int = 1):  # type: ignore[no-untyped-def]
        async with self.factory() as session:
            return await ClientOrderService(session, random.Random(seed)).get_board(pid, now=now)

    async def offer_count(self, pid: int, status: str = "available") -> int:
        return int(await self.scalar(
            "SELECT COUNT(*) FROM client_offers WHERE player_id=:i AND status=:s", i=pid, s=status
        ))  # type: ignore[arg-type]

    # --- расписание ----------------------------------------------------------------

    async def test_first_refresh_gives_initial_board_and_schedules_next(self) -> None:
        pid = await self.make_player()
        result = await self.refresh(pid, T0)
        self.assertTrue(result.refreshed)
        self.assertGreaterEqual(len(result.created_tiers), INITIAL_OFFERS)
        self.assertEqual(result.next_refresh_at, T0 + INTERVAL)
        self.assertEqual(await self.offer_count(pid), len(result.created_tiers))

    async def test_two_hour_interval(self) -> None:
        pid = await self.make_player()
        await self.refresh(pid, T0)
        early = await self.refresh(pid, T0 + INTERVAL - timedelta(minutes=1), seed=2)
        self.assertFalse(early.refreshed)
        self.assertEqual(early.created_tiers, ())
        due = await self.refresh(pid, T0 + INTERVAL, seed=3)
        self.assertTrue(due.refreshed)
        self.assertEqual(due.next_refresh_at, T0 + 2 * INTERVAL)

    async def test_repeated_press_and_restart_do_not_duplicate(self) -> None:
        pid = await self.make_player()
        await self.refresh(pid, T0)
        count = await self.offer_count(pid)
        for _ in range(3):
            await self.refresh(pid, T0 + timedelta(minutes=5))
        await self.restart()
        again = await self.refresh(pid, T0 + timedelta(minutes=10))
        self.assertFalse(again.refreshed)
        self.assertEqual(await self.offer_count(pid), count)
        self.assertEqual(again.next_refresh_at, T0 + INTERVAL)  # время пережило перезапуск

    async def test_concurrent_refresh_creates_one_batch(self) -> None:
        pid = await self.make_player()
        await self.refresh(pid, T0)
        due = T0 + INTERVAL
        before = await self.offer_count(pid)
        results = await asyncio.gather(*(self.refresh(pid, due, seed=s) for s in range(6)))
        self.assertEqual(sum(r.refreshed for r in results), 1)
        winner = next(r for r in results if r.refreshed)
        self.assertEqual(await self.offer_count(pid), before + len(winner.created_tiers))

    async def test_board_never_exceeds_limit(self) -> None:
        pid = await self.make_player()
        now = T0
        for step in range(40):
            await self.refresh(pid, now, seed=step)
            self.assertLessEqual(await self.offer_count(pid), BOARD_SIZE)
            now += INTERVAL
        self.assertEqual(BOARD_SIZE, 10)

    async def test_long_downtime_does_not_flood_board(self) -> None:
        pid = await self.make_player()
        await self.refresh(pid, T0)
        later = T0 + timedelta(days=30)
        await self.refresh(pid, later, seed=4)
        self.assertLessEqual(await self.offer_count(pid), BOARD_SIZE)

    async def test_accepted_order_survives_refreshes_and_restart(self) -> None:
        pid = await self.make_player()
        board = await self.board(pid, T0)
        offer = board.offers[0]
        async with self.factory() as session:
            accepted = await ClientOrderService(session).accept_offer(pid, offer.offer_id, now=T0)
        for k in range(1, 5):
            await self.refresh(pid, T0 + k * INTERVAL * 6, seed=k)  # дальше срока жизни предложений
        await self.restart()
        async with self.factory() as session:
            orders = await ClientOrderService(session).list_workshop(pid)
        self.assertEqual([o.order_id for o in orders], [accepted.order_id])
        self.assertEqual(orders[0].status, OrderStatus.NEW)
        self.assertGreater(OFFER_LIFETIME_HOURS, 0)

    async def test_double_accept_is_rejected(self) -> None:
        pid = await self.make_player()
        offer = (await self.board(pid, T0)).offers[0]
        async with self.factory() as session:
            await ClientOrderService(session).accept_offer(pid, offer.offer_id, now=T0)
        with self.assertRaises(OfferUnavailable):
            async with self.factory() as session:
                await ClientOrderService(session).accept_offer(pid, offer.offer_id, now=T0)

    async def test_background_refresh_notifies_once(self) -> None:
        pid = await self.make_player()
        await self.board(pid, T0)  # создаёт состояние доски
        notices = await refresh_due_boards(self.factory, now=T0 + INTERVAL, rng=random.Random(2))
        again = await refresh_due_boards(self.factory, now=T0 + INTERVAL, rng=random.Random(2))
        self.assertEqual(again, [])
        self.assertLessEqual(len(notices), 1)
        for notice in notices:
            self.assertEqual(notice.player_id, pid)
            self.assertTrue(notice.result.created_tiers)

    async def test_pity_counter_is_persisted(self) -> None:
        pid = await self.make_player()
        await self.refresh(pid, T0)
        await self.set_streak(pid, 3)
        await self.restart()
        self.assertEqual(await self.scalar("SELECT empty_streak FROM order_board_state WHERE player_id=:i", i=pid), 3)

    async def set_streak(self, pid: int, value: int) -> None:
        async with self.factory() as session:
            await session.execute(
                text("UPDATE order_board_state SET empty_streak=:v WHERE player_id=:i"), {"v": value, "i": pid}
            )
            await session.commit()

    # --- заказ → деньги ------------------------------------------------------------

    async def play_order(self, pid: int):  # type: ignore[no-untyped-def]
        """Принимает лёгкий заказ и честно проходит диагностику, покупку деталей и ремонт."""
        board = await self.board(pid, T0)
        offer = next(o for o in board.offers if o.tier == 1)
        async with self.factory() as session:
            accepted = await ClientOrderService(session).accept_offer(pid, offer.offer_id, now=T0)
        oid = accepted.order_id
        await self.check(pid, oid, "visual")
        async with self.factory() as session:
            truth = await DiagnosticRepository(session).list_hidden(oid)
            planned = await session.scalar(
                text("SELECT planned_faults FROM client_offers WHERE id=:i"), {"i": offer.offer_id}
            )
        return pid, oid, offer, truth, parse_plan(planned)

    async def repair_all(self, pid: int, oid: int, causes: list[str]) -> None:
        from app.services import DiagnosticService

        async with self.factory() as session:
            await DiagnosticService(session).conclude(player_id=pid, order_id=oid, cause_codes=causes)
        for cause in causes:
            for op in ops_for_cause(cause):
                for need in op.needs:
                    await self.buy(pid, oid, need.type_code, 2, need.qty)
                await self.perform(pid, oid, op.code)

    async def test_hidden_faults_follow_the_plan(self) -> None:
        pid = await self.make_player()
        _, _, _, truth, planned = await self.play_order(pid)
        self.assertEqual(set(truth), {f.code for f in planned})
        self.assertEqual(len(truth), 1)  # лёгкий заказ — одна неисправность

    async def test_full_order_pays_once_and_profit_is_correct(self) -> None:
        pid = await self.make_player(money=5_000_000)
        _, oid, offer, truth, _ = await self.play_order(pid)
        before = await self.balance(pid)
        await self.repair_all(pid, oid, list(truth))
        spent = before - await self.balance(pid)
        verification = await self.verify(pid, oid)
        self.assertTrue(verification.ok)
        self.assertEqual(await self.balance(pid), before - spent)  # без ремонта денег не прибавилось
        done = await self.finish(pid, oid)
        self.assertFalse(done.already_completed)
        self.assertEqual(done.profit, done.reward_paid - done.parts_cost)
        after_first = await self.balance(pid)
        self.assertEqual(after_first, before - spent + done.reward_paid)
        self.assertGreaterEqual(done.reward_paid, offer.payment)
        again = await self.finish(pid, oid)  # повторная выплата невозможна
        self.assertTrue(again.already_completed)
        self.assertEqual(await self.balance(pid), after_first)
        summary = await self._summary(pid)
        self.assertEqual((summary.orders_done, summary.revenue), (1, done.reward_paid))
        self.assertEqual(summary.expenses, done.parts_cost)
        self.assertEqual(summary.profit, summary.revenue - summary.expenses)
        await self.restart()
        again_summary = await self._summary(pid)
        self.assertEqual(again_summary, summary)  # итоги и баланс пережили перезапуск

    async def _summary(self, pid: int):  # type: ignore[no-untyped-def]
        async with self.factory() as session:
            return await EconomyService(session).summary(pid)

    async def test_no_money_without_finished_repair(self) -> None:
        pid = await self.make_player(money=5_000_000)
        _, oid, _, truth, _ = await self.play_order(pid)
        before = await self.balance(pid)
        with self.assertRaises(InvalidOrderState):
            await self.finish(pid, oid)
        self.assertEqual(await self.balance(pid), before)
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM repair_history WHERE order_id=:o", o=oid), 0)

    async def test_insufficient_funds_for_parts(self) -> None:
        pid = await self.make_player(money=0)
        _, oid, _, truth, _ = await self.play_order(pid)
        cause = next(iter(truth))
        need = next(n for op in ops_for_cause(cause) for n in op.needs)
        from app.services import DiagnosticService

        async with self.factory() as session:
            await DiagnosticService(session).conclude(player_id=pid, order_id=oid, cause_codes=[cause])
        with self.assertRaises(InsufficientFunds):
            await self.buy(pid, oid, need.type_code, 2, need.qty)
        self.assertEqual(await self.balance(pid), 0)

    async def test_schema_upgrade_from_5_adds_columns_and_keeps_offers(self) -> None:
        pid = await self.make_player()
        await self.board(pid, T0)
        kept = await self.offer_count(pid)
        async with self.factory() as session:
            await session.execute(text("DROP TABLE order_board_state"))
            await session.execute(text("ALTER TABLE client_offers DROP COLUMN tier"))
            await session.execute(text("ALTER TABLE client_offers DROP COLUMN planned_faults"))
            await session.execute(text("ALTER TABLE client_offers DROP COLUMN est_cost"))
            await session.execute(text("PRAGMA user_version = 5"))
            await session.commit()
        await self.restart()
        self.assertEqual(await self.scalar("PRAGMA user_version"), SCHEMA_VERSION)
        self.assertEqual(await self.offer_count(pid), kept)
        self.assertEqual(await self.scalar("SELECT MIN(tier) FROM client_offers"), 1)
        board = await self.board(pid, T0 + timedelta(minutes=1))
        self.assertEqual(len(board.offers), kept)
