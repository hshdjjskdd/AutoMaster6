"""Общая основа тестов: временная файловая SQLite и фабрики тестовых данных."""

import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from sqlalchemy import text

from app.config import Settings
from app.database import create_engine, create_session_factory, init_db
from app.game_data.catalog import CAR_CONFIGURATIONS
from app.game_data.enums import OrderStatus
from app.models import Car, Order
from app.schemas import CarConfigurationData, CarData, TelegramUserData
from app.services import GarageService, OrderService, PlayerService

FAKE_TOKEN = "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"


class DatabaseTestCase(unittest.IsolatedAsyncioTestCase):
    """Каждому тесту — своя чистая БД в файле (нужен для проверки перезапуска и гонок)."""

    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "test.db"
        self.settings = Settings(
            bot_token=FAKE_TOKEN,
            database_url=f"sqlite+aiosqlite:///{self.db_path.as_posix()}",
        )
        self._vin_counter = 0
        await self._open()

    async def _open(self) -> None:
        self.engine = create_engine(self.settings)
        self.factory = create_session_factory(self.engine)
        await init_db(self.engine)

    async def restart(self) -> None:
        """Имитирует перезапуск бота: закрывает соединения и открывает БД заново."""
        await self.engine.dispose()
        await self._open()

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()
        self._tmp.cleanup()

    # --- фабрики -----------------------------------------------------------

    async def make_player(self, telegram_id: int = 1, money: int | None = None) -> int:
        async with self.factory() as session:
            service = PlayerService(session)
            await service.register_or_update(
                TelegramUserData(telegram_id=telegram_id, first_name=f"Игрок{telegram_id}")
            )
            player_id = await service.get_player_id(telegram_id)
        assert player_id is not None
        if money is not None:
            await self.set_money(player_id, money)
        return player_id

    async def set_money(self, player_id: int, money: int) -> None:
        async with self.factory() as session:
            await session.execute(
                text("UPDATE players SET money = :m WHERE id = :i"), {"m": money, "i": player_id}
            )
            await session.commit()

    async def scalar(self, sql: str, **params: object) -> object:
        """Выполняет произвольный SELECT и возвращает первое значение."""
        async with self.factory() as session:
            return await session.scalar(text(sql), params)

    async def balance(self, player_id: int) -> int:
        return int(await self.scalar("SELECT money FROM players WHERE id = :i", i=player_id))  # type: ignore[arg-type]

    async def make_car(self, player_id: int, config_index: int = 0) -> Car:
        self._vin_counter += 1
        async with self.factory() as session:
            return await GarageService(session).register_car(
                player_id=player_id,
                configuration=CarConfigurationData(**asdict(CAR_CONFIGURATIONS[config_index])),
                car=CarData(
                    vin=f"XTA2109901{self._vin_counter:07d}",
                    plate=f"A{self._vin_counter:03d}BC163",
                    mileage_km=100_000,
                    color="white",
                ),
            )

    async def make_order(
        self, player_id: int, car_id: int, reward: int = 3_000, status: OrderStatus | None = None
    ) -> Order:
        async with self.factory() as session:
            order = await OrderService(session).create_order(
                player_id=player_id,
                car_id=car_id,
                customer_name="Клиент",
                complaint="Стук в подвеске",
                reward=reward,
            )
        if status is not None:
            await self.move_order(player_id, order.id, status)
        return order

    async def move_order(self, player_id: int, order_id: int, target: OrderStatus) -> None:
        """Проводит заказ по допустимой цепочке статусов до target."""
        chain = {
            OrderStatus.DIAGNOSTICS: [OrderStatus.DIAGNOSTICS],
            OrderStatus.IN_REPAIR: [OrderStatus.DIAGNOSTICS, OrderStatus.IN_REPAIR],
            OrderStatus.AWAITING_PARTS: [OrderStatus.DIAGNOSTICS, OrderStatus.AWAITING_PARTS],
            OrderStatus.READY: [
                OrderStatus.DIAGNOSTICS,
                OrderStatus.IN_REPAIR,
                OrderStatus.READY,
            ],
        }[target]
        for step in chain:
            async with self.factory() as session:
                await OrderService(session).change_status(
                    player_id=player_id, order_id=order_id, new_status=step
                )
