"""Магазин и склад: каталог запчастей, подбор под автомобиль, покупка.

Покупка атомарна: списание денег и добавление деталей на склад — одна транзакция
(InventoryService.purchase_part). Защита от двойного нажатия — ключ идемпотентности,
в который входит номер последней записи журнала на момент показа экрана.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import OrderNotFound, ShopStale, UnknownPart
from app.game_data.enums import OrderStatus
from app.game_data.order_flow import ACTIVE_STATUSES
from app.game_data.part_catalog import (
    PART_TYPE_BY_CODE,
    QUALITIES,
    QUALITY_BY_LEVEL,
    SECTIONS,
    fit_models,
    fit_value,
    make_sku,
    parse_sku,
    price_of,
    spec_for,
)
from app.game_data.repair_catalog import FAULT_INFO
from app.repositories import (
    CarRepository,
    FaultRepository,
    FinanceRepository,
    InventoryRepository,
    OrderRepository,
    RepairRepository,
)
from app.schemas import (
    OrderPartsPlan,
    PlanLine,
    PurchaseResult,
    QualityView,
    ShopOrderOption,
    ShopTypeView,
    StockLine,
)
from app.services.inventory_service import InventoryService
from app.services.transaction import atomic
from app.services.vehicle import configuration_tags

logger = logging.getLogger(__name__)

MAX_QUANTITY = 99
_FIT_TITLES = {
    "engine": "двигатель",
    "chassis": "кузов/шасси",
    "plug": "группа свечей",
    "battery": "класс АКБ",
    "trans": "коробка",
}


def purchase_key(player_id: int, sku: str, quantity: int, ver: int) -> str:
    return f"shop:{player_id}:{sku}:{quantity}:{ver}"


class ShopService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._inventory = InventoryRepository(session)
        self._finance = FinanceRepository(session)
        self._cars = CarRepository(session)
        self._orders = OrderRepository(session)
        self._faults = FaultRepository(session)
        self._repairs = RepairRepository(session)

    # --- чтение --------------------------------------------------------------

    async def list_orders(self, player_id: int) -> list[ShopOrderOption]:
        """Активные заказы игрока: для них подбираются детали."""
        orders = await self._orders.list_for_player(player_id, statuses=list(ACTIVE_STATUSES))
        options = []
        for order in orders:
            car = await self._cars.get(player_id, order.car_id, with_configuration=True)
            if car is None:
                continue
            c = car.configuration
            options.append(ShopOrderOption(order_id=order.id, car_title=f"{c.brand} {c.model}, {c.year}"))
        return options

    async def _order_tags(self, player_id: int, order_id: int) -> tuple[dict[str, object], str]:
        order = await self._orders.get(player_id, order_id)
        if order is None:
            raise OrderNotFound(order_id)
        car = await self._cars.get(player_id, order.car_id, with_configuration=True)
        assert car is not None
        c = car.configuration
        return configuration_tags(c), f"{c.brand} {c.model}, {c.year}"

    async def _stock_map(self, player_id: int) -> dict[str, int]:
        return {item.part.sku: item.quantity for item in await self._inventory.list_stock(player_id)}

    async def type_view(self, player_id: int, type_code: str, order_id: int = 0) -> ShopTypeView:
        """Карточка типа детали с тремя вариантами качества, ценами и остатком на складе."""
        ptype = PART_TYPE_BY_CODE.get(type_code)
        if ptype is None:
            raise UnknownPart(type_code)
        tags: dict[str, object] = {}
        car_title: str | None = None
        if not ptype.universal:
            if not order_id:
                raise OrderNotFound(order_id)
            tags, car_title = await self._order_tags(player_id, order_id)
        fit = fit_value(ptype, tags)
        stock = await self._stock_map(player_id)
        qualities = []
        for q in QUALITIES:
            sku = make_sku(ptype.code, fit, q.level)
            existing = await self._inventory.get_part_by_sku(sku)
            price = existing.base_price if existing else price_of(ptype, fit, q.level)
            qualities.append(
                QualityView(
                    sku=sku, level=q.level, title=q.title, emoji=q.emoji, note=q.note,
                    price=price, stock=stock.get(sku, 0),
                )
            )
        balance = await self._finance.get_balance(player_id)
        assert balance is not None
        fit_label = "универсальная" if ptype.universal else f"{_FIT_TITLES[ptype.fit or '']} {fit}"
        return ShopTypeView(
            type_code=ptype.code,
            name=ptype.name,
            section=ptype.section,
            universal=ptype.universal,
            fit_label=fit_label,
            models=tuple(fit_models(ptype, fit)),
            qualities=tuple(qualities),
            balance=balance,
            ver=await self._finance.last_transaction_id(player_id),
            order_id=order_id,
            car_title=car_title,
        )

    async def inventory(self, player_id: int) -> list[StockLine]:
        lines = []
        for item in await self._inventory.list_stock(player_id):
            parsed = parse_sku(item.part.sku)
            if parsed is None:
                section, emoji = "Прочее", ""
            else:
                ptype, _, level = parsed
                section, emoji = ptype.section, QUALITY_BY_LEVEL[level].emoji
            lines.append(
                StockLine(
                    sku=item.part.sku, name=item.part.name, quantity=item.quantity,
                    section=section, quality_emoji=emoji,
                )
            )
        order = {s: i for i, s in enumerate((*SECTIONS, "Прочее"))}
        return sorted(lines, key=lambda l: (order.get(l.section, 99), l.name))

    async def order_plan(self, player_id: int, order_id: int) -> OrderPartsPlan:
        """«Подбор по заказу»: какие детали нужны для невыполненных операций и чего не хватает."""
        from app.game_data.repair_catalog import ops_for_cause

        tags, car_title = await self._order_tags(player_id, order_id)
        faults = await self._faults.list_for_order(order_id)
        done = {op.op_code for op in await self._repairs.list_for_order(order_id)}
        stock = await self._stock_map(player_id)
        lines: list[PlanLine] = []
        for fault in faults:
            if fault.is_resolved or fault.code not in FAULT_INFO:
                continue
            for op in ops_for_cause(fault.code):
                if op.code in done:
                    continue
                for need in op.needs:
                    ptype = PART_TYPE_BY_CODE[need.type_code]
                    fit = fit_value(ptype, tags)
                    have = sum(
                        stock.get(make_sku(ptype.code, fit, q.level), 0) for q in QUALITIES
                    )
                    lines.append(
                        PlanLine(
                            fault_name=fault.name, op_title=op.title, type_code=ptype.code,
                            part_name=ptype.name, qty=need.qty, in_stock=have,
                            unit_price=price_of(ptype, fit, 2),
                        )
                    )
        balance = await self._finance.get_balance(player_id)
        assert balance is not None
        return OrderPartsPlan(order_id=order_id, car_title=car_title, lines=tuple(lines), balance=balance)

    # --- покупка ---------------------------------------------------------------

    async def buy(
        self, *, player_id: int, type_code: str, quality: int, quantity: int, order_id: int, ver: int
    ) -> PurchaseResult:
        """Покупает деталь. SKU собирается на сервере по автомобилю заказа.

        Повтор с теми же параметрами (двойное нажатие) возвращает duplicate=True и не
        списывает деньги. Если после показа экрана деньги/склад менялись, ShopStale.

        Raises: UnknownPart, OrderNotFound, ShopStale, InsufficientFunds, ValueError.
        """
        ptype = PART_TYPE_BY_CODE.get(type_code)
        if ptype is None or quality not in QUALITY_BY_LEVEL:
            raise UnknownPart(type_code)
        if not 1 <= quantity <= MAX_QUANTITY:
            raise ValueError("Количество должно быть от 1 до 99")
        tags: dict[str, object] = {}
        if not ptype.universal:
            tags, _ = await self._order_tags(player_id, order_id)
        sku = make_sku(ptype.code, fit_value(ptype, tags), quality)
        spec = spec_for(sku)
        if spec is None:
            raise UnknownPart(sku)
        key = purchase_key(player_id, sku, quantity, ver)

        if await self._finance.get_by_key(key) is None:
            if await self._finance.last_transaction_id(player_id) != ver:
                raise ShopStale()
        await self._session.rollback()  # закрываем читающую транзакцию: запись начнём «с чистого листа»
        async with atomic(self._session):
            await self._inventory.seed_parts((spec,))
        result = await InventoryService(self._session).purchase_part(
            player_id=player_id, sku=sku, quantity=quantity, idempotency_key=key
        )
        logger.info("Покупка %s ×%s игроком %s (дубликат=%s)", sku, quantity, player_id, result.duplicate)
        return result

    @staticmethod
    def active_statuses() -> frozenset[OrderStatus]:
        return ACTIVE_STATUSES
