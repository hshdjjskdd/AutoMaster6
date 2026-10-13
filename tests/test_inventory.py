"""Склад и оборудование: покупки, списание, ограничения."""

import asyncio

from app.exceptions import (
    EquipmentAlreadyOwned,
    EquipmentNotFound,
    IdempotencyConflict,
    InsufficientFunds,
    LevelTooLow,
    PartNotFound,
)
from app.services import InventoryService, ProgressService
from tests.base import DatabaseTestCase

PAD_PRICE = 2_200  # BRK-PAD-F
LIFT_PRICE = 85_000  # LIFT-2POST, нужен уровень 3


class PartPurchaseTests(DatabaseTestCase):
    async def _buy(self, player_id: int, sku: str = "BRK-PAD-F", qty: int = 1, key: str | None = None):
        async with self.factory() as session:
            return await InventoryService(session).purchase_part(
                player_id=player_id, sku=sku, quantity=qty, idempotency_key=key
            )

    async def _stock(self, player_id: int) -> dict[str, int]:
        async with self.factory() as session:
            return {s.part.sku: s.quantity for s in await InventoryService(session).get_stock(player_id)}

    async def test_purchase_charges_money_and_adds_stock_together(self) -> None:
        player_id = await self.make_player(money=10_000)
        result = await self._buy(player_id, qty=3)
        self.assertEqual(result.total_price, 3 * PAD_PRICE)
        self.assertEqual(await self.balance(player_id), 10_000 - 3 * PAD_PRICE)
        self.assertEqual(await self._stock(player_id), {"BRK-PAD-F": 3})

    async def test_repeated_purchases_accumulate_stock(self) -> None:
        player_id = await self.make_player(money=20_000)
        await self._buy(player_id, qty=2)
        await self._buy(player_id, qty=3)
        self.assertEqual(await self._stock(player_id), {"BRK-PAD-F": 5})
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM stock_items"), 1)

    async def test_insufficient_funds_changes_neither_money_nor_stock(self) -> None:
        player_id = await self.make_player(money=PAD_PRICE - 1)
        with self.assertRaises(InsufficientFunds):
            await self._buy(player_id)
        self.assertEqual(await self.balance(player_id), PAD_PRICE - 1)
        self.assertEqual(await self._stock(player_id), {})
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM financial_transactions"), 0)

    async def test_same_key_is_not_charged_twice(self) -> None:
        player_id = await self.make_player(money=10_000)
        first = await self._buy(player_id, qty=2, key="cb-1")
        second = await self._buy(player_id, qty=2, key="cb-1")
        self.assertFalse(first.duplicate)
        self.assertTrue(second.duplicate)
        self.assertEqual(await self.balance(player_id), 10_000 - 2 * PAD_PRICE)
        self.assertEqual(await self._stock(player_id), {"BRK-PAD-F": 2})

    async def test_same_key_with_different_goods_is_a_conflict(self) -> None:
        player_id = await self.make_player(money=10_000)
        await self._buy(player_id, qty=1, key="cb-2")
        with self.assertRaises(IdempotencyConflict):
            await self._buy(player_id, qty=2, key="cb-2")
        self.assertEqual(await self._stock(player_id), {"BRK-PAD-F": 1})

    async def test_unknown_part_and_bad_quantity(self) -> None:
        player_id = await self.make_player(money=10_000)
        with self.assertRaises(PartNotFound):
            await self._buy(player_id, sku="NOPE")
        with self.assertRaises(ValueError):
            await self._buy(player_id, qty=0)
        self.assertEqual(await self.balance(player_id), 10_000)

    async def test_concurrent_same_key_charges_once(self) -> None:
        """Двойное нажатие кнопки «Купить»: параллельные запросы с одним ключом."""
        player_id = await self.make_player(money=10_000)
        results = await asyncio.gather(
            *(self._buy(player_id, qty=2, key="double-tap") for _ in range(8))
        )
        self.assertEqual(sum(1 for r in results if not r.duplicate), 1)
        self.assertEqual({r.total_price for r in results}, {2 * PAD_PRICE})
        self.assertEqual(await self.balance(player_id), 10_000 - 2 * PAD_PRICE)
        self.assertEqual(await self._stock(player_id), {"BRK-PAD-F": 2})
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM financial_transactions"), 1)

    async def test_concurrent_purchases_respect_balance(self) -> None:
        player_id = await self.make_player(money=3 * PAD_PRICE)

        async def attempt(i: int) -> bool:
            try:
                await self._buy(player_id, key=f"c{i}")
                return True
            except InsufficientFunds:
                return False

        results = await asyncio.gather(*(attempt(i) for i in range(8)))
        self.assertEqual(sum(results), 3)
        self.assertEqual(await self._stock(player_id), {"BRK-PAD-F": 3})
        self.assertEqual(await self.balance(player_id), 0)


class EquipmentTests(DatabaseTestCase):
    async def _buy(self, player_id: int, code: str, key: str | None = None):
        async with self.factory() as session:
            return await InventoryService(session).buy_equipment(
                player_id=player_id, code=code, idempotency_key=key
            )

    async def _owned(self, player_id: int) -> list[str]:
        async with self.factory() as session:
            items = await InventoryService(session).get_player_equipment(player_id)
        return [i.equipment.code for i in items]

    async def test_buy_equipment(self) -> None:
        player_id = await self.make_player(money=5_000)
        result = await self._buy(player_id, "OBD-SCANNER")
        self.assertEqual(result.balance_after, 5_000 - 3_500)
        self.assertEqual(await self._owned(player_id), ["OBD-SCANNER"])

    async def test_cannot_buy_twice_and_is_not_charged_again(self) -> None:
        player_id = await self.make_player(money=10_000)
        await self._buy(player_id, "OBD-SCANNER")
        with self.assertRaises(EquipmentAlreadyOwned):
            await self._buy(player_id, "OBD-SCANNER")
        self.assertEqual(await self.balance(player_id), 10_000 - 3_500)

    async def test_repeated_request_with_same_key_is_a_harmless_duplicate(self) -> None:
        player_id = await self.make_player(money=10_000)
        await self._buy(player_id, "OBD-SCANNER", key="tap-1")
        again = await self._buy(player_id, "OBD-SCANNER", key="tap-1")
        self.assertTrue(again.duplicate)
        self.assertEqual(await self.balance(player_id), 10_000 - 3_500)

    async def test_level_requirement(self) -> None:
        player_id = await self.make_player(money=LIFT_PRICE * 2)
        with self.assertRaises(LevelTooLow) as ctx:
            await self._buy(player_id, "LIFT-2POST")
        self.assertEqual((ctx.exception.required, ctx.exception.actual), (3, 1))
        self.assertEqual(await self.balance(player_id), LIFT_PRICE * 2)

        async with self.factory() as session:
            await ProgressService(session).add_experience(player_id, 250)  # уровень 3
        await self._buy(player_id, "LIFT-2POST")
        self.assertEqual(await self._owned(player_id), ["LIFT-2POST"])

    async def test_insufficient_funds_does_not_grant_item(self) -> None:
        player_id = await self.make_player(money=1_000)
        with self.assertRaises(InsufficientFunds):
            await self._buy(player_id, "OBD-SCANNER")
        self.assertEqual(await self._owned(player_id), [])
        self.assertEqual(await self.balance(player_id), 1_000)

    async def test_free_starter_equipment(self) -> None:
        player_id = await self.make_player(money=0)
        result = await self._buy(player_id, "TOOLSET-BASIC")
        self.assertEqual(result.balance_after, 0)
        self.assertEqual(await self._owned(player_id), ["TOOLSET-BASIC"])
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM financial_transactions"), 0)

    async def test_unknown_equipment(self) -> None:
        player_id = await self.make_player()
        with self.assertRaises(EquipmentNotFound):
            await self._buy(player_id, "NOPE")

    async def test_concurrent_purchase_of_same_item_charges_once(self) -> None:
        player_id = await self.make_player(money=20_000)

        async def attempt(i: int) -> bool:
            try:
                await self._buy(player_id, "OBD-SCANNER", key=f"race-{i}")
                return True
            except EquipmentAlreadyOwned:
                return False

        results = await asyncio.gather(*(attempt(i) for i in range(6)))
        self.assertEqual(sum(results), 1)
        self.assertEqual(await self._owned(player_id), ["OBD-SCANNER"])
        self.assertEqual(await self.balance(player_id), 20_000 - 3_500)
