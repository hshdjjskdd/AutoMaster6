"""Целостность схемы: связи, ограничения, инициализация и версии."""

import tempfile
import unittest
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.config import Settings
from app.database import (
    SCHEMA_VERSION,
    DatabaseVersionError,
    create_engine,
    create_session_factory,
    init_db,
)
from app.models import Base, Player
from app.schemas import TelegramUserData
from app.services import PlayerService
from tests.base import FAKE_TOKEN, DatabaseTestCase


class SchemaTests(DatabaseTestCase):
    async def _insert_fails(self, sql: str, **params: object) -> None:
        async with self.factory() as session:
            with self.assertRaises(IntegrityError):
                await session.execute(text(sql), params)
                await session.commit()

    async def test_all_tables_created(self) -> None:
        names = set(Base.metadata.tables)
        self.assertGreaterEqual(
            names,
            {
                "players", "cars", "car_configurations", "orders", "order_parts", "faults",
                "diagnostic_results", "parts", "stock_items", "equipment", "player_equipment",
                "repair_history", "financial_transactions", "client_offers",
                "diagnostic_sessions", "hidden_faults", "diagnostic_check_runs",
            },
        )
        for name in names:
            exists = await self.scalar(
                "SELECT name FROM sqlite_master WHERE type='table' AND name = :n", n=name
            )
            self.assertEqual(exists, name)

    async def test_foreign_keys_are_enforced(self) -> None:
        await self._insert_fails(
            "INSERT INTO stock_items (player_id, part_id, quantity, updated_at) "
            "VALUES (9999, 1, 1, '2026-01-01 00:00:00')"
        )

    async def test_negative_stock_rejected_by_database(self) -> None:
        player_id = await self.make_player()
        await self._insert_fails(
            "INSERT INTO stock_items (player_id, part_id, quantity, updated_at) "
            "VALUES (:p, 1, -1, '2026-01-01 00:00:00')",
            p=player_id,
        )

    async def test_negative_money_rejected_by_database(self) -> None:
        player_id = await self.make_player()
        await self._insert_fails(
            "UPDATE players SET money = -1 WHERE id = :p", p=player_id
        )

    async def test_vin_is_unique(self) -> None:
        player_id = await self.make_player()
        car = await self.make_car(player_id)
        await self._insert_fails(
            "INSERT INTO cars (player_id, configuration_id, vin, plate, mileage_km, color, "
            "condition_pct, created_at) VALUES (:p, :c, (SELECT vin FROM cars WHERE id = :i), "
            "'X', 0, 'red', 100, '2026-01-01 00:00:00')",
            p=player_id, c=car.configuration_id, i=car.id,
        )

    async def test_completed_order_requires_timestamp(self) -> None:
        player_id = await self.make_player()
        car = await self.make_car(player_id)
        await self._insert_fails(
            "INSERT INTO orders (player_id, car_id, status, customer_name, complaint, reward, "
            "created_at, updated_at) VALUES (:p, :c, 'completed', 'x', 'y', 0, "
            "'2026-01-01 00:00:00', '2026-01-01 00:00:00')",
            p=player_id, c=car.id,
        )

    async def test_reward_paid_only_for_completed_order(self) -> None:
        player_id = await self.make_player()
        car = await self.make_car(player_id)
        await self._insert_fails(
            "INSERT INTO orders (player_id, car_id, status, customer_name, complaint, reward, "
            "reward_paid_at, created_at, updated_at) VALUES (:p, :c, 'new', 'x', 'y', 0, "
            "'2026-01-01 00:00:00', '2026-01-01 00:00:00', '2026-01-01 00:00:00')",
            p=player_id, c=car.id,
        )

    async def test_unknown_status_rejected(self) -> None:
        player_id = await self.make_player()
        car = await self.make_car(player_id)
        await self._insert_fails(
            "INSERT INTO orders (player_id, car_id, status, customer_name, complaint, reward, "
            "created_at, updated_at) VALUES (:p, :c, 'bogus', 'x', 'y', 0, "
            "'2026-01-01 00:00:00', '2026-01-01 00:00:00')",
            p=player_id, c=car.id,
        )

    async def test_ledger_amount_must_match_type(self) -> None:
        player_id = await self.make_player()
        await self._insert_fails(
            "INSERT INTO financial_transactions (player_id, type, category, amount, "
            "balance_after, idempotency_key, created_at) VALUES (:p, 'income', "
            "'order_reward', -5, 0, 'k', '2026-01-01 00:00:00')",
            p=player_id,
        )

    async def test_deleting_player_cascades(self) -> None:
        player_id = await self.make_player()
        car = await self.make_car(player_id)
        await self.make_order(player_id, car.id)
        async with self.factory() as session:
            await session.execute(text("DELETE FROM players WHERE id = :p"), {"p": player_id})
            await session.commit()
        for table in ("cars", "orders"):
            count = await self.scalar(f"SELECT COUNT(*) FROM {table}")
            self.assertEqual(count, 0, table)

    async def test_car_with_orders_cannot_be_deleted(self) -> None:
        player_id = await self.make_player()
        car = await self.make_car(player_id)
        await self.make_order(player_id, car.id)
        await self._insert_fails("DELETE FROM cars WHERE id = :c", c=car.id)
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM cars"), 1)

    async def test_catalog_with_restrict_blocks_part_deletion(self) -> None:
        player_id = await self.make_player()
        async with self.factory() as session:
            await session.execute(
                text(
                    "INSERT INTO stock_items (player_id, part_id, quantity, updated_at) "
                    "VALUES (:p, 1, 1, '2026-01-01 00:00:00')"
                ),
                {"p": player_id},
            )
            await session.commit()
        await self._insert_fails("DELETE FROM parts WHERE id = 1")


class InitDbTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        path = Path(self._tmp.name) / "init.db"
        self.settings = Settings(
            bot_token=FAKE_TOKEN, database_url=f"sqlite+aiosqlite:///{path.as_posix()}"
        )

    async def asyncTearDown(self) -> None:
        self._tmp.cleanup()

    async def test_init_is_idempotent_and_seeds_catalog_once(self) -> None:
        engine = create_engine(self.settings)
        try:
            await init_db(engine)
            await init_db(engine)
            async with engine.connect() as conn:
                parts = (await conn.execute(text("SELECT COUNT(*) FROM parts"))).scalar_one()
                equipment = (await conn.execute(text("SELECT COUNT(*) FROM equipment"))).scalar_one()
                configs = (
                    await conn.execute(text("SELECT COUNT(*) FROM car_configurations"))
                ).scalar_one()
                version = (await conn.execute(text("PRAGMA user_version"))).scalar_one()
            self.assertGreater(parts, 0)
            self.assertGreater(equipment, 0)
            self.assertGreater(configs, 0)
            self.assertEqual(version, SCHEMA_VERSION)
        finally:
            await engine.dispose()

    async def test_seed_does_not_overwrite_manual_changes(self) -> None:
        engine = create_engine(self.settings)
        try:
            await init_db(engine)
            async with engine.begin() as conn:
                await conn.execute(text("UPDATE parts SET base_price = 1 WHERE sku = 'FLT-OIL'"))
            await init_db(engine)
            async with engine.connect() as conn:
                price = (
                    await conn.execute(text("SELECT base_price FROM parts WHERE sku = 'FLT-OIL'"))
                ).scalar_one()
            self.assertEqual(price, 1)
        finally:
            await engine.dispose()

    async def test_database_from_stage_1_is_upgraded_without_data_loss(self) -> None:
        engine = create_engine(self.settings)
        try:
            # База этапа 1: только таблица players и данные игрока.
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all, tables=[Player.__table__])
            factory = create_session_factory(engine)
            async with factory() as session:
                await PlayerService(session).register_or_update(
                    TelegramUserData(telegram_id=5, first_name="Старый")
                )
            await init_db(engine)
            async with factory() as session:
                profile = await PlayerService(session).get_profile(5)
            self.assertIsNotNone(profile)
            self.assertEqual(profile.money, 15_000)
            async with engine.connect() as conn:
                tables = (
                    await conn.execute(
                        text("SELECT COUNT(*) FROM sqlite_master WHERE name = 'orders'")
                    )
                ).scalar_one()
            self.assertEqual(tables, 1)
        finally:
            await engine.dispose()

    async def test_database_from_newer_version_is_rejected(self) -> None:
        engine = create_engine(self.settings)
        try:
            async with engine.begin() as conn:
                await conn.execute(text(f"PRAGMA user_version = {SCHEMA_VERSION + 1}"))
            with self.assertRaises(DatabaseVersionError):
                await init_db(engine)
        finally:
            await engine.dispose()


if __name__ == "__main__":
    unittest.main()
