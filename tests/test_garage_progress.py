"""Гараж (автомобили и конфигурации) и прогресс игрока."""

import asyncio
from dataclasses import asdict

from pydantic import ValidationError

from app.exceptions import CarAlreadyExists, CarNotFound, PlayerNotFound
from app.game_data.catalog import CAR_CONFIGURATIONS
from app.schemas import CarConfigurationData, CarData
from app.services import GarageService, PlayerService, ProgressService
from tests.base import DatabaseTestCase


def config(index: int = 0) -> CarConfigurationData:
    return CarConfigurationData(**asdict(CAR_CONFIGURATIONS[index]))


def car_data(vin: str = "XTA21099012345678") -> CarData:
    return CarData(vin=vin, plate="A123BC163", mileage_km=90_000, color="silver")


class GarageTests(DatabaseTestCase):
    async def test_register_and_read_car_with_configuration(self) -> None:
        pid = await self.make_player()
        async with self.factory() as session:
            created = await GarageService(session).register_car(
                player_id=pid, configuration=config(1), car=car_data("KNADM4123EA123456")
            )
            fetched = await GarageService(session).get_car(pid, created.id)
        self.assertEqual(fetched.configuration.brand, "Kia")
        self.assertEqual(fetched.configuration.engine_code, "G4FA")
        self.assertEqual(fetched.mileage_km, 90_000)

    async def test_cars_share_one_configuration_row(self) -> None:
        pid = await self.make_player()
        await self.make_car(pid, 0)
        await self.make_car(pid, 0)
        self.assertEqual(
            await self.scalar("SELECT COUNT(*) FROM car_configurations WHERE brand = 'Lada'"), 1
        )
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM cars"), 2)

    async def test_new_configuration_is_created_on_demand(self) -> None:
        pid = await self.make_player()
        before = await self.scalar("SELECT COUNT(*) FROM car_configurations")
        custom = config(0).model_copy(update={"engine_code": "CUSTOM", "power_hp": 99})
        async with self.factory() as session:
            await GarageService(session).register_car(
                player_id=pid, configuration=custom, car=car_data()
            )
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM car_configurations"), before + 1)

    async def test_duplicate_vin_rejected_without_orphan_rows(self) -> None:
        pid = await self.make_player()
        async with self.factory() as session:
            await GarageService(session).register_car(
                player_id=pid, configuration=config(), car=car_data()
            )
        async with self.factory() as session:
            with self.assertRaises(CarAlreadyExists):
                await GarageService(session).register_car(
                    player_id=pid, configuration=config(2), car=car_data()
                )
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM cars"), 1)

    async def test_concurrent_registration_of_same_vin(self) -> None:
        pid = await self.make_player()

        async def register() -> bool:
            async with self.factory() as session:
                try:
                    await GarageService(session).register_car(
                        player_id=pid, configuration=config(3), car=car_data("WVWZZZ6RZEY123456")
                    )
                    return True
                except CarAlreadyExists:
                    return False

        results = await asyncio.gather(*(register() for _ in range(6)))
        self.assertEqual(sum(results), 1)
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM cars"), 1)

    async def test_unknown_player_and_foreign_car(self) -> None:
        async with self.factory() as session:
            with self.assertRaises(PlayerNotFound):
                await GarageService(session).register_car(
                    player_id=9_999, configuration=config(), car=car_data()
                )
        owner = await self.make_player(telegram_id=1)
        stranger = await self.make_player(telegram_id=2)
        car = await self.make_car(owner)
        async with self.factory() as session:
            with self.assertRaises(CarNotFound):
                await GarageService(session).get_car(stranger, car.id)
            self.assertEqual(await GarageService(session).list_cars(stranger), [])

    def test_vin_validation(self) -> None:
        self.assertEqual(car_data("xta21099012345678").vin, "XTA21099012345678")
        for bad in ("SHORT", "XTA2109901234567I", "XTA2109901234567O", "XTA2109901234567Q",
                    "XTA210990123456789", ""):
            with self.assertRaises(ValidationError, msg=bad):
                car_data(bad)

    def test_car_data_bounds(self) -> None:
        with self.assertRaises(ValidationError):
            CarData(vin="XTA21099012345678", plate="A", mileage_km=-1, color="red")
        with self.assertRaises(ValidationError):
            CarData(vin="XTA21099012345678", plate="A", mileage_km=0, color="red", condition_pct=101)


class ProgressTests(DatabaseTestCase):
    async def _add_xp(self, pid: int, amount: int):
        async with self.factory() as session:
            return await ProgressService(session).add_experience(pid, amount)

    async def test_experience_and_level_up(self) -> None:
        pid = await self.make_player()
        first = await self._add_xp(pid, 99)
        self.assertEqual((first.experience, first.level, first.leveled_up), (99, 1, False))
        second = await self._add_xp(pid, 1)
        self.assertEqual((second.experience, second.level, second.leveled_up), (100, 2, True))
        third = await self._add_xp(pid, 400)  # 500 -> уровень 4, через уровень 3
        self.assertEqual((third.level, third.leveled_up), (4, True))

    async def test_level_never_decreases_and_caps_at_max(self) -> None:
        pid = await self.make_player()
        result = await self._add_xp(pid, 1_000_000)
        self.assertEqual(result.level, 10)
        again = await self._add_xp(pid, 1)
        self.assertEqual((again.level, again.leveled_up), (10, False))

    async def test_invalid_experience_and_unknown_player(self) -> None:
        pid = await self.make_player()
        for bad in (0, -5):
            with self.assertRaises(ValueError):
                await self._add_xp(pid, bad)
        with self.assertRaises(PlayerNotFound):
            await self._add_xp(9_999, 10)

    async def test_concurrent_experience_is_not_lost(self) -> None:
        pid = await self.make_player()
        await asyncio.gather(*(self._add_xp(pid, 10) for _ in range(20)))
        async with self.factory() as session:
            profile = await PlayerService(session).get_profile(1)
        self.assertEqual(profile.experience, 200)
        self.assertEqual(profile.level, 2)

    async def test_reputation_is_clamped(self) -> None:
        pid = await self.make_player()
        async with self.factory() as session:
            service = ProgressService(session)
            self.assertEqual(await service.change_reputation(pid, 7), 57)
            self.assertEqual(await service.change_reputation(pid, 500), 100)
            self.assertEqual(await service.change_reputation(pid, -30), 70)
            self.assertEqual(await service.change_reputation(pid, -500), 0)
            with self.assertRaises(PlayerNotFound):
                await service.change_reputation(9_999, 1)
