"""Сервис склада и оборудования: покупки за деньги игрока."""

from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import (
    EquipmentAlreadyOwned,
    EquipmentNotFound,
    IdempotencyConflict,
    LevelTooLow,
    PartNotFound,
    PlayerNotFound,
)
from app.game_data.enums import TransactionCategory
from app.models import Equipment, Part, PlayerEquipment, StockItem
from app.repositories import FinanceRepository, InventoryRepository, PlayerRepository
from app.schemas import PurchaseResult
from app.services.transaction import atomic


class InventoryService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._finance = FinanceRepository(session)
        self._inventory = InventoryRepository(session)
        self._players = PlayerRepository(session)

    async def purchase_part(
        self,
        *,
        player_id: int,
        sku: str,
        quantity: int,
        idempotency_key: str | None = None,
    ) -> PurchaseResult:
        """Покупает детали на склад: списывает деньги и добавляет остаток одной транзакцией.

        Повтор с тем же idempotency_key ничего не меняет (duplicate=True).

        Raises:
            PartNotFound, InsufficientFunds, PlayerNotFound, IdempotencyConflict.
        """
        if quantity <= 0:
            raise ValueError("Количество должно быть положительным")
        key = idempotency_key or f"purchase_part:{uuid4().hex}"

        try:
            async with atomic(self._session):
                part = await self._inventory.get_part_by_sku(sku)
                if part is None:
                    raise PartNotFound(sku)
                total = part.base_price * quantity
                entry, duplicate = await self._finance.apply_change(
                    player_id=player_id,
                    amount=-total,
                    category=TransactionCategory.PART_PURCHASE,
                    idempotency_key=key,
                    description=f"Покупка: {part.name} × {quantity}",
                )
                if not duplicate:
                    await self._inventory.add_stock(player_id, part.id, quantity)
        except IntegrityError:
            # Параллельный запрос с тем же ключом успел раньше: транзакция откачена,
            # деньги и склад не изменены. Возвращаем результат победителя.
            existing = await self._finance.get_by_key(key)
            if existing is None:
                raise
            if (
                existing.player_id != player_id
                or existing.category != TransactionCategory.PART_PURCHASE
            ):
                raise IdempotencyConflict(key) from None
            return PurchaseResult(
                item_code=sku,
                quantity=quantity,
                total_price=-existing.amount,
                balance_after=existing.balance_after,
                duplicate=True,
            )
        return PurchaseResult(
            item_code=sku,
            quantity=quantity,
            total_price=total,
            balance_after=entry.balance_after,
            duplicate=duplicate,
        )

    async def buy_equipment(
        self, *, player_id: int, code: str, idempotency_key: str | None = None
    ) -> PurchaseResult:
        """Покупает оборудование: проверяет уровень, списывает деньги, выдаёт предмет.

        Raises:
            EquipmentNotFound, LevelTooLow, EquipmentAlreadyOwned, InsufficientFunds,
            PlayerNotFound, IdempotencyConflict.
        """
        key = idempotency_key or f"buy_equipment:{uuid4().hex}"
        try:
            async with atomic(self._session):
                equipment = await self._inventory.get_equipment_by_code(code)
                if equipment is None:
                    raise EquipmentNotFound(code)
                level = await self._players.get_level(player_id)
                if level is None:
                    raise PlayerNotFound(player_id)
                if level < equipment.required_level:
                    raise LevelTooLow(equipment.required_level, level)
                if await self._inventory.owns_equipment(player_id, equipment.id):
                    # Повторный запрос с уже проведённым ключом — не ошибка.
                    existing = await self._finance.get_by_key(key)
                    if existing is not None:
                        return PurchaseResult(
                            item_code=code,
                            quantity=1,
                            total_price=equipment.price,
                            balance_after=existing.balance_after,
                            duplicate=True,
                        )
                    raise EquipmentAlreadyOwned(code)

                balance_after = await self._charge_equipment(player_id, equipment, key)
                await self._inventory.add_player_equipment(player_id, equipment.id)
        except IntegrityError as exc:
            # Одновременная покупка того же предмета: уникальность (игрок, предмет)
            # сработала, вся транзакция откачена, деньги не списаны.
            raise EquipmentAlreadyOwned(code) from exc
        return PurchaseResult(
            item_code=code,
            quantity=1,
            total_price=equipment.price,
            balance_after=balance_after,
            duplicate=False,
        )

    async def _charge_equipment(self, player_id: int, equipment: Equipment, key: str) -> int:
        """Списывает стоимость оборудования. Бесплатное оборудование деньги не трогает."""
        if equipment.price == 0:
            balance = await self._finance.get_balance(player_id)
            assert balance is not None
            return balance
        entry, _ = await self._finance.apply_change(
            player_id=player_id,
            amount=-equipment.price,
            category=TransactionCategory.EQUIPMENT_PURCHASE,
            idempotency_key=key,
            description=f"Покупка: {equipment.name}",
        )
        return entry.balance_after

    async def list_parts(self) -> list[Part]:
        return await self._inventory.list_parts()

    async def list_equipment_catalog(self) -> list[Equipment]:
        return await self._inventory.list_equipment()

    async def get_stock(self, player_id: int) -> list[StockItem]:
        """Склад игрока: только позиции с ненулевым остатком, с данными детали."""
        return await self._inventory.list_stock(player_id)

    async def get_player_equipment(self, player_id: int) -> list[PlayerEquipment]:
        return await self._inventory.list_player_equipment(player_id)
