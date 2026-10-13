"""Репозиторий склада, каталога запчастей и оборудования игрока."""

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.game_data.catalog import EquipmentSpec, PartSpec
from app.models import Equipment, Part, PlayerEquipment, StockItem
from app.models.types import utc_now


class InventoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- каталог ---------------------------------------------------------

    async def get_part_by_sku(self, sku: str) -> Part | None:
        result = await self._session.execute(select(Part).where(Part.sku == sku))
        return result.scalar_one_or_none()

    async def get_equipment_by_code(self, code: str) -> Equipment | None:
        result = await self._session.execute(select(Equipment).where(Equipment.code == code))
        return result.scalar_one_or_none()

    async def list_parts(self) -> list[Part]:
        return list((await self._session.execute(select(Part).order_by(Part.id))).scalars())

    async def list_equipment(self) -> list[Equipment]:
        return list(
            (await self._session.execute(select(Equipment).order_by(Equipment.id))).scalars()
        )

    async def seed_parts(self, specs: tuple[PartSpec, ...]) -> None:
        """Добавляет недостающие запчасти. Существующие не изменяются."""
        for spec in specs:
            await self._session.execute(
                sqlite_insert(Part)
                .values(
                    sku=spec.sku,
                    name=spec.name,
                    category=spec.category,
                    base_price=spec.base_price,
                )
                .on_conflict_do_nothing(index_elements=["sku"])
            )

    async def ensure_part(self, spec: PartSpec) -> Part:
        """Возвращает запчасть с таким SKU, создавая запись при первом обращении."""
        part = await self.get_part_by_sku(spec.sku)
        if part is not None:
            return part
        await self.seed_parts((spec,))
        part = await self.get_part_by_sku(spec.sku)
        assert part is not None
        return part

    async def seed_equipment(self, specs: tuple[EquipmentSpec, ...]) -> None:
        """Добавляет недостающее оборудование. Существующее не изменяется."""
        for spec in specs:
            await self._session.execute(
                sqlite_insert(Equipment)
                .values(
                    code=spec.code,
                    name=spec.name,
                    category=spec.category,
                    price=spec.price,
                    required_level=spec.required_level,
                )
                .on_conflict_do_nothing(index_elements=["code"])
            )

    # --- склад -----------------------------------------------------------

    async def get_stock_quantity(self, player_id: int, part_id: int) -> int:
        quantity = await self._session.scalar(
            select(StockItem.quantity).where(
                StockItem.player_id == player_id, StockItem.part_id == part_id
            )
        )
        return quantity or 0

    async def list_stock(self, player_id: int) -> list[StockItem]:
        result = await self._session.execute(
            select(StockItem)
            .where(StockItem.player_id == player_id, StockItem.quantity > 0)
            .options(selectinload(StockItem.part))
            .order_by(StockItem.part_id)
            .execution_options(populate_existing=True)
        )
        return list(result.scalars())

    async def add_stock(self, player_id: int, part_id: int, quantity: int) -> None:
        """Атомарно увеличивает остаток (создаёт строку склада при необходимости)."""
        if quantity <= 0:
            raise ValueError("Количество должно быть положительным")
        stmt = sqlite_insert(StockItem).values(
            player_id=player_id, part_id=part_id, quantity=quantity, updated_at=utc_now()
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["player_id", "part_id"],
            set_={
                "quantity": StockItem.quantity + stmt.excluded.quantity,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        await self._session.execute(stmt)

    async def take_stock(self, player_id: int, part_id: int, quantity: int) -> bool:
        """Атомарно списывает остаток. False, если деталей не хватает (склад не меняется)."""
        if quantity <= 0:
            raise ValueError("Количество должно быть положительным")
        result = await self._session.execute(
            update(StockItem)
            .where(
                StockItem.player_id == player_id,
                StockItem.part_id == part_id,
                StockItem.quantity >= quantity,
            )
            .values(quantity=StockItem.quantity - quantity, updated_at=utc_now())
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1

    # --- оборудование игрока --------------------------------------------

    async def add_player_equipment(self, player_id: int, equipment_id: int) -> PlayerEquipment:
        """Добавляет оборудование игроку. IntegrityError, если оно уже есть."""
        item = PlayerEquipment(player_id=player_id, equipment_id=equipment_id)
        self._session.add(item)
        await self._session.flush()
        return item

    async def owns_equipment(self, player_id: int, equipment_id: int) -> bool:
        found = await self._session.scalar(
            select(PlayerEquipment.id).where(
                PlayerEquipment.player_id == player_id,
                PlayerEquipment.equipment_id == equipment_id,
            )
        )
        return found is not None

    async def list_player_equipment(self, player_id: int) -> list[PlayerEquipment]:
        result = await self._session.execute(
            select(PlayerEquipment)
            .where(PlayerEquipment.player_id == player_id)
            .options(selectinload(PlayerEquipment.equipment))
            .order_by(PlayerEquipment.id)
            .execution_options(populate_existing=True)
        )
        return list(result.scalars())
