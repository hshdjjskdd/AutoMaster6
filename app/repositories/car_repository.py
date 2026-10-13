"""Репозиторий автомобилей и их конфигураций."""

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Car, CarConfiguration
from app.schemas import CarConfigurationData, CarData


class CarRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create_configuration(self, data: CarConfigurationData) -> CarConfiguration:
        """Возвращает конфигурацию, создавая её при отсутствии (без гонок)."""
        values = data.model_dump()
        await self._session.execute(
            sqlite_insert(CarConfiguration).values(**values).on_conflict_do_nothing()
        )
        result = await self._session.execute(
            select(CarConfiguration)
            .where(
                CarConfiguration.brand == data.brand,
                CarConfiguration.model == data.model,
                CarConfiguration.year == data.year,
                CarConfiguration.engine_code == data.engine_code,
                CarConfiguration.transmission == data.transmission,
                CarConfiguration.drive_type == data.drive_type,
            )
            .execution_options(populate_existing=True)
        )
        return result.scalar_one()

    async def create_car(self, *, player_id: int, configuration_id: int, data: CarData) -> Car:
        """Добавляет автомобиль. IntegrityError при повторном VIN или отсутствии игрока."""
        car = Car(
            player_id=player_id,
            configuration_id=configuration_id,
            vin=data.vin,
            plate=data.plate,
            mileage_km=data.mileage_km,
            color=data.color,
            condition_pct=data.condition_pct,
        )
        self._session.add(car)
        await self._session.flush()
        return car

    async def get(self, player_id: int, car_id: int, *, with_configuration: bool = False) -> Car | None:
        stmt = (
            select(Car)
            .where(Car.id == car_id, Car.player_id == player_id)
            .execution_options(populate_existing=True)
        )
        if with_configuration:
            stmt = stmt.options(selectinload(Car.configuration))
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_for_player(self, player_id: int) -> list[Car]:
        result = await self._session.execute(
            select(Car)
            .where(Car.player_id == player_id)
            .options(selectinload(Car.configuration))
            .order_by(Car.id)
        )
        return list(result.scalars())

    async def list_configurations(self) -> list[CarConfiguration]:
        result = await self._session.execute(
            select(CarConfiguration).order_by(CarConfiguration.id)
        )
        return list(result.scalars())
