"""Ремонт: операции, списание деталей, проверка результата и сдача заказа.

Гарантии:
  * операция выполняется ровно один раз (уникальность (order_id, op_code) + блокировка заказа);
  * детали списываются только при успешной операции и в той же транзакции;
  * заказ нельзя сдать, пока не выполнены обязательные операции и не пройдена проверка;
  * проверка результата сверяет реальные (скрытые) неисправности с устранёнными.
"""

import json
import logging
from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import (
    InvalidOrderState,
    MissingParts,
    NothingToVerify,
    OperationAlreadyDone,
    OrderNotFound,
    UnknownOperation,
)
from app.game_data.diagnostic_checks import DEADLINE_MINUTES_PER_GAME_MINUTE
from app.game_data.enums import OrderStatus
from app.game_data.part_catalog import (
    PART_TYPE_BY_CODE,
    QUALITIES,
    fit_value,
    make_sku,
)
from app.game_data.rarity import difficulty_of
from app.game_data.repair_catalog import CAUSE_OF_OP, OPS_BY_CODE, ops_for_cause
from app.models import Order
from app.repositories import (
    CarRepository,
    DiagnosticRepository,
    FaultRepository,
    FinanceRepository,
    InventoryRepository,
    OrderRepository,
    RepairRepository,
)
from app.schemas import (
    FaultRepairView,
    FinishResult,
    NeedView,
    OperationResult,
    OperationView,
    RepairOverview,
    UsedPart,
    VerificationResult,
)
from app.services.order_service import OrderService
from app.services.progress_service import ProgressService
from app.services.transaction import atomic
from app.services.vehicle import configuration_tags

logger = logging.getLogger(__name__)

REPAIR_STATUSES = frozenset(
    {OrderStatus.DIAGNOSTICS, OrderStatus.AWAITING_PARTS, OrderStatus.IN_REPAIR}
)
VERIFY_MINUTES = 15
BASE_EXPERIENCE = 20
EXPERIENCE_PER_DIFFICULTY = 15


class RepairService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._orders = OrderRepository(session)
        self._cars = CarRepository(session)
        self._faults = FaultRepository(session)
        self._repairs = RepairRepository(session)
        self._inventory = InventoryRepository(session)
        self._diag = DiagnosticRepository(session)
        self._finance = FinanceRepository(session)

    # --- чтение ----------------------------------------------------------------

    async def get_overview(self, player_id: int, order_id: int) -> RepairOverview:
        order = await self._get_order(player_id, order_id)
        car = await self._cars.get(player_id, order.car_id, with_configuration=True)
        assert car is not None
        config = car.configuration
        tags = configuration_tags(config)
        faults = await self._faults.list_for_order(order_id)
        done = {op.op_code for op in await self._repairs.list_for_order(order_id)}
        stock = {i.part.sku: i.quantity for i in await self._inventory.list_stock(player_id)}
        fault_views = []
        for fault in faults:
            ops = []
            for op in ops_for_cause(fault.code):
                needs = tuple(
                    NeedView(
                        type_code=n.type_code,
                        name=PART_TYPE_BY_CODE[n.type_code].name,
                        qty=n.qty,
                        in_stock=self._available(n.type_code, tags, stock),
                    )
                    for n in op.needs
                )
                ops.append(
                    OperationView(
                        code=op.code, title=op.title, minutes=op.minutes,
                        done=op.code in done, needs=needs,
                    )
                )
            fault_views.append(
                FaultRepairView(
                    fault_id=fault.id, code=fault.code, name=fault.name, system=fault.system,
                    resolved=fault.is_resolved, ops=tuple(ops),
                )
            )
        session = await self._diag.get_session(order_id)
        balance = await self._finance.get_balance(player_id)
        assert balance is not None
        return RepairOverview(
            order_id=order_id,
            status=order.status,
            car_title=f"{config.brand} {config.model}, {config.year}",
            plate=car.plate,
            complaint=order.complaint,
            faults=tuple(fault_views),
            balance=balance,
            deadline_at=order.deadline_at,
            diagnostics_open=session is not None and session.concluded_at is None,
        )

    @staticmethod
    def _skus(type_code: str, tags: dict[str, object]) -> list[str]:
        ptype = PART_TYPE_BY_CODE[type_code]
        fit = fit_value(ptype, tags)
        # от худшего качества к лучшему: сначала тратится бюджетное, оригинал — в последнюю очередь
        return [make_sku(ptype.code, fit, q.level) for q in QUALITIES]

    def _available(self, type_code: str, tags: dict[str, object], stock: dict[str, int]) -> int:
        return sum(stock.get(sku, 0) for sku in self._skus(type_code, tags))

    # --- операция -----------------------------------------------------------------

    async def perform_operation(
        self, *, player_id: int, order_id: int, op_code: str
    ) -> OperationResult:
        """Выполняет ремонтную операцию, списывая подходящие детали со склада.

        Raises: OrderNotFound, InvalidOrderState, UnknownOperation, OperationAlreadyDone,
            MissingParts.
        """
        op = OPS_BY_CODE.get(op_code)
        if op is None:
            raise UnknownOperation(op_code)
        try:
            return await self._perform(player_id, order_id, op_code)
        except IntegrityError as exc:
            # Параллельный запрос успел раньше: транзакция откачена, детали не списаны.
            raise OperationAlreadyDone(op_code) from exc

    async def _perform(self, player_id: int, order_id: int, op_code: str) -> OperationResult:
        op = OPS_BY_CODE[op_code]
        async with atomic(self._session):
            locked = await self._orders.touch_if_status(
                order_id=order_id, player_id=player_id, statuses=REPAIR_STATUSES
            )
            order = await self._get_order(player_id, order_id)
            if not locked:
                raise InvalidOrderState(order_id, order.status)
            car = await self._cars.get(player_id, order.car_id, with_configuration=True)
            assert car is not None
            tags = configuration_tags(car.configuration)

            faults = await self._faults.list_for_order(order_id)
            fault = next((f for f in faults if f.code == CAUSE_OF_OP[op_code]), None)
            if fault is None:
                raise UnknownOperation(op_code)
            done = {o.op_code for o in await self._repairs.list_for_order(order_id)}
            if op_code in done:
                raise OperationAlreadyDone(op_code)

            # 1. подбираем детали (только совместимые), ничего ещё не списывая
            plan: list[tuple[int, str, int, int]] = []  # (part_id, name, qty, price)
            missing: list[str] = []
            for need in op.needs:
                remaining = need.qty
                for sku in self._skus(need.type_code, tags):
                    if remaining == 0:
                        break
                    part = await self._inventory.get_part_by_sku(sku)
                    if part is None:
                        continue
                    have = await self._inventory.get_stock_quantity(player_id, part.id)
                    take = min(have, remaining)
                    if take > 0:
                        plan.append((part.id, part.name, take, part.base_price, sku))  # type: ignore[arg-type]
                        remaining -= take
                if remaining:
                    missing.append(f"{PART_TYPE_BY_CODE[need.type_code].name} ×{remaining}")
            if missing:
                raise MissingParts(missing)

            # 2. списываем и записываем в заказ
            used: list[UsedPart] = []
            for part_id, name, qty, price, sku in plan:  # type: ignore[misc]
                if not await self._inventory.take_stock(player_id, part_id, qty):
                    raise MissingParts([name])
                await self._orders.add_part(
                    order_id=order_id, part_id=part_id, quantity=qty, unit_price=price
                )
                used.append(UsedPart(sku=sku, name=name, qty=qty, price=price))

            # 3. фиксируем операцию (уникальность — защита от повтора)
            await self._repairs.add_operation(
                order_id=order_id,
                player_id=player_id,
                fault_id=fault.id,
                op_code=op_code,
                minutes=op.minutes,
                parts_json=json.dumps([u.model_dump() for u in used], ensure_ascii=False),
            )

            if order.status != OrderStatus.IN_REPAIR:
                await self._orders.transition_status(
                    order_id=order_id, player_id=player_id,
                    expected=order.status, new=OrderStatus.IN_REPAIR,
                )
            if order.deadline_at is not None:
                await self._orders.set_deadline(
                    order_id=order_id, player_id=player_id,
                    deadline_at=order.deadline_at
                    - timedelta(minutes=op.minutes * DEADLINE_MINUTES_PER_GAME_MINUTE),
                )

            # 4. неисправность устранена, когда выполнены все её операции
            fault_ops = {o.code for o in ops_for_cause(fault.code)}
            fault_resolved = fault_ops <= (done | {op_code})
            if fault_resolved:
                await self._faults.resolve(order_id=order_id, fault_id=fault.id)
            all_resolved = fault_resolved and all(
                f.is_resolved or f.id == fault.id for f in faults
            )
        logger.info("Заказ %s: операция %s выполнена", order_id, op_code)
        return OperationResult(
            order_id=order_id, op_code=op_code, title=op.title, minutes=op.minutes,
            parts=tuple(used), fault_resolved=fault_resolved, all_resolved=all_resolved,
        )

    # --- проверка результата ----------------------------------------------------------

    async def verify(self, *, player_id: int, order_id: int) -> VerificationResult:
        """Тест-драйв: сравнивает реальные неисправности с устранёнными.

        Всё устранено — заказ готов к выдаче (READY). Если часть реальных поломок осталась
        (неверный вывод диагностики), жалоба сохраняется, заключение снимается, и
        диагностику можно продолжить.

        Raises: OrderNotFound, InvalidOrderState, NothingToVerify.
        """
        async with atomic(self._session):
            locked = await self._orders.touch_if_status(
                order_id=order_id, player_id=player_id, statuses={OrderStatus.IN_REPAIR}
            )
            order = await self._get_order(player_id, order_id)
            if not locked:
                raise InvalidOrderState(order_id, order.status)
            faults = await self._faults.list_for_order(order_id)
            if not faults:
                raise NothingToVerify("Нет внесённых неисправностей")
            if any(not f.is_resolved for f in faults):
                raise NothingToVerify("Сначала выполни все ремонтные операции")
            truth = await self._diag.list_hidden(order_id)
            resolved = {f.code for f in faults}
            remains = [code for code in truth if code not in resolved]
            if order.deadline_at is not None:
                await self._orders.set_deadline(
                    order_id=order_id, player_id=player_id,
                    deadline_at=order.deadline_at
                    - timedelta(minutes=VERIFY_MINUTES * DEADLINE_MINUTES_PER_GAME_MINUTE),
                )
            if remains:
                await self._diag.reopen(order_id=order_id)
            else:
                await self._orders.transition_status(
                    order_id=order_id, player_id=player_id,
                    expected=OrderStatus.IN_REPAIR, new=OrderStatus.READY,
                )
        return VerificationResult(
            order_id=order_id, ok=not remains, complaint_remains=bool(remains), minutes=VERIFY_MINUTES
        )

    # --- сдача заказа ---------------------------------------------------------------------

    async def finish(self, *, player_id: int, order_id: int) -> FinishResult:
        """Сдаёт готовый заказ через OrderService.complete_order (награда не более одного раза)."""
        order = await self._get_order(player_id, order_id)
        car = await self._cars.get(player_id, order.car_id, with_configuration=True)
        assert car is not None
        brand, model = car.configuration.brand, car.configuration.model
        await self._session.rollback()  # закрываем читающую транзакцию перед записью
        result = await OrderService(self._session).complete_order(
            player_id=player_id, order_id=order_id
        )
        gained, level, leveled = 0, None, False
        if not result.already_completed:
            gained = BASE_EXPERIENCE + EXPERIENCE_PER_DIFFICULTY * difficulty_of(brand, model)
            progress = await ProgressService(self._session).add_experience(player_id, gained)
            level, leveled = progress.level, progress.leveled_up
        return FinishResult(
            order_id=order_id,
            reward_paid=result.reward_paid,
            bonus=result.bonus,
            parts_cost=result.parts_cost,
            profit=result.profit,
            balance=result.balance,
            experience_gained=gained,
            level=level,
            leveled_up=leveled,
            already_completed=result.already_completed,
        )

    async def _get_order(self, player_id: int, order_id: int) -> Order:
        order = await self._orders.get(player_id, order_id)
        if order is None:
            raise OrderNotFound(order_id)
        return order
