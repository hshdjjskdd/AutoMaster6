"""Диагностика автомобиля: проверки, журнал, расход времени и денег, заключение.

Реальная поломка определяется при первой проверке заказа, сохраняется в БД и
не показывается игроку. Игрок видит только измерения (с шумом и неоднозначностью)
и делает вывод сам. Время проверки сдвигает срок заказа, деньги списываются через
общий финансовый журнал; всё выполняется одной транзакцией.
"""

import json
import logging
import random
from dataclasses import asdict
from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import (
    DiagnosticsConcluded,
    DiagnosticsNotStarted,
    DiagnosticStale,
    FaultAlreadyRecorded,
    InvalidConclusion,
    InvalidOrderState,
    OrderNotFound,
    UnknownCheck,
)
from app.game_data.diagnostic_checks import (
    CHECK_BY_CODE,
    CHECKS,
    DEADLINE_MINUTES_PER_GAME_MINUTE,
    TOOL_CODES,
    TOOL_TITLES,
    CheckDef,
    check_available,
    check_fee,
)
from app.game_data.diagnostic_engine import Reading, VehicleContext, perform_check
from app.game_data.enums import OrderStatus, TransactionCategory
from app.game_data.order_planner import parse_plan
from app.game_data.fault_catalog import CAUSE_BY_CODE, CAUSES, generate_truth, matches, truth_from_plan
from app.models import DiagnosticCheckRun, Order
from app.models.types import utc_now
from app.repositories import (
    CarRepository,
    DiagnosticRepository,
    FaultRepository,
    FinanceRepository,
    InventoryRepository,
    OfferRepository,
    OrderRepository,
)
from app.schemas import (
    CheckOption,
    CheckRunView,
    ConclusionFault,
    ConclusionResult,
    DiagnosticOverview,
    ReadingView,
    ToolOption,
)
from app.services.transaction import atomic
from app.services.vehicle import configuration_tags

logger = logging.getLogger(__name__)

# Проверки доступны, пока диагностика не завершена заключением. После неудачной проверки
# ремонта заключение снимается, и диагностику можно продолжить уже в ходе ремонта.
CHECKABLE_STATUSES = frozenset(
    {OrderStatus.NEW, OrderStatus.DIAGNOSTICS, OrderStatus.AWAITING_PARTS, OrderStatus.IN_REPAIR}
)
CONCLUDABLE_STATUSES = frozenset(
    {OrderStatus.DIAGNOSTICS, OrderStatus.AWAITING_PARTS, OrderStatus.IN_REPAIR}
)
MAX_CONCLUSION_FAULTS = 3


def check_idempotency_key(order_id: int, run_no: int) -> str:
    """Ключ списания за проверку: одну и ту же попытку нельзя оплатить дважды."""
    return f"diag_check:{order_id}:{run_no}"


def _run_view(run: DiagnosticCheckRun) -> CheckRunView:
    definition = CHECK_BY_CODE.get(run.check_code)
    readings = tuple(ReadingView(**item) for item in json.loads(run.readings_json))
    return CheckRunView(
        run_no=run.run_no,
        check_code=run.check_code,
        title=definition.title if definition else run.check_code,
        emoji=definition.emoji if definition else "🔧",
        tool_title=TOOL_TITLES.get(run.tool_code) if run.tool_code else None,
        tool_owned=run.tool_owned,
        minutes=run.minutes,
        cost=run.cost,
        readings=readings,
        interpretation=run.interpretation,
        created_at=run.created_at,
    )


class DiagnosticService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._diag = DiagnosticRepository(session)
        self._orders = OrderRepository(session)
        self._cars = CarRepository(session)
        self._faults = FaultRepository(session)
        self._finance = FinanceRepository(session)
        self._inventory = InventoryRepository(session)
        self._offers = OfferRepository(session)

    # --- чтение ----------------------------------------------------------------

    async def get_overview(self, player_id: int, order_id: int) -> DiagnosticOverview:
        """Меню диагностики: сводка заказа и список проверок с ценой и временем."""
        order = await self._get_order(player_id, order_id)
        car = await self._cars.get(player_id, order.car_id, with_configuration=True)
        assert car is not None
        owned = await self._owned_tools(player_id)
        session = await self._diag.get_session(order_id)
        done = await self._diag.count_by_check(order_id)
        balance = await self._finance.get_balance(player_id)
        assert balance is not None
        concluded = session is not None and session.concluded_at is not None
        config = car.configuration
        return DiagnosticOverview(
            order_id=order_id,
            order_status=order.status,
            car_title=f"{config.brand} {config.model}, {config.year}",
            plate=car.plate,
            complaint=order.complaint,
            runs=sum(done.values()),
            minutes_spent=session.minutes_spent if session else 0,
            money_spent=session.money_spent if session else 0,
            balance=balance,
            deadline_at=order.deadline_at,
            concluded=concluded,
            can_run=order.status in CHECKABLE_STATUSES and not concluded,
            options=tuple(
                self._option(c, owned, done)
                for c in CHECKS
                if check_available(c, configuration_tags(config))
            ),
        )

    async def get_check_option(self, player_id: int, order_id: int, check_code: str) -> CheckOption:
        check = self._definition(check_code)
        order = await self._get_order(player_id, order_id)
        await self._require_applicable(player_id, order, check)
        owned = await self._owned_tools(player_id)
        done = await self._diag.count_by_check(order_id)
        return self._option(check, owned, done)

    async def get_journal(self, player_id: int, order_id: int) -> list[CheckRunView]:
        await self._get_order(player_id, order_id)
        return [_run_view(r) for r in await self._diag.list_runs(order_id)]

    async def get_run(self, player_id: int, order_id: int, run_no: int) -> CheckRunView:
        await self._get_order(player_id, order_id)
        run = await self._diag.get_run(order_id, run_no)
        if run is None:
            raise OrderNotFound(order_id)
        return _run_view(run)

    async def conclusion_causes(self, player_id: int, order_id: int) -> list[int]:
        """Индексы причин (в CAUSES), которые можно выбрать в заключении для этой машины.

        Невозможные для автомобиля причины и уже внесённые в заказ не показываются.
        """
        order = await self._get_order(player_id, order_id)
        car = await self._cars.get(player_id, order.car_id, with_configuration=True)
        assert car is not None
        tags = configuration_tags(car.configuration)
        recorded = {f.code for f in await self._faults.list_for_order(order_id)}
        return [
            i for i, c in enumerate(CAUSES)
            if matches(c.requires, tags) and c.code not in recorded
        ]

    async def list_tools(self, player_id: int) -> list[ToolOption]:
        owned = await self._owned_tools(player_id)
        catalog = {e.code: e for e in await self._inventory.list_equipment()}
        tools = []
        for code in TOOL_CODES:
            equipment = catalog.get(code)
            tools.append(
                ToolOption(
                    code=code,
                    title=TOOL_TITLES[code],
                    owned=code in owned,
                    price=equipment.price if equipment else 0,
                    required_level=equipment.required_level if equipment else 1,
                )
            )
        return tools

    # --- проверка --------------------------------------------------------------

    async def run_check(
        self,
        *,
        player_id: int,
        order_id: int,
        check_code: str,
        expected_runs: int | None = None,
    ) -> CheckRunView:
        """Выполняет проверку.

        Одной транзакцией: статус NEW -> DIAGNOSTICS, списание денег, запись в журнал,
        расход времени (срок заказа сдвигается). expected_runs защищает от двойного
        нажатия кнопки: если журнал уже изменился, проверка не выполняется и не платится.

        Raises: UnknownCheck, OrderNotFound, InvalidOrderState, DiagnosticsConcluded,
            DiagnosticStale, InsufficientFunds.
        """
        check = self._definition(check_code)
        async with atomic(self._session):
            order = await self._lock_order(player_id, order_id, CHECKABLE_STATUSES)
            car = await self._cars.get(player_id, order.car_id, with_configuration=True)
            assert car is not None
            tags = configuration_tags(car.configuration)
            if not check_available(check, tags):
                raise UnknownCheck(check.code)
            if order.status == OrderStatus.NEW:
                await self._orders.transition_status(
                    order_id=order_id,
                    player_id=player_id,
                    expected=OrderStatus.NEW,
                    new=OrderStatus.DIAGNOSTICS,
                )

            if await self._diag.create_session_if_missing(order_id=order_id, player_id=player_id):
                await self._create_truth(player_id, order_id, car.vin, tags)
            session = await self._diag.get_session(order_id)
            assert session is not None
            if session.concluded_at is not None:
                raise DiagnosticsConcluded(order_id)

            last = await self._diag.last_run_no(order_id)
            if expected_runs is not None and expected_runs != last:
                raise DiagnosticStale(order_id)
            run_no = last + 1

            owned = await self._owned_tools(player_id)
            tool_owned = check.tool_code is None or check.tool_code in owned
            fee = check_fee(check, tool_owned)
            if fee > 0:
                await self._finance.apply_change(
                    player_id=player_id,
                    amount=-fee,
                    category=TransactionCategory.ADJUSTMENT,
                    idempotency_key=check_idempotency_key(order_id, run_no),
                    order_id=order_id,
                    description=f"Диагностика: {check.title}, заказ №{order_id}",
                )

            truth = await self._diag.list_hidden(order_id)
            config = car.configuration
            context = VehicleContext(
                model=config.model,
                engine_code=config.engine_code,
                engine_volume_cc=config.engine_volume_cc,
                mileage_km=car.mileage_km,
                tags=tags,
            )
            rng = random.Random(f"{order_id}:{car.vin}:{check.code}:{run_no}")
            outcome = perform_check(check.code, context, truth, rng)

            run = await self._diag.add_run(
                order_id=order_id,
                player_id=player_id,
                run_no=run_no,
                check_code=check.code,
                tool_code=check.tool_code,
                tool_owned=tool_owned,
                minutes=check.minutes,
                cost=fee,
                readings_json=_dump(outcome.readings),
                interpretation=outcome.interpretation,
            )
            if not await self._diag.add_spent(order_id=order_id, minutes=check.minutes, money=fee):
                raise DiagnosticsConcluded(order_id)
            if order.deadline_at is not None:
                await self._orders.set_deadline(
                    order_id=order_id,
                    player_id=player_id,
                    deadline_at=order.deadline_at
                    - timedelta(minutes=check.minutes * DEADLINE_MINUTES_PER_GAME_MINUTE),
                )
        logger.info("Заказ %s: проверка %s (попытка %s), списано %s", order_id, check.code, run_no, fee)
        return _run_view(run)

    # --- заключение ---------------------------------------------------------------

    async def conclude(
        self, *, player_id: int, order_id: int, cause_codes: list[str]
    ) -> ConclusionResult:
        """Фиксирует вывод игрока: выбранные причины записываются как неисправности заказа.

        Правильность вывода здесь не оценивается — это произойдёт при ремонте.

        Raises: OrderNotFound, InvalidOrderState, DiagnosticsNotStarted,
            DiagnosticsConcluded, InvalidConclusion, FaultAlreadyRecorded.
        """
        codes = list(dict.fromkeys(cause_codes))
        if not codes:
            raise InvalidConclusion("Выбери хотя бы одну причину")
        if len(codes) > MAX_CONCLUSION_FAULTS:
            raise InvalidConclusion(f"Можно указать не более {MAX_CONCLUSION_FAULTS} причин")
        unknown = [c for c in codes if c not in CAUSE_BY_CODE]
        if unknown:
            raise InvalidConclusion("Неизвестная причина неисправности")

        try:
            async with atomic(self._session):
                order = await self._lock_order(
                    player_id, order_id, CONCLUDABLE_STATUSES, new_order_error=True
                )
                car = await self._cars.get(player_id, order.car_id, with_configuration=True)
                assert car is not None
                tags = configuration_tags(car.configuration)
                if any(not matches(CAUSE_BY_CODE[c].requires, tags) for c in codes):
                    raise InvalidConclusion("Такая неисправность невозможна на этом автомобиле")
                session = await self._diag.get_session(order_id)
                if session is None or await self._diag.last_run_no(order_id) == 0:
                    raise DiagnosticsNotStarted(order_id)
                if session.concluded_at is not None:
                    raise DiagnosticsConcluded(order_id)
                if not await self._diag.conclude(order_id=order_id, now=utc_now()):
                    raise DiagnosticsConcluded(order_id)
                for code in codes:
                    cause = CAUSE_BY_CODE[code]
                    await self._faults.add_fault(
                        order_id=order_id,
                        car_id=order.car_id,
                        code=cause.code,
                        name=cause.name,
                        system=cause.system,
                        severity=cause.severity,
                    )
                if order.status == OrderStatus.DIAGNOSTICS:
                    # Диагностика завершена, неисправности внесены: дальше — запчасти и ремонт.
                    await self._orders.transition_status(
                        order_id=order_id,
                        player_id=player_id,
                        expected=OrderStatus.DIAGNOSTICS,
                        new=OrderStatus.AWAITING_PARTS,
                    )
        except IntegrityError as exc:
            raise FaultAlreadyRecorded(",".join(codes)) from exc
        return ConclusionResult(
            order_id=order_id,
            faults=tuple(
                ConclusionFault(
                    code=c, name=CAUSE_BY_CODE[c].name, system=CAUSE_BY_CODE[c].system
                )
                for c in codes
            ),
        )

    # --- внутреннее -----------------------------------------------------------------

    @staticmethod
    def _definition(code: str) -> CheckDef:
        check = CHECK_BY_CODE.get(code)
        if check is None:
            raise UnknownCheck(code)
        return check

    async def _get_order(self, player_id: int, order_id: int) -> Order:
        order = await self._orders.get(player_id, order_id)
        if order is None:
            raise OrderNotFound(order_id)
        return order

    async def _lock_order(
        self,
        player_id: int,
        order_id: int,
        allowed: "frozenset[OrderStatus] | set[OrderStatus]",
        *,
        new_order_error: bool = False,
    ) -> Order:
        """Берёт блокировку записи через UPDATE и возвращает заказ в допустимом статусе."""
        locked = await self._orders.touch_if_status(
            order_id=order_id, player_id=player_id, statuses=allowed
        )
        order = await self._orders.get(player_id, order_id)
        if order is None:
            raise OrderNotFound(order_id)
        if not locked:
            if new_order_error and order.status == OrderStatus.NEW:
                raise DiagnosticsNotStarted(order_id)
            raise InvalidOrderState(order_id, order.status)
        return order

    async def _owned_tools(self, player_id: int) -> set[str]:
        items = await self._inventory.list_player_equipment(player_id)
        return {item.equipment.code for item in items}

    async def _require_applicable(self, player_id: int, order: Order, check: CheckDef) -> None:
        car = await self._cars.get(player_id, order.car_id, with_configuration=True)
        assert car is not None
        if not check_available(check, configuration_tags(car.configuration)):
            raise UnknownCheck(check.code)

    async def _create_truth(
        self, player_id: int, order_id: int, vin: str, tags: dict[str, object]
    ) -> None:
        offer = await self._offers.get_by_order(player_id, order_id)
        scenario = offer.scenario_code if offer else None
        seed = f"{order_id}:{vin}"
        plan = [(f.code, f.scenario_code) for f in parse_plan(offer.planned_faults)] if offer else []
        # Заказы этапа 6 несут запланированный набор неисправностей; у старых его нет.
        truth = truth_from_plan(seed, plan, tags) if plan else []
        for fault in truth or generate_truth(seed, scenario, tags):
            await self._diag.add_hidden(
                order_id=order_id, cause_code=fault.code, detail=fault.detail
            )

    @staticmethod
    def _option(check: CheckDef, owned: set[str], done: dict[str, int]) -> CheckOption:
        tool_owned = check.tool_code is None or check.tool_code in owned
        return CheckOption(
            code=check.code,
            title=check.title,
            emoji=check.emoji,
            group=check.group,
            description=check.description,
            interpretation=check.interpretation,
            minutes=check.minutes,
            fee=check_fee(check, tool_owned),
            tool_code=check.tool_code,
            tool_title=TOOL_TITLES.get(check.tool_code) if check.tool_code else None,
            tool_owned=tool_owned,
            times_done=done.get(check.code, 0),
        )


def _dump(readings: tuple[Reading, ...]) -> str:
    return json.dumps([asdict(r) for r in readings], ensure_ascii=False)
