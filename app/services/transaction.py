"""Граница транзакции для операций сервисов."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession


@asynccontextmanager
async def atomic(session: AsyncSession) -> AsyncIterator[None]:
    """Выполняет блок как одну транзакцию.

    Успех — commit. Любое исключение (в том числе доменное, например
    InsufficientFunds) — rollback всех изменений блока, и исключение пробрасывается
    дальше. Так деньги, склад и статус заказа никогда не остаются в разном состоянии.
    """
    try:
        yield
        await session.commit()
    except BaseException:
        await session.rollback()
        raise
