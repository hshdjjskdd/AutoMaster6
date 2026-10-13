"""Данные сохраняются после перезапуска бота."""

from app.exceptions import InsufficientFunds
from app.game_data.enums import (
    DiagnosticOutcome,
    FaultSeverity,
    OrderStatus,
    TransactionCategory,
)
from app.services import (
    FinanceService,
    GarageService,
    InventoryService,
    OrderService,
    PlayerService,
    ProgressService,
)
from tests.base import DatabaseTestCase


class PersistenceTests(DatabaseTestCase):
    async def test_everything_survives_restart(self) -> None:
        player_id = await self.make_player(telegram_id=77)
        car = await self.make_car(player_id)

        async with self.factory() as session:
            await InventoryService(session).purchase_part(
                player_id=player_id, sku="BRK-PAD-F", quantity=3, idempotency_key="p1"
            )
            await InventoryService(session).buy_equipment(player_id=player_id, code="OBD-SCANNER")
            await ProgressService(session).add_experience(player_id, 120)
            await ProgressService(session).change_reputation(player_id, 7)

        order = await self.make_order(player_id, car.id, reward=5_000)
        await self.move_order(player_id, order.id, OrderStatus.DIAGNOSTICS)
        async with self.factory() as session:
            service = OrderService(session)
            fault = await service.add_fault(
                player_id=player_id,
                order_id=order.id,
                code="BRK01",
                name="Износ колодок",
                system="brakes",
                severity=FaultSeverity.MODERATE,
            )
            await service.record_diagnostic(
                player_id=player_id,
                order_id=order.id,
                check_name="Осмотр тормозов",
                outcome=DiagnosticOutcome.FAULT_FOUND,
                findings="Колодки стёрты до металла",
                duration_minutes=15,
                fault_id=fault.id,
                equipment_code="OBD-SCANNER",
            )

        balance_before = await self.balance(player_id)
        await self.restart()

        async with self.factory() as session:
            profile = await PlayerService(session).get_profile(77)
            self.assertEqual(profile.money, balance_before)
            self.assertEqual(profile.level, 2)
            self.assertEqual(profile.experience, 120)
            self.assertEqual(profile.reputation, 57)

            cars = await GarageService(session).list_cars(player_id)
            self.assertEqual([c.vin for c in cars], [car.vin])
            self.assertEqual(cars[0].configuration.brand, "Lada")

            stock = await InventoryService(session).get_stock(player_id)
            self.assertEqual([(s.part.sku, s.quantity) for s in stock], [("BRK-PAD-F", 3)])
            equipment = await InventoryService(session).get_player_equipment(player_id)
            self.assertEqual([e.equipment.code for e in equipment], ["OBD-SCANNER"])

            full = await OrderService(session).get_order(player_id, order.id, with_details=True)
            self.assertEqual(full.status, OrderStatus.DIAGNOSTICS)
            self.assertEqual([f.code for f in full.faults], ["BRK01"])
            self.assertEqual(full.diagnostics[0].findings, "Колодки стёрты до металла")
            self.assertEqual(full.car.vin, car.vin)

            ledger = await FinanceService(session).get_history(player_id)
            self.assertEqual(
                sorted(t.category.value for t in ledger),
                ["equipment_purchase", "part_purchase"],
            )

    async def test_completed_order_and_reward_survive_restart_without_double_payment(self) -> None:
        player_id = await self.make_player(money=0)
        car = await self.make_car(player_id)
        order = await self.make_order(player_id, car.id, reward=4_000)
        await self.move_order(player_id, order.id, OrderStatus.READY)
        async with self.factory() as session:
            first = await OrderService(session).complete_order(
                player_id=player_id, order_id=order.id
            )
        self.assertEqual(first.reward_paid, 4_000)

        await self.restart()

        async with self.factory() as session:
            again = await OrderService(session).complete_order(
                player_id=player_id, order_id=order.id
            )
            history = await OrderService(session).get_repair_history(player_id)
        self.assertTrue(again.already_completed)
        self.assertEqual(again.reward_paid, 0)
        self.assertEqual(await self.balance(player_id), 4_000)
        self.assertEqual(len(history), 1)

    async def test_idempotency_key_survives_restart(self) -> None:
        player_id = await self.make_player(money=1_000)
        async with self.factory() as session:
            await FinanceService(session).apply(
                player_id=player_id,
                amount=-300,
                category=TransactionCategory.PENALTY,
                idempotency_key="fine-1",
            )
        await self.restart()
        async with self.factory() as session:
            result = await FinanceService(session).apply(
                player_id=player_id,
                amount=-300,
                category=TransactionCategory.PENALTY,
                idempotency_key="fine-1",
            )
        self.assertTrue(result.duplicate)
        self.assertEqual(await self.balance(player_id), 700)

    async def test_failed_operation_leaves_no_trace_after_restart(self) -> None:
        player_id = await self.make_player(money=100)
        async with self.factory() as session:
            with self.assertRaises(InsufficientFunds):
                await InventoryService(session).purchase_part(
                    player_id=player_id, sku="BAT-60AH", quantity=1
                )
        await self.restart()
        self.assertEqual(await self.balance(player_id), 100)
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM stock_items"), 0)
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM financial_transactions"), 0)
