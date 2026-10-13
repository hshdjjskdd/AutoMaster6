"""Сервис гаража: регистрация и просмотр автомобилей."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import CarAlreadyExists, CarNotFound, PlayerNotFound
from app.models import Car
from app.repositories import CarRepository, PlayerRepository
from app.schemas import CarConfigurationData, CarData
from app.services.transaction import atomic


class GarageService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._cars = CarRepository(session)
        self._players = PlayerRepository(session)

    async def register_car(
        self, *, player_id: int, configuration: CarConfigurationData, car: CarData
    ) -> Car:
        """Регистрирует автомобиль игрока; конфигурация создаётся, если её ещё нет.

        Raises:
            PlayerNotFound: игрока нет.
            CarAlreadyExists: VIN уже зарегистрирован.
        """
        try:
            async with atomic(self._session):
                if await self._players.get_level(player_id) is None:
                    raise PlayerNotFound(player_id)
                config = await self._cars.get_or_create_configuration(configuration)
                created = await self._cars.create_car(
                    player_id=player_id, configuration_id=config.id, data=car
                )
        except IntegrityError as exc:
            raise CarAlreadyExists(car.vin) from exc
        return created

    async def get_car(self, player_id: int, car_id: int) -> Car:
        """Автомобиль игрока с конфигурацией. Raises: CarNotFound."""
        car = await self._cars.get(player_id, car_id, with_configuration=True)
        if car is None:
            raise CarNotFound(car_id)
        return car

    async def list_cars(self, player_id: int) -> list[Car]:
        """Все автомобили игрока (с конфигурациями)."""
        return await self._cars.list_for_player(player_id)
