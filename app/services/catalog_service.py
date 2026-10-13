"""Загрузка стартового каталога в БД."""

from dataclasses import asdict

from sqlalchemy.ext.asyncio import AsyncSession

from app.game_data.catalog import CAR_CONFIGURATIONS, EQUIPMENT, PARTS
from app.game_data.diagnostic_checks import DIAGNOSTIC_EQUIPMENT
from app.repositories import CarRepository, InventoryRepository
from app.schemas import CarConfigurationData
from app.services.transaction import atomic


async def seed_catalog(session: AsyncSession) -> None:
    """Добавляет недостающие записи каталога. Повторный вызов ничего не дублирует."""
    inventory = InventoryRepository(session)
    cars = CarRepository(session)
    async with atomic(session):
        await inventory.seed_parts(PARTS)
        await inventory.seed_equipment(EQUIPMENT + DIAGNOSTIC_EQUIPMENT)
        for spec in CAR_CONFIGURATIONS:
            await cars.get_or_create_configuration(CarConfigurationData(**asdict(spec)))
