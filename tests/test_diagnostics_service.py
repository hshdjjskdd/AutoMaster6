"""Тесты диагностики с БД: проверки, деньги, время, журнал, заключение, изоляция."""

import asyncio
import json
import random
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.exceptions import (
    DiagnosticsConcluded,
    DiagnosticsNotStarted,
    DiagnosticStale,
    InsufficientFunds,
    InvalidConclusion,
    InvalidOrderState,
    OrderNotFound,
    UnknownCheck,
)
from app.game_data.diagnostic_checks import DEADLINE_MINUTES_PER_GAME_MINUTE
from app.game_data.enums import OrderStatus
from app.game_data.fault_catalog import CAUSE_BY_CODE, SCENARIO_CAUSES
from app.services import ClientOrderService, DiagnosticService, InventoryService, OrderService
from tests.base import DatabaseTestCase

DEADLINE = datetime(2030, 1, 1, 12, 0, tzinfo=UTC)


class DiagnosticsTestCase(DatabaseTestCase):
    async def new_order(self, pid: int, *, with_deadline: bool = True) -> int:
        car = await self.make_car(pid)
        async with self.factory() as session:
            order = await OrderService(session).create_order(
                player_id=pid,
                car_id=car.id,
                customer_name="Клиент",
                complaint="Не заводится",
                reward=3_000,
                deadline_at=DEADLINE if with_deadline else None,
            )
        return order.id

    async def set_truth(self, pid: int, order_id: int, truth: dict[str, str]) -> None:
        """Подменяет скрытую поломку (создаёт сессию заранее, генератор уже не сработает)."""
        async with self.factory() as session:
            await session.execute(
                text("INSERT INTO diagnostic_sessions (order_id, player_id, minutes_spent, money_spent, created_at)"
                     " VALUES (:o, :p, 0, 0, '2026-01-01 00:00:00')"),
                {"o": order_id, "p": pid},
            )
            for code, detail in truth.items():
                await session.execute(
                    text("INSERT INTO hidden_faults (order_id, cause_code, detail) VALUES (:o, :c, :d)"),
                    {"o": order_id, "c": code, "d": detail},
                )
            await session.commit()

    async def check(self, pid: int, order_id: int, code: str, expected: int | None = None):  # type: ignore[no-untyped-def]
        async with self.factory() as session:
            return await DiagnosticService(session).run_check(
                player_id=pid, order_id=order_id, check_code=code, expected_runs=expected
            )

    async def overview(self, pid: int, order_id: int):  # type: ignore[no-untyped-def]
        async with self.factory() as session:
            return await DiagnosticService(session).get_overview(pid, order_id)

    async def status(self, order_id: int) -> str:
        return str(await self.scalar("SELECT status FROM orders WHERE id=:i", i=order_id))

    def value(self, run, label: str) -> float:  # type: ignore[no-untyped-def]
        return float(next(r.value for r in run.readings if r.label == label))

    def flags(self, run) -> set[str]:  # type: ignore[no-untyped-def]
        return {r.flag for r in run.readings}


class RunCheckTests(DiagnosticsTestCase):
    async def test_first_check_starts_diagnostics_and_is_saved(self) -> None:
        pid = await self.make_player()
        oid = await self.new_order(pid)
        await self.set_truth(pid, oid, {"BAT_WEAK": ""})
        run = await self.check(pid, oid, "battery")
        self.assertEqual(run.run_no, 1)
        self.assertEqual(run.check_code, "battery")
        self.assertEqual(await self.status(oid), "diagnostics")
        self.assertTrue(run.readings)
        stored = await self.scalar("SELECT COUNT(*) FROM diagnostic_check_runs WHERE order_id=:i", i=oid)
        self.assertEqual(stored, 1)
        async with self.factory() as session:
            journal = await DiagnosticService(session).get_journal(pid, oid)
        self.assertEqual(journal, [run])

    async def test_costs_time_and_money(self) -> None:
        pid = await self.make_player()
        oid = await self.new_order(pid)
        await self.set_truth(pid, oid, {})
        run = await self.check(pid, oid, "battery")  # мультиметра нет: аренда 150
        self.assertEqual(run.cost, 150)
        self.assertFalse(run.tool_owned)
        self.assertEqual(await self.balance(pid), 15_000 - 150)
        ledger = await self.scalar(
            "SELECT amount || ':' || category || ':' || order_id FROM financial_transactions WHERE order_id=:i",
            i=oid,
        )
        self.assertEqual(ledger, f"-150:adjustment:{oid}")
        overview = await self.overview(pid, oid)
        self.assertEqual(overview.minutes_spent, 5)
        self.assertEqual(overview.money_spent, 150)
        self.assertEqual(overview.runs, 1)
        self.assertEqual(
            overview.deadline_at, DEADLINE - timedelta(minutes=5 * DEADLINE_MINUTES_PER_GAME_MINUTE)
        )

    async def test_own_tool_makes_check_free(self) -> None:
        pid = await self.make_player()
        oid = await self.new_order(pid)
        await self.set_truth(pid, oid, {})
        async with self.factory() as session:
            await InventoryService(session).buy_equipment(player_id=pid, code="MULTIMETER")
        money_after_purchase = await self.balance(pid)
        run = await self.check(pid, oid, "battery")
        self.assertEqual(run.cost, 0)
        self.assertTrue(run.tool_owned)
        self.assertEqual(await self.balance(pid), money_after_purchase)

    async def test_consumables_are_paid_even_with_tool(self) -> None:
        pid = await self.make_player()
        oid = await self.new_order(pid)
        await self.set_truth(pid, oid, {})
        async with self.factory() as session:
            await InventoryService(session).buy_equipment(player_id=pid, code="TOOLSET-BASIC")
        before = await self.balance(pid)
        run = await self.check(pid, oid, "intake")
        self.assertEqual(run.cost, 100)
        self.assertEqual(await self.balance(pid), before - 100)

    async def test_insufficient_funds_changes_nothing(self) -> None:
        pid = await self.make_player(money=100)
        oid = await self.new_order(pid)
        with self.assertRaises(InsufficientFunds):
            await self.check(pid, oid, "fuel")  # аренда 600
        self.assertEqual(await self.balance(pid), 100)
        self.assertEqual(await self.status(oid), "new")
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM diagnostic_check_runs"), 0)
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM diagnostic_sessions"), 0)
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM hidden_faults"), 0)
        overview = await self.overview(pid, oid)
        self.assertEqual(overview.deadline_at, DEADLINE)

    async def test_free_visual_check_works_with_no_money(self) -> None:
        pid = await self.make_player(money=0)
        oid = await self.new_order(pid)
        run = await self.check(pid, oid, "visual")
        self.assertEqual(run.cost, 0)

    async def test_order_without_deadline(self) -> None:
        pid = await self.make_player()
        oid = await self.new_order(pid, with_deadline=False)
        await self.check(pid, oid, "visual")
        self.assertIsNone((await self.overview(pid, oid)).deadline_at)

    async def test_unknown_check_rejected(self) -> None:
        pid = await self.make_player()
        oid = await self.new_order(pid)
        with self.assertRaises(UnknownCheck):
            await self.check(pid, oid, "magic")

    async def test_repeat_is_allowed_and_charged_again_with_new_noise(self) -> None:
        pid = await self.make_player()
        oid = await self.new_order(pid)
        await self.set_truth(pid, oid, {})
        a = await self.check(pid, oid, "battery")
        b = await self.check(pid, oid, "battery")
        self.assertEqual((a.run_no, b.run_no), (1, 2))
        self.assertEqual(await self.balance(pid), 15_000 - 300)
        self.assertNotEqual(a.readings[0].value, b.readings[0].value)

    async def test_only_new_and_diagnostics_orders_can_be_checked(self) -> None:
        pid = await self.make_player()
        oid = await self.new_order(pid)
        await self.move_order(pid, oid, OrderStatus.IN_REPAIR)
        with self.assertRaises(InvalidOrderState):
            await self.check(pid, oid, "visual")
        self.assertFalse((await self.overview(pid, oid)).can_run)


class TruthTests(DiagnosticsTestCase):
    async def test_readings_follow_hidden_truth(self) -> None:
        pid = await self.make_player()
        weak = await self.new_order(pid)
        await self.set_truth(pid, weak, {"BAT_WEAK": ""})
        run = await self.check(pid, weak, "battery")
        self.assertIn(run.readings[0].flag, ("warn", "bad"))
        charging = await self.check(pid, weak, "alternator")
        self.assertGreater(self.value(charging, "Напряжение бортсети, холостой ход"), 14.0)

        pid2 = await self.make_player(2)
        alt = await self.new_order(pid2)
        await self.set_truth(pid2, alt, {"ALT_FAIL": "no_charge"})
        charging = await self.check(pid2, alt, "alternator")
        self.assertLess(self.value(charging, "Напряжение бортсети, холостой ход"), 13.0)
        self.assertIn("bad", self.flags(charging))

    async def test_truth_created_once_and_stable_after_restart(self) -> None:
        pid = await self.make_player()
        oid = await self.new_order(pid)
        await self.check(pid, oid, "visual")
        rows = await self.scalar("SELECT group_concat(cause_code || ':' || detail) FROM hidden_faults WHERE order_id=:i", i=oid)
        count = await self.scalar("SELECT COUNT(*) FROM hidden_faults WHERE order_id=:i", i=oid)
        self.assertIn(count, (1, 2))
        await self.restart()
        await self.check(pid, oid, "battery")
        await self.check(pid, oid, "visual")
        self.assertEqual(
            rows,
            await self.scalar("SELECT group_concat(cause_code || ':' || detail) FROM hidden_faults WHERE order_id=:i", i=oid),
        )

    async def test_truth_matches_client_scenario(self) -> None:
        pid = await self.make_player()
        async with self.factory() as session:
            board = await ClientOrderService(session, random.Random(11)).get_board(pid)
        async with self.factory() as session:
            accepted = await ClientOrderService(session).accept_offer(pid, board.offers[0].offer_id)
        scenario = await self.scalar(
            "SELECT scenario_code FROM client_offers WHERE order_id=:i", i=accepted.order_id
        )
        await self.check(pid, accepted.order_id, "visual")
        async with self.factory() as session:
            rows = (await session.execute(
                text("SELECT cause_code FROM hidden_faults WHERE order_id=:i ORDER BY id"),
                {"i": accepted.order_id},
            )).all()
        primary = rows[0][0]
        self.assertIn(primary, {c for c, _ in SCENARIO_CAUSES[str(scenario)]})

    async def test_views_never_leak_the_truth(self) -> None:
        pid = await self.make_player()
        oid = await self.new_order(pid)
        await self.set_truth(pid, oid, {"COOLANT_LEAK": ""})
        for code in ("visual", "cooling", "obd"):
            await self.check(pid, oid, code)
        async with self.factory() as session:
            service = DiagnosticService(session)
            blob = json.dumps(
                [r.model_dump(mode="json") for r in await service.get_journal(pid, oid)]
                + [(await service.get_overview(pid, oid)).model_dump(mode="json")],
                ensure_ascii=False,
            )
        for code, cause in CAUSE_BY_CODE.items():
            self.assertNotIn(code, blob)
            self.assertNotIn(cause.name, blob)


class SafetyTests(DiagnosticsTestCase):
    async def test_double_click_is_charged_once(self) -> None:
        pid = await self.make_player()
        oid = await self.new_order(pid)
        await self.set_truth(pid, oid, {})
        await self.check(pid, oid, "battery", expected=0)
        with self.assertRaises(DiagnosticStale):
            await self.check(pid, oid, "battery", expected=0)
        self.assertEqual(await self.balance(pid), 15_000 - 150)
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM diagnostic_check_runs"), 1)

    async def test_concurrent_clicks_run_one_check(self) -> None:
        pid = await self.make_player()
        oid = await self.new_order(pid)
        await self.set_truth(pid, oid, {})
        results = await asyncio.gather(
            *(self.check(pid, oid, "battery", expected=0) for _ in range(5)),
            return_exceptions=True,
        )
        ok = [r for r in results if not isinstance(r, BaseException)]
        self.assertEqual(len(ok), 1, results)
        self.assertEqual(await self.balance(pid), 15_000 - 150)
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM diagnostic_check_runs"), 1)

    async def test_players_are_isolated(self) -> None:
        a = await self.make_player(1)
        b = await self.make_player(2)
        oid = await self.new_order(a)
        await self.check(a, oid, "visual")
        with self.assertRaises(OrderNotFound):
            await self.check(b, oid, "visual")
        async with self.factory() as session:
            service = DiagnosticService(session)
            with self.assertRaises(OrderNotFound):
                await service.get_journal(b, oid)
            with self.assertRaises(OrderNotFound):
                await service.get_overview(b, oid)
            with self.assertRaises(OrderNotFound):
                await service.get_run(b, oid, 1)
            with self.assertRaises(OrderNotFound):
                await service.conclude(player_id=b, order_id=oid, cause_codes=["BAT_WEAK"])
        self.assertEqual(await self.balance(b), 15_000)

    async def test_journal_survives_restart(self) -> None:
        pid = await self.make_player()
        oid = await self.new_order(pid)
        await self.check(pid, oid, "visual")
        await self.check(pid, oid, "battery")
        async with self.factory() as session:
            before = await DiagnosticService(session).get_journal(pid, oid)
        await self.restart()
        async with self.factory() as session:
            after = await DiagnosticService(session).get_journal(pid, oid)
            overview = await DiagnosticService(session).get_overview(pid, oid)
        self.assertEqual(before, after)
        self.assertEqual(overview.runs, 2)

    async def test_overview_lists_all_checks_with_ownership(self) -> None:
        pid = await self.make_player()
        oid = await self.new_order(pid)
        overview = await self.overview(pid, oid)
        codes = {o.code for o in overview.options}
        self.assertGreaterEqual(
            codes,
            {"battery", "alternator", "fuses", "starter", "plugs", "obd", "fuel", "intake",
             "cooling", "brakes", "suspension"},
        )
        fuel = next(o for o in overview.options if o.code == "fuel")
        self.assertEqual((fuel.fee, fuel.tool_owned), (600, False))
        self.assertTrue(overview.can_run)
        async with self.factory() as session:
            tools = await DiagnosticService(session).list_tools(pid)
        self.assertEqual(
            [t.code for t in tools],
            ["TOOLSET-BASIC", "MULTIMETER", "OBD-SCANNER", "FUEL-PRESSURE-KIT", "BRAKE-SUSP-TESTER"],
        )
        self.assertTrue(all(not t.owned for t in tools))


class ConclusionTests(DiagnosticsTestCase):
    async def conclude(self, pid: int, oid: int, codes: list[str]):  # type: ignore[no-untyped-def]
        async with self.factory() as session:
            return await DiagnosticService(session).conclude(
                player_id=pid, order_id=oid, cause_codes=codes
            )

    async def test_requires_checks_first(self) -> None:
        pid = await self.make_player()
        oid = await self.new_order(pid)
        with self.assertRaises(DiagnosticsNotStarted):
            await self.conclude(pid, oid, ["BAT_WEAK"])

    async def test_conclusion_records_faults_and_closes_diagnostics(self) -> None:
        pid = await self.make_player()
        oid = await self.new_order(pid)
        await self.set_truth(pid, oid, {"BAT_WEAK": ""})
        await self.check(pid, oid, "battery")
        result = await self.conclude(pid, oid, ["BAT_WEAK", "ALT_FAIL", "BAT_WEAK"])
        self.assertEqual([f.code for f in result.faults], ["BAT_WEAK", "ALT_FAIL"])
        codes = await self.scalar(
            "SELECT group_concat(code) FROM (SELECT code FROM faults WHERE order_id=:i ORDER BY id)", i=oid
        )
        self.assertEqual(codes, "BAT_WEAK,ALT_FAIL")
        with self.assertRaises(DiagnosticsConcluded):
            await self.conclude(pid, oid, ["BAT_WEAK"])
        with self.assertRaises(DiagnosticsConcluded):
            await self.check(pid, oid, "alternator")
        overview = await self.overview(pid, oid)
        self.assertTrue(overview.concluded)
        self.assertFalse(overview.can_run)
        # скрытая правда не менялась и не раскрыта
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM hidden_faults WHERE order_id=:i", i=oid), 1)

    async def test_validation(self) -> None:
        pid = await self.make_player()
        oid = await self.new_order(pid)
        await self.check(pid, oid, "visual")
        with self.assertRaises(InvalidConclusion):
            await self.conclude(pid, oid, [])
        with self.assertRaises(InvalidConclusion):
            await self.conclude(pid, oid, ["BAT_WEAK", "ALT_FAIL", "FUSE_BLOWN", "WIRE_CORR"])
        with self.assertRaises(InvalidConclusion):
            await self.conclude(pid, oid, ["NOPE"])
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM faults WHERE order_id=:i", i=oid), 0)
        self.assertFalse((await self.overview(pid, oid)).concluded)

    async def test_cancel_after_diagnostics_start_costs_reputation(self) -> None:
        pid = await self.make_player()
        async with self.factory() as session:
            board = await ClientOrderService(session, random.Random(5)).get_board(pid)
        async with self.factory() as session:
            accepted = await ClientOrderService(session).accept_offer(pid, board.offers[0].offer_id)
        await self.check(pid, accepted.order_id, "visual")
        async with self.factory() as session:
            result = await ClientOrderService(session).cancel_order(pid, accepted.order_id)
        self.assertEqual(result.reputation_penalty, 5)
