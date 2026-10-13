"""Магазин, склад и ремонт с БД: покупки, совместимость, ремонт ровно один раз, проверка результата.

Требуют SQLAlchemy/aiosqlite (как и остальные тесты с БД).
"""

import asyncio

from sqlalchemy import text

from app.database import SCHEMA_VERSION
from app.exceptions import (
    InsufficientFunds,
    InvalidStatusTransition,
    MissingParts,
    NothingToVerify,
    OperationAlreadyDone,
    OrderNotFound,
    ShopStale,
    UnknownOperation,
)
from app.game_data.part_catalog import PART_TYPE_BY_CODE, fit_value, make_sku, spec_for
from app.game_data.fleet import tags_for_configuration
from app.game_data.catalog import CAR_CONFIGURATIONS
from app.repositories import InventoryRepository
from app.services import (
    DiagnosticService,
    InventoryService,
    RepairService,
    ShopService,
)
from app.services.transaction import atomic
from tests.test_diagnostics_service import DiagnosticsTestCase

_C = CAR_CONFIGURATIONS[0]  # Lada Granta 2018, 11186, МКПП
TAGS = tags_for_configuration(
    _C.brand, _C.model, _C.engine_code, _C.transmission, _C.engine_volume_cc
)


def sku(type_code: str, quality: int = 1) -> str:
    return make_sku(type_code, fit_value(PART_TYPE_BY_CODE[type_code], TAGS), quality)


class ShopRepairCase(DiagnosticsTestCase):
    async def prepare(self, truth: dict[str, str], conclude: list[str] | None = None):  # type: ignore[no-untyped-def]
        """Игрок, заказ со скрытой правдой, выполненная бесплатная проверка и заключение."""
        pid = await self.make_player()
        oid = await self.new_order(pid)
        await self.set_truth(pid, oid, truth)
        await self.check(pid, oid, "visual")
        if conclude is not None:
            async with self.factory() as session:
                await DiagnosticService(session).conclude(
                    player_id=pid, order_id=oid, cause_codes=conclude
                )
        return pid, oid

    async def buy(self, pid: int, oid: int, type_code: str, quality: int = 1, qty: int = 1):  # type: ignore[no-untyped-def]
        async with self.factory() as session:
            view = await ShopService(session).type_view(pid, type_code, oid)
        async with self.factory() as session:
            return await ShopService(session).buy(
                player_id=pid, type_code=type_code, quality=quality, quantity=qty,
                order_id=oid, ver=view.ver,
            )

    async def stock(self, pid: int, part_sku: str) -> int:
        return int(
            await self.scalar(
                "SELECT COALESCE(SUM(s.quantity), 0) FROM stock_items s JOIN parts p ON p.id = s.part_id "
                "WHERE s.player_id=:p AND p.sku=:k",
                p=pid, k=part_sku,
            )  # type: ignore[arg-type]
        )

    async def perform(self, pid: int, oid: int, op: str):  # type: ignore[no-untyped-def]
        async with self.factory() as session:
            return await RepairService(session).perform_operation(player_id=pid, order_id=oid, op_code=op)

    async def verify(self, pid: int, oid: int):  # type: ignore[no-untyped-def]
        async with self.factory() as session:
            return await RepairService(session).verify(player_id=pid, order_id=oid)

    async def finish(self, pid: int, oid: int):  # type: ignore[no-untyped-def]
        async with self.factory() as session:
            return await RepairService(session).finish(player_id=pid, order_id=oid)

    async def repair_overview(self, pid: int, oid: int):  # type: ignore[no-untyped-def]
        async with self.factory() as session:
            return await RepairService(session).get_overview(pid, oid)


class ShopTests(ShopRepairCase):
    async def test_purchase_debits_money_and_adds_stock_atomically(self) -> None:
        pid, oid = await self.prepare({"BAT_WEAK": ""})
        before = await self.balance(pid)
        result = await self.buy(pid, oid, "battery", 2, 2)
        spec = spec_for(sku("battery", 2))
        assert spec is not None
        self.assertEqual(result.total_price, spec.base_price * 2)
        self.assertEqual(await self.balance(pid), before - spec.base_price * 2)
        self.assertEqual(await self.stock(pid, sku("battery", 2)), 2)

    async def test_double_tap_on_same_screen_charges_once(self) -> None:
        pid, oid = await self.prepare({})
        async with self.factory() as session:
            view = await ShopService(session).type_view(pid, "pads", oid)
        before = await self.balance(pid)
        args = dict(player_id=pid, type_code="pads", quality=1, quantity=1, order_id=oid, ver=view.ver)
        async with self.factory() as session:
            first = await ShopService(session).buy(**args)
        async with self.factory() as session:
            second = await ShopService(session).buy(**args)
        self.assertFalse(first.duplicate)
        self.assertTrue(second.duplicate)
        self.assertEqual(before - await self.balance(pid), first.total_price)
        self.assertEqual(await self.stock(pid, sku("pads", 1)), 1)

    async def test_concurrent_double_tap_charges_once(self) -> None:
        pid, oid = await self.prepare({})
        async with self.factory() as session:
            view = await ShopService(session).type_view(pid, "pads", oid)
        before = await self.balance(pid)

        async def tap():  # type: ignore[no-untyped-def]
            async with self.factory() as session:
                return await ShopService(session).buy(
                    player_id=pid, type_code="pads", quality=1, quantity=1, order_id=oid, ver=view.ver
                )

        results = await asyncio.gather(tap(), tap(), return_exceptions=True)
        ok = [r for r in results if not isinstance(r, Exception)]
        self.assertGreaterEqual(len(ok), 1)
        price = spec_for(sku("pads", 1)).base_price  # type: ignore[union-attr]
        self.assertEqual(before - await self.balance(pid), price)
        self.assertEqual(await self.stock(pid, sku("pads", 1)), 1)

    async def test_stale_screen_is_rejected(self) -> None:
        pid, oid = await self.prepare({})
        async with self.factory() as session:
            view = await ShopService(session).type_view(pid, "pads", oid)
        async with self.factory() as session:
            await ShopService(session).buy(
                player_id=pid, type_code="pads", quality=1, quantity=1, order_id=oid, ver=view.ver
            )
        with self.assertRaises(ShopStale):
            async with self.factory() as session:
                await ShopService(session).buy(
                    player_id=pid, type_code="pads", quality=1, quantity=2, order_id=oid, ver=view.ver
                )
        self.assertEqual(await self.stock(pid, sku("pads", 1)), 1)

    async def test_insufficient_funds_changes_nothing(self) -> None:
        pid, oid = await self.prepare({})
        await self.set_money(pid, 100)
        with self.assertRaises(InsufficientFunds):
            await self.buy(pid, oid, "starter", 3, 1)
        self.assertEqual(await self.balance(pid), 100)
        self.assertEqual(await self.stock(pid, sku("starter", 3)), 0)

    async def test_balance_never_negative_after_many_purchases(self) -> None:
        pid, oid = await self.prepare({})
        await self.set_money(pid, 5_000)
        for _ in range(10):
            try:
                await self.buy(pid, oid, "alt", 1, 1)
            except InsufficientFunds:
                break
        self.assertGreaterEqual(await self.balance(pid), 0)

    async def test_fitment_part_requires_an_order(self) -> None:
        pid, _ = await self.prepare({})
        async with self.factory() as session:
            with self.assertRaises(OrderNotFound):
                await ShopService(session).type_view(pid, "pads", 0)
            view = await ShopService(session).type_view(pid, "fuse", 0)
        self.assertTrue(view.universal)
        self.assertEqual(len(view.qualities), 3)

    async def test_inventory_and_plan_after_restart(self) -> None:
        pid, oid = await self.prepare({"BAT_WEAK": ""}, ["BAT_WEAK"])
        await self.buy(pid, oid, "battery", 1, 1)
        await self.restart()
        async with self.factory() as session:
            lines = await ShopService(session).inventory(pid)
            plan = await ShopService(session).order_plan(pid, oid)
        self.assertEqual([l.sku for l in lines], [sku("battery", 1)])
        self.assertEqual(lines[0].quantity, 1)
        battery = next(l for l in plan.lines if l.type_code == "battery")
        self.assertEqual(battery.missing, 0)


class RepairTests(ShopRepairCase):
    async def test_operation_consumes_parts_exactly_once(self) -> None:
        pid, oid = await self.prepare({"BAT_WEAK": ""}, ["BAT_WEAK"])
        self.assertEqual(await self.status(oid), "awaiting_parts")
        await self.buy(pid, oid, "battery", 1, 2)
        result = await self.perform(pid, oid, "BAT_WEAK.1")
        self.assertTrue(result.fault_resolved)
        self.assertEqual(await self.stock(pid, sku("battery", 1)), 1)
        self.assertEqual(await self.status(oid), "in_repair")
        self.assertEqual(
            await self.scalar("SELECT COUNT(*) FROM repair_operations WHERE order_id=:o", o=oid), 1
        )
        self.assertEqual(await self.scalar("SELECT SUM(quantity) FROM order_parts WHERE order_id=:o", o=oid), 1)
        with self.assertRaises(OperationAlreadyDone):
            await self.perform(pid, oid, "BAT_WEAK.1")
        self.assertEqual(await self.stock(pid, sku("battery", 1)), 1)  # повтор ничего не списал

    async def test_concurrent_presses_apply_once(self) -> None:
        pid, oid = await self.prepare({"BAT_WEAK": ""}, ["BAT_WEAK"])
        await self.buy(pid, oid, "battery", 1, 2)
        results = await asyncio.gather(
            self.perform(pid, oid, "BAT_WEAK.1"), self.perform(pid, oid, "BAT_WEAK.1"),
            return_exceptions=True,
        )
        self.assertEqual(sum(1 for r in results if not isinstance(r, Exception)), 1)
        self.assertEqual(await self.stock(pid, sku("battery", 1)), 1)

    async def test_missing_parts_change_nothing(self) -> None:
        pid, oid = await self.prepare({"BAT_WEAK": ""}, ["BAT_WEAK"])
        with self.assertRaises(MissingParts):
            await self.perform(pid, oid, "BAT_WEAK.1")
        overview = await self.repair_overview(pid, oid)
        self.assertFalse(overview.faults[0].resolved)
        self.assertEqual(await self.status(oid), "awaiting_parts")
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM repair_operations"), 0)

    async def test_incompatible_stock_is_not_used(self) -> None:
        pid, oid = await self.prepare({"BAT_WEAK": ""}, ["BAT_WEAK"])
        wrong = "battery:75:2"  # класс АКБ, не подходящий Granta
        spec = spec_for(wrong)
        assert spec is not None
        async with self.factory() as session:
            async with atomic(session):
                await InventoryRepository(session).seed_parts((spec,))
        async with self.factory() as session:
            await InventoryService(session).purchase_part(player_id=pid, sku=wrong, quantity=1)
        with self.assertRaises(MissingParts):
            await self.perform(pid, oid, "BAT_WEAK.1")
        self.assertEqual(await self.stock(pid, wrong), 1)

    async def test_unknown_or_foreign_operation(self) -> None:
        pid, oid = await self.prepare({"BAT_WEAK": ""}, ["BAT_WEAK"])
        with self.assertRaises(UnknownOperation):
            await self.perform(pid, oid, "NOPE.1")
        with self.assertRaises(UnknownOperation):  # неисправности ALT_FAIL в заказе нет
            await self.perform(pid, oid, "ALT_FAIL.1")

    async def test_multiple_faults_full_cycle_and_reward_once(self) -> None:
        pid, oid = await self.prepare(
            {"BAT_WEAK": "", "PLUGS_WORN": ""}, ["BAT_WEAK", "PLUGS_WORN"]
        )
        await self.buy(pid, oid, "battery", 2, 1)
        await self.buy(pid, oid, "plugs", 1, 1)
        await self.perform(pid, oid, "BAT_WEAK.1")
        with self.assertRaises(NothingToVerify):  # ещё не всё устранено
            await self.verify(pid, oid)
        with self.assertRaises(InvalidStatusTransition):  # сдать до проверки нельзя
            await self.finish(pid, oid)
        done = await self.perform(pid, oid, "PLUGS_WORN.1")
        self.assertTrue(done.all_resolved)
        check = await self.verify(pid, oid)
        self.assertTrue(check.ok)
        self.assertEqual(await self.status(oid), "ready")
        before = await self.balance(pid)
        first = await self.finish(pid, oid)
        self.assertFalse(first.already_completed)
        self.assertEqual(first.reward_paid, 3_000 + 450)  # премия 15 % за срок
        self.assertEqual(await self.balance(pid), before + 3_450)
        again = await self.finish(pid, oid)
        self.assertTrue(again.already_completed)
        self.assertEqual(await self.balance(pid), before + 3_450)
        self.assertEqual(await self.status(oid), "completed")

    async def test_wrong_diagnosis_fails_verification_then_reopens_diagnostics(self) -> None:
        pid, oid = await self.prepare({"PLUGS_WORN": ""}, ["BAT_WEAK"])  # игрок ошибся
        await self.buy(pid, oid, "battery", 1, 1)
        await self.perform(pid, oid, "BAT_WEAK.1")
        check = await self.verify(pid, oid)
        self.assertFalse(check.ok)
        self.assertTrue(check.complaint_remains)
        self.assertEqual(await self.status(oid), "in_repair")
        overview = await self.overview(pid, oid)
        self.assertFalse(overview.concluded)
        self.assertTrue(overview.can_run)
        # игрок продолжает диагностику и записывает верную причину
        await self.check(pid, oid, "visual", expected=None)
        async with self.factory() as session:
            allowed = await DiagnosticService(session).conclusion_causes(pid, oid)
            await DiagnosticService(session).conclude(
                player_id=pid, order_id=oid, cause_codes=["PLUGS_WORN"]
            )
        self.assertTrue(allowed)
        await self.buy(pid, oid, "plugs", 1, 1)
        await self.perform(pid, oid, "PLUGS_WORN.1")
        self.assertTrue((await self.verify(pid, oid)).ok)
        self.assertEqual(await self.status(oid), "ready")

    async def test_fault_with_two_operations_resolves_after_both(self) -> None:
        pid, oid = await self.prepare({"TIE_ROD": "left"}, ["TIE_ROD"])
        await self.buy(pid, oid, "tierod", 1, 1)
        first = await self.perform(pid, oid, "TIE_ROD.1")
        self.assertFalse(first.fault_resolved)
        second = await self.perform(pid, oid, "TIE_ROD.2")  # развал-схождение, без деталей
        self.assertTrue(second.fault_resolved)

    async def test_progress_survives_restart(self) -> None:
        pid, oid = await self.prepare({"BAT_WEAK": ""}, ["BAT_WEAK"])
        await self.buy(pid, oid, "battery", 1, 1)
        await self.perform(pid, oid, "BAT_WEAK.1")
        await self.restart()
        overview = await self.repair_overview(pid, oid)
        self.assertTrue(overview.faults[0].resolved)
        self.assertTrue(overview.faults[0].ops[0].done)
        self.assertTrue(overview.can_verify)
        with self.assertRaises(OperationAlreadyDone):
            await self.perform(pid, oid, "BAT_WEAK.1")

    async def test_other_players_order_is_not_accessible(self) -> None:
        pid, oid = await self.prepare({"BAT_WEAK": ""}, ["BAT_WEAK"])
        other = await self.make_player(telegram_id=2)
        with self.assertRaises(OrderNotFound):
            await self.repair_overview(other, oid)


class MigrationTests(ShopRepairCase):
    async def test_upgrade_from_schema_4_keeps_data(self) -> None:
        pid, oid = await self.prepare({"BAT_WEAK": ""}, ["BAT_WEAK"])
        async with self.factory() as session:
            await session.execute(text("DROP TABLE repair_operations"))
            await session.execute(text("PRAGMA user_version = 4"))
            await session.commit()
        await self.restart()  # init_db: create_all + повышение версии
        self.assertEqual(await self.scalar("PRAGMA user_version"), SCHEMA_VERSION)
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM repair_operations"), 0)
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM faults WHERE order_id=:o", o=oid), 1)
        await self.buy(pid, oid, "battery", 1, 1)
        await self.perform(pid, oid, "BAT_WEAK.1")
