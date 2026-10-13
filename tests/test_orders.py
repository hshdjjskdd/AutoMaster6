"""Заказы: статусы, неисправности, диагностика, детали, сдача и защита награды."""

import asyncio

from app.exceptions import (
    CarBusy,
    CarNotFound,
    EquipmentNotFound,
    FaultAlreadyRecorded,
    FaultAlreadyResolved,
    FaultNotFound,
    InsufficientStock,
    InvalidOrderState,
    InvalidStatusTransition,
    OrderNotFound,
    OrderNotReady,
    PartNotFound,
)
from app.game_data.enums import DiagnosticOutcome, FaultSeverity, OrderStatus
from app.services import InventoryService, OrderService
from tests.base import DatabaseTestCase


class OrderTestCase(DatabaseTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.pid = await self.make_player(money=50_000)
        self.car = await self.make_car(self.pid)

    async def call(self, method: str, **kwargs):
        """Вызывает метод OrderService в отдельной сессии (как отдельный апдейт Telegram)."""
        async with self.factory() as session:
            return await getattr(OrderService(session), method)(player_id=self.pid, **kwargs)

    async def status(self, order_id: int) -> OrderStatus:
        order = await self.call("get_order", order_id=order_id)
        return order.status

    async def add_fault(self, order_id: int, code: str = "BRK01"):
        return await self.call(
            "add_fault", order_id=order_id, code=code, name="Износ колодок",
            system="brakes", severity=FaultSeverity.MODERATE,
        )

    async def buy_part(self, sku: str, qty: int) -> None:
        async with self.factory() as session:
            await InventoryService(session).purchase_part(
                player_id=self.pid, sku=sku, quantity=qty
            )


class CreationAndStatusTests(OrderTestCase):
    async def test_create_order(self) -> None:
        order = await self.make_order(self.pid, self.car.id, reward=2_500)
        self.assertEqual(order.status, OrderStatus.NEW)
        self.assertEqual(order.reward, 2_500)
        self.assertIsNone(order.completed_at)

    async def test_one_active_order_per_car(self) -> None:
        await self.make_order(self.pid, self.car.id)
        with self.assertRaises(CarBusy):
            await self.make_order(self.pid, self.car.id)

    async def test_new_order_allowed_after_previous_is_closed(self) -> None:
        first = await self.make_order(self.pid, self.car.id)
        await self.call("cancel_order", order_id=first.id)
        second = await self.make_order(self.pid, self.car.id)
        self.assertNotEqual(first.id, second.id)

    async def test_foreign_or_missing_car(self) -> None:
        other = await self.make_player(telegram_id=2)
        foreign_car = await self.make_car(other)
        with self.assertRaises(CarNotFound):
            await self.make_order(self.pid, foreign_car.id)
        with self.assertRaises(CarNotFound):
            await self.make_order(self.pid, 9_999)

    async def test_valid_transition_chain(self) -> None:
        order = await self.make_order(self.pid, self.car.id)
        for target in (OrderStatus.DIAGNOSTICS, OrderStatus.AWAITING_PARTS,
                       OrderStatus.IN_REPAIR, OrderStatus.READY, OrderStatus.IN_REPAIR):
            updated = await self.call("change_status", order_id=order.id, new_status=target)
            self.assertEqual(updated.status, target)

    async def test_invalid_transitions_are_rejected(self) -> None:
        order = await self.make_order(self.pid, self.car.id)
        for bad in (OrderStatus.READY, OrderStatus.IN_REPAIR, OrderStatus.NEW):
            with self.assertRaises(InvalidStatusTransition):
                await self.call("change_status", order_id=order.id, new_status=bad)
        self.assertEqual(await self.status(order.id), OrderStatus.NEW)

    async def test_completed_cannot_be_set_by_plain_status_change(self) -> None:
        order = await self.make_order(self.pid, self.car.id, status=OrderStatus.READY)
        with self.assertRaises(InvalidStatusTransition):
            await self.call("change_status", order_id=order.id, new_status=OrderStatus.COMPLETED)
        self.assertEqual(await self.status(order.id), OrderStatus.READY)

    async def test_terminal_statuses_are_final(self) -> None:
        order = await self.make_order(self.pid, self.car.id)
        await self.call("cancel_order", order_id=order.id)
        with self.assertRaises(InvalidStatusTransition):
            await self.call("change_status", order_id=order.id, new_status=OrderStatus.DIAGNOSTICS)

    async def test_orders_of_other_players_are_invisible(self) -> None:
        order = await self.make_order(self.pid, self.car.id)
        other = await self.make_player(telegram_id=2)
        async with self.factory() as session:
            with self.assertRaises(OrderNotFound):
                await OrderService(session).change_status(
                    player_id=other, order_id=order.id, new_status=OrderStatus.DIAGNOSTICS
                )
            with self.assertRaises(OrderNotFound):
                await OrderService(session).get_order(other, order.id)
            self.assertEqual(await OrderService(session).list_orders(other), [])
        self.assertEqual(await self.status(order.id), OrderStatus.NEW)

    async def test_concurrent_status_change_has_single_winner(self) -> None:
        order = await self.make_order(self.pid, self.car.id, status=OrderStatus.IN_REPAIR)

        async def move(target: OrderStatus) -> bool:
            try:
                await self.call("change_status", order_id=order.id, new_status=target)
                return True
            except Exception:  # noqa: BLE001 — проигравший получает любую доменную ошибку
                return False

        # READY и AWAITING_PARTS допустимы из IN_REPAIR, но после первого перехода
        # второй из нового статуса уже недопустим.
        results = await asyncio.gather(
            move(OrderStatus.READY), move(OrderStatus.AWAITING_PARTS)
        )
        self.assertEqual(sum(results), 1)
        self.assertIn(await self.status(order.id), (OrderStatus.READY, OrderStatus.AWAITING_PARTS))

    async def test_list_orders_filters_by_status(self) -> None:
        a = await self.make_order(self.pid, self.car.id)
        car2 = await self.make_car(self.pid, 1)
        b = await self.make_order(self.pid, car2.id, status=OrderStatus.DIAGNOSTICS)
        new_only = await self.call("list_orders", statuses=[OrderStatus.NEW])
        self.assertEqual([o.id for o in new_only], [a.id])
        everything = await self.call("list_orders")
        self.assertEqual([o.id for o in everything], [b.id, a.id])


class FaultsAndDiagnosticsTests(OrderTestCase):
    async def test_add_fault_and_diagnostic_result(self) -> None:
        order = await self.make_order(self.pid, self.car.id, status=OrderStatus.DIAGNOSTICS)
        fault = await self.add_fault(order.id)
        diag = await self.call(
            "record_diagnostic", order_id=order.id, check_name="Осмотр тормозов",
            outcome=DiagnosticOutcome.FAULT_FOUND, findings="Колодки стёрты",
            duration_minutes=20, fault_id=fault.id,
        )
        self.assertEqual(diag.fault_id, fault.id)
        full = await self.call("get_order", order_id=order.id, with_details=True)
        self.assertEqual([f.code for f in full.faults], ["BRK01"])
        self.assertEqual([d.check_name for d in full.diagnostics], ["Осмотр тормозов"])

    async def test_faults_require_suitable_status(self) -> None:
        order = await self.make_order(self.pid, self.car.id)  # NEW
        with self.assertRaises(InvalidOrderState):
            await self.add_fault(order.id)
        with self.assertRaises(OrderNotFound):
            await self.add_fault(9_999)

    async def test_duplicate_fault_code_in_same_order(self) -> None:
        order = await self.make_order(self.pid, self.car.id, status=OrderStatus.DIAGNOSTICS)
        await self.add_fault(order.id, "ENG01")
        with self.assertRaises(FaultAlreadyRecorded):
            await self.add_fault(order.id, "ENG01")

    async def test_diagnostic_validates_references(self) -> None:
        order = await self.make_order(self.pid, self.car.id, status=OrderStatus.DIAGNOSTICS)
        with self.assertRaises(FaultNotFound):
            await self.call("record_diagnostic", order_id=order.id, check_name="x",
                            outcome=DiagnosticOutcome.NO_FAULT, fault_id=12_345)
        with self.assertRaises(EquipmentNotFound):
            await self.call("record_diagnostic", order_id=order.id, check_name="x",
                            outcome=DiagnosticOutcome.NO_FAULT, equipment_code="NOPE")
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM diagnostic_results"), 0)

    async def test_resolve_fault_once(self) -> None:
        order = await self.make_order(self.pid, self.car.id, status=OrderStatus.DIAGNOSTICS)
        fault = await self.add_fault(order.id)
        await self.call("change_status", order_id=order.id, new_status=OrderStatus.IN_REPAIR)
        await self.call("resolve_fault", order_id=order.id, fault_id=fault.id)
        with self.assertRaises(FaultAlreadyResolved):
            await self.call("resolve_fault", order_id=order.id, fault_id=fault.id)
        with self.assertRaises(FaultNotFound):
            await self.call("resolve_fault", order_id=order.id, fault_id=999)
        self.assertIsNotNone(
            await self.scalar("SELECT resolved_at FROM faults WHERE id = :i", i=fault.id)
        )


class PartsTests(OrderTestCase):
    async def test_install_part_takes_stock_and_records_price(self) -> None:
        await self.buy_part("BRK-PAD-F", 3)
        order = await self.make_order(self.pid, self.car.id, status=OrderStatus.IN_REPAIR)
        await self.call("install_part", order_id=order.id, sku="BRK-PAD-F", quantity=2)
        full = await self.call("get_order", order_id=order.id, with_details=True)
        self.assertEqual([(p.part.sku, p.quantity, p.unit_price) for p in full.parts],
                         [("BRK-PAD-F", 2, 2_200)])
        async with self.factory() as session:
            stock = await InventoryService(session).get_stock(self.pid)
        self.assertEqual([(s.part.sku, s.quantity) for s in stock], [("BRK-PAD-F", 1)])

    async def test_repeated_install_sums_quantity_in_one_row(self) -> None:
        await self.buy_part("FLT-OIL", 4)
        order = await self.make_order(self.pid, self.car.id, status=OrderStatus.IN_REPAIR)
        await self.call("install_part", order_id=order.id, sku="FLT-OIL", quantity=1)
        await self.call("install_part", order_id=order.id, sku="FLT-OIL", quantity=2)
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM order_parts"), 1)
        self.assertEqual(await self.scalar("SELECT quantity FROM order_parts"), 3)

    async def test_not_enough_stock_changes_nothing(self) -> None:
        await self.buy_part("BRK-PAD-F", 1)
        order = await self.make_order(self.pid, self.car.id, status=OrderStatus.IN_REPAIR)
        with self.assertRaises(InsufficientStock):
            await self.call("install_part", order_id=order.id, sku="BRK-PAD-F", quantity=2)
        self.assertEqual(await self.scalar("SELECT quantity FROM stock_items"), 1)
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM order_parts"), 0)

    async def test_part_not_in_stock_or_unknown(self) -> None:
        order = await self.make_order(self.pid, self.car.id, status=OrderStatus.IN_REPAIR)
        with self.assertRaises(InsufficientStock):
            await self.call("install_part", order_id=order.id, sku="BRK-PAD-F", quantity=1)
        with self.assertRaises(PartNotFound):
            await self.call("install_part", order_id=order.id, sku="NOPE", quantity=1)

    async def test_install_requires_suitable_status(self) -> None:
        await self.buy_part("BRK-PAD-F", 1)
        order = await self.make_order(self.pid, self.car.id, status=OrderStatus.DIAGNOSTICS)
        with self.assertRaises(InvalidOrderState):
            await self.call("install_part", order_id=order.id, sku="BRK-PAD-F", quantity=1)
        self.assertEqual(await self.scalar("SELECT quantity FROM stock_items"), 1)

    async def test_concurrent_installs_cannot_overspend_stock(self) -> None:
        await self.buy_part("SPK-PLUG", 4)
        order = await self.make_order(self.pid, self.car.id, status=OrderStatus.IN_REPAIR)

        async def install() -> bool:
            try:
                await self.call("install_part", order_id=order.id, sku="SPK-PLUG", quantity=1)
                return True
            except InsufficientStock:
                return False

        results = await asyncio.gather(*(install() for _ in range(10)))
        self.assertEqual(sum(results), 4)
        self.assertEqual(await self.scalar("SELECT quantity FROM stock_items"), 0)
        self.assertEqual(await self.scalar("SELECT quantity FROM order_parts"), 4)


class CompletionTests(OrderTestCase):
    async def _ready_order(self, reward: int = 3_000):
        order = await self.make_order(self.pid, self.car.id, reward=reward,
                                      status=OrderStatus.IN_REPAIR)
        await self.call("change_status", order_id=order.id, new_status=OrderStatus.READY)
        return order

    async def test_completion_pays_reward_and_writes_history(self) -> None:
        await self.buy_part("BRK-PAD-F", 1)
        order = await self.make_order(self.pid, self.car.id, reward=5_000,
                                      status=OrderStatus.IN_REPAIR)
        await self.call("install_part", order_id=order.id, sku="BRK-PAD-F", quantity=1)
        await self.call("change_status", order_id=order.id, new_status=OrderStatus.READY)
        before = await self.balance(self.pid)

        result = await self.call("complete_order", order_id=order.id)

        self.assertEqual((result.reward_paid, result.parts_cost, result.profit),
                         (5_000, 2_200, 2_800))
        self.assertFalse(result.already_completed)
        self.assertEqual(await self.balance(self.pid), before + 5_000)
        done = await self.call("get_order", order_id=order.id)
        self.assertEqual(done.status, OrderStatus.COMPLETED)
        self.assertIsNotNone(done.completed_at)
        self.assertIsNotNone(done.reward_paid_at)
        history = await self.call("get_repair_history")
        self.assertEqual([(h.order_id, h.revenue, h.parts_cost, h.profit) for h in history],
                         [(order.id, 5_000, 2_200, 2_800)])
        self.assertEqual(
            await self.scalar("SELECT amount FROM financial_transactions "
                              "WHERE category = 'order_reward'"), 5_000)

    async def test_second_completion_never_pays_again(self) -> None:
        order = await self._ready_order(reward=4_000)
        before = await self.balance(self.pid)
        first = await self.call("complete_order", order_id=order.id)
        second = await self.call("complete_order", order_id=order.id)
        third = await self.call("complete_order", order_id=order.id)
        self.assertEqual(first.reward_paid, 4_000)
        for repeat in (second, third):
            self.assertTrue(repeat.already_completed)
            self.assertEqual(repeat.reward_paid, 0)
        self.assertEqual(await self.balance(self.pid), before + 4_000)
        self.assertEqual(
            await self.scalar("SELECT COUNT(*) FROM financial_transactions "
                              "WHERE category = 'order_reward'"), 1)
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM repair_history"), 1)

    async def test_concurrent_completion_pays_exactly_once(self) -> None:
        order = await self._ready_order(reward=7_000)
        before = await self.balance(self.pid)

        results = await asyncio.gather(
            *(self.call("complete_order", order_id=order.id) for _ in range(12))
        )

        self.assertEqual(sum(1 for r in results if not r.already_completed), 1)
        self.assertEqual(sum(r.reward_paid for r in results), 7_000)
        self.assertEqual(await self.balance(self.pid), before + 7_000)
        self.assertEqual(
            await self.scalar("SELECT COUNT(*) FROM financial_transactions "
                              "WHERE category = 'order_reward'"), 1)
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM repair_history"), 1)

    async def test_database_refuses_second_reward_entry_for_same_order(self) -> None:
        """Даже обойдя сервис, вторую награду по заказу записать нельзя."""
        from sqlalchemy import text
        from sqlalchemy.exc import IntegrityError

        order = await self._ready_order(reward=1_000)
        await self.call("complete_order", order_id=order.id)
        async with self.factory() as session:
            with self.assertRaises(IntegrityError):
                await session.execute(text(
                    "INSERT INTO financial_transactions (player_id, order_id, type, category, "
                    "amount, balance_after, idempotency_key, created_at) VALUES "
                    "(:p, :o, 'income', 'order_reward', 1000, 0, :k, '2026-01-01 00:00:00')"),
                    {"p": self.pid, "o": order.id, "k": f"order_reward:{order.id}"})
        async with self.factory() as session:
            with self.assertRaises(IntegrityError):
                await session.execute(text(
                    "INSERT INTO repair_history (player_id, order_id, car_id, summary, revenue, "
                    "parts_cost, profit, completed_at) VALUES (:p, :o, :c, 's', 1, 0, 1, "
                    "'2026-01-01 00:00:00')"), {"p": self.pid, "o": order.id, "c": self.car.id})

    async def test_not_ready_order_cannot_be_completed(self) -> None:
        order = await self.make_order(self.pid, self.car.id, status=OrderStatus.IN_REPAIR)
        before = await self.balance(self.pid)
        with self.assertRaises(InvalidStatusTransition):
            await self.call("complete_order", order_id=order.id)
        self.assertEqual(await self.balance(self.pid), before)
        self.assertEqual(await self.status(order.id), OrderStatus.IN_REPAIR)

    async def test_unresolved_faults_block_completion(self) -> None:
        order = await self.make_order(self.pid, self.car.id, status=OrderStatus.DIAGNOSTICS)
        fault = await self.add_fault(order.id)
        await self.call("change_status", order_id=order.id, new_status=OrderStatus.IN_REPAIR)
        await self.call("change_status", order_id=order.id, new_status=OrderStatus.READY)
        with self.assertRaises(OrderNotReady) as ctx:
            await self.call("complete_order", order_id=order.id)
        self.assertEqual(ctx.exception.unresolved, 1)
        self.assertEqual(await self.status(order.id), OrderStatus.READY)

        await self.call("change_status", order_id=order.id, new_status=OrderStatus.IN_REPAIR)
        await self.call("resolve_fault", order_id=order.id, fault_id=fault.id)
        await self.call("change_status", order_id=order.id, new_status=OrderStatus.READY)
        result = await self.call("complete_order", order_id=order.id)
        self.assertFalse(result.already_completed)

    async def test_cancelled_order_never_pays(self) -> None:
        order = await self.make_order(self.pid, self.car.id, reward=9_000)
        await self.call("cancel_order", order_id=order.id)
        before = await self.balance(self.pid)
        with self.assertRaises(InvalidStatusTransition):
            await self.call("complete_order", order_id=order.id)
        self.assertEqual(await self.balance(self.pid), before)

    async def test_zero_reward_order_completes_without_ledger_entry(self) -> None:
        order = await self._ready_order(reward=0)
        result = await self.call("complete_order", order_id=order.id)
        self.assertEqual(result.reward_paid, 0)
        self.assertFalse(result.already_completed)
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM financial_transactions"), 0)
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM repair_history"), 1)

    async def test_other_player_cannot_complete_order(self) -> None:
        order = await self._ready_order()
        other = await self.make_player(telegram_id=2, money=0)
        async with self.factory() as session:
            with self.assertRaises(OrderNotFound):
                await OrderService(session).complete_order(player_id=other, order_id=order.id)
        self.assertEqual(await self.balance(other), 0)
        self.assertEqual(await self.status(order.id), OrderStatus.READY)
