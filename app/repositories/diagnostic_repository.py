"""Репозиторий диагностики. Все операции привязаны к заказу, проверенному сервисом."""

from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DiagnosticCheckRun, DiagnosticSession, HiddenFault


class DiagnosticRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- сессия -------------------------------------------------------------

    async def create_session_if_missing(self, *, order_id: int, player_id: int) -> bool:
        """True, если сессия создана этим вызовом (то есть правда о поломке ещё не определена)."""
        result = await self._session.execute(
            sqlite_insert(DiagnosticSession)
            .values(order_id=order_id, player_id=player_id, minutes_spent=0, money_spent=0)
            .on_conflict_do_nothing(index_elements=["order_id"])
        )
        return result.rowcount == 1

    async def get_session(self, order_id: int) -> DiagnosticSession | None:
        result = await self._session.execute(
            select(DiagnosticSession)
            .where(DiagnosticSession.order_id == order_id)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def add_spent(self, *, order_id: int, minutes: int, money: int) -> bool:
        """Прибавляет время и деньги, пока заключение не вынесено."""
        result = await self._session.execute(
            update(DiagnosticSession)
            .where(DiagnosticSession.order_id == order_id, DiagnosticSession.concluded_at.is_(None))
            .values(
                minutes_spent=DiagnosticSession.minutes_spent + minutes,
                money_spent=DiagnosticSession.money_spent + money,
            )
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1

    async def conclude(self, *, order_id: int, now: datetime) -> bool:
        """Фиксирует заключение (один раз). False — уже вынесено."""
        result = await self._session.execute(
            update(DiagnosticSession)
            .where(DiagnosticSession.order_id == order_id, DiagnosticSession.concluded_at.is_(None))
            .values(concluded_at=now)
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1

    async def reopen(self, *, order_id: int) -> bool:
        """Снимает заключение: после неудачной проверки ремонта диагностику можно продолжить."""
        result = await self._session.execute(
            update(DiagnosticSession)
            .where(
                DiagnosticSession.order_id == order_id,
                DiagnosticSession.concluded_at.is_not(None),
            )
            .values(concluded_at=None)
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1

    # --- скрытая правда ------------------------------------------------------

    async def add_hidden(self, *, order_id: int, cause_code: str, detail: str) -> None:
        await self._session.execute(
            sqlite_insert(HiddenFault)
            .values(order_id=order_id, cause_code=cause_code, detail=detail)
            .on_conflict_do_nothing(index_elements=["order_id", "cause_code"])
        )

    async def list_hidden(self, order_id: int) -> dict[str, str]:
        result = await self._session.execute(
            select(HiddenFault).where(HiddenFault.order_id == order_id).order_by(HiddenFault.id)
        )
        return {row.cause_code: row.detail for row in result.scalars()}

    # --- журнал ---------------------------------------------------------------

    async def last_run_no(self, order_id: int) -> int:
        value = await self._session.scalar(
            select(func.coalesce(func.max(DiagnosticCheckRun.run_no), 0)).where(
                DiagnosticCheckRun.order_id == order_id
            )
        )
        return int(value or 0)

    async def add_run(
        self,
        *,
        order_id: int,
        player_id: int,
        run_no: int,
        check_code: str,
        tool_code: str | None,
        tool_owned: bool,
        minutes: int,
        cost: int,
        readings_json: str,
        interpretation: str,
    ) -> DiagnosticCheckRun:
        run = DiagnosticCheckRun(
            order_id=order_id,
            player_id=player_id,
            run_no=run_no,
            check_code=check_code,
            tool_code=tool_code,
            tool_owned=tool_owned,
            minutes=minutes,
            cost=cost,
            readings_json=readings_json,
            interpretation=interpretation,
        )
        self._session.add(run)
        await self._session.flush()
        return run

    async def list_runs(self, order_id: int) -> list[DiagnosticCheckRun]:
        result = await self._session.execute(
            select(DiagnosticCheckRun)
            .where(DiagnosticCheckRun.order_id == order_id)
            .order_by(DiagnosticCheckRun.run_no)
            .execution_options(populate_existing=True)
        )
        return list(result.scalars())

    async def get_run(self, order_id: int, run_no: int) -> DiagnosticCheckRun | None:
        result = await self._session.execute(
            select(DiagnosticCheckRun)
            .where(DiagnosticCheckRun.order_id == order_id, DiagnosticCheckRun.run_no == run_no)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def count_by_check(self, order_id: int) -> dict[str, int]:
        result = await self._session.execute(
            select(DiagnosticCheckRun.check_code, func.count())
            .where(DiagnosticCheckRun.order_id == order_id)
            .group_by(DiagnosticCheckRun.check_code)
        )
        return {code: int(count) for code, count in result.all()}
