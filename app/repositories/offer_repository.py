"""Репозиторий предложений клиентов. Все выборки ограничены игроком."""

from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.game_data.enums import OfferStatus
from app.models import ClientOffer


class OfferRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, *, player_id: int, configuration_id: int, draft_fields: dict[str, object]) -> ClientOffer:
        offer = ClientOffer(player_id=player_id, configuration_id=configuration_id, **draft_fields)
        self._session.add(offer)
        await self._session.flush()
        return offer

    async def expire_stale(self, player_id: int, now: datetime) -> int:
        """AVAILABLE с истёкшим сроком -> EXPIRED. Первый write в транзакции."""
        result = await self._session.execute(
            update(ClientOffer)
            .where(
                ClientOffer.player_id == player_id,
                ClientOffer.status == OfferStatus.AVAILABLE,
                ClientOffer.expires_at <= now,
            )
            .values(status=OfferStatus.EXPIRED, resolved_at=now)
            .execution_options(synchronize_session=False)
        )
        return result.rowcount or 0

    async def count_available(self, player_id: int) -> int:
        total = await self._session.scalar(
            select(func.count())
            .select_from(ClientOffer)
            .where(ClientOffer.player_id == player_id, ClientOffer.status == OfferStatus.AVAILABLE)
        )
        return int(total or 0)

    async def list_available(self, player_id: int) -> list[ClientOffer]:
        result = await self._session.execute(
            select(ClientOffer)
            .where(ClientOffer.player_id == player_id, ClientOffer.status == OfferStatus.AVAILABLE)
            .options(selectinload(ClientOffer.configuration))
            .order_by(ClientOffer.id)
            .execution_options(populate_existing=True)
        )
        return list(result.scalars())

    async def get(self, player_id: int, offer_id: int) -> ClientOffer | None:
        result = await self._session.execute(
            select(ClientOffer)
            .where(ClientOffer.id == offer_id, ClientOffer.player_id == player_id)
            .options(selectinload(ClientOffer.configuration))
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def get_by_order(self, player_id: int, order_id: int) -> ClientOffer | None:
        result = await self._session.execute(
            select(ClientOffer)
            .where(ClientOffer.order_id == order_id, ClientOffer.player_id == player_id)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def resolve_if_available(
        self, *, player_id: int, offer_id: int, new: OfferStatus, now: datetime
    ) -> bool:
        """AVAILABLE и не истёк -> new (compare-and-swap). True — переход выполнен."""
        result = await self._session.execute(
            update(ClientOffer)
            .where(
                ClientOffer.id == offer_id,
                ClientOffer.player_id == player_id,
                ClientOffer.status == OfferStatus.AVAILABLE,
                ClientOffer.expires_at > now,
            )
            .values(status=new, resolved_at=now)
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1

    async def link_order(self, *, offer_id: int, order_id: int) -> None:
        await self._session.execute(
            update(ClientOffer)
            .where(ClientOffer.id == offer_id)
            .values(order_id=order_id)
            .execution_options(synchronize_session=False)
        )
