"""Репозиторий неисправностей и результатов диагностики."""

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.game_data.enums import DiagnosticOutcome, FaultSeverity
from app.models import DiagnosticResult, Fault
from app.models.types import utc_now


class FaultRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_fault(
        self,
        *,
        order_id: int,
        car_id: int,
        code: str,
        name: str,
        system: str,
        severity: FaultSeverity,
    ) -> Fault:
        """Добавляет неисправность. IntegrityError, если код уже внесён в этот заказ."""
        fault = Fault(
            order_id=order_id,
            car_id=car_id,
            code=code,
            name=name,
            system=system,
            severity=severity,
        )
        self._session.add(fault)
        await self._session.flush()
        return fault

    async def list_for_order(self, order_id: int) -> list[Fault]:
        result = await self._session.execute(
            select(Fault)
            .where(Fault.order_id == order_id)
            .order_by(Fault.id)
            .execution_options(populate_existing=True)
        )
        return list(result.scalars())

    async def get(self, order_id: int, fault_id: int) -> Fault | None:
        result = await self._session.execute(
            select(Fault)
            .where(Fault.id == fault_id, Fault.order_id == order_id)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def count_unresolved(self, order_id: int) -> int:
        count = await self._session.scalar(
            select(func.count(Fault.id)).where(
                Fault.order_id == order_id, Fault.is_resolved.is_(False)
            )
        )
        return int(count or 0)

    async def resolve(self, *, order_id: int, fault_id: int) -> bool:
        """Отмечает неисправность устранённой. False, если её нет или она уже устранена."""
        result = await self._session.execute(
            update(Fault)
            .where(
                Fault.id == fault_id,
                Fault.order_id == order_id,
                Fault.is_resolved.is_(False),
            )
            .values(is_resolved=True, resolved_at=utc_now())
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1

    async def add_diagnostic(
        self,
        *,
        order_id: int,
        check_name: str,
        outcome: DiagnosticOutcome,
        findings: str,
        duration_minutes: int,
        fault_id: int | None,
        equipment_id: int | None,
    ) -> DiagnosticResult:
        result = DiagnosticResult(
            order_id=order_id,
            check_name=check_name,
            outcome=outcome,
            findings=findings,
            duration_minutes=duration_minutes,
            fault_id=fault_id,
            equipment_id=equipment_id,
        )
        self._session.add(result)
        await self._session.flush()
        return result

    async def list_diagnostics(self, order_id: int) -> list[DiagnosticResult]:
        result = await self._session.execute(
            select(DiagnosticResult)
            .where(DiagnosticResult.order_id == order_id)
            .order_by(DiagnosticResult.id)
            .execution_options(populate_existing=True)
        )
        return list(result.scalars())
