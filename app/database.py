"""Подключение к БД: движок SQLAlchemy, фабрика сессий и создание таблиц."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import Settings
from app.models import Base

logger = logging.getLogger(__name__)

# Версия схемы БД, записывается в PRAGMA user_version. Увеличивайте при изменении
# таблиц вместе с миграцией: create_all не изменяет уже существующие таблицы.
#   1 — этап 1: таблица players
#   2 — этап 2: автомобили, заказы, склад, оборудование, финансы, история
#   3 — этап 3: предложения клиентов (client_offers)
#   4 — этап 4: диагностика (diagnostic_sessions, hidden_faults, diagnostic_check_runs)
#   5 — этап 5: ремонт (repair_operations). Запчасти динамического каталога пишутся в уже
#       существующую таблицу parts по мере показа/покупки; существующие колонки и данные
#       не меняются, поэтому достаточно create_all для новой таблицы и повышения версии.
#   6 — этап 6: динамическая доска (order_board_state) и три новые колонки client_offers
#       (tier, planned_faults, est_cost), добавляются ALTER TABLE с DEFAULT: старые
#       предложения и игроки остаются как были.
SCHEMA_VERSION = 6


class DatabaseVersionError(RuntimeError):
    """База создана более новой версией приложения."""


# Последняя линия защиты денег на уровне БД. CHECK нельзя добавить к уже существующей
# таблице SQLite без её пересоздания, поэтому используются триггеры: они одинаково
# работают и в новых базах, и в базах, созданных на этапе 1.
_MONEY_GUARD_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TRIGGER IF NOT EXISTS trg_players_money_nonneg_insert
    BEFORE INSERT ON players
    WHEN NEW.money < 0
    BEGIN
        SELECT RAISE(ABORT, 'players.money must be >= 0');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_players_money_nonneg_update
    BEFORE UPDATE OF money ON players
    WHEN NEW.money < 0
    BEGIN
        SELECT RAISE(ABORT, 'players.money must be >= 0');
    END
    """,
)


# Колонки, добавленные к уже существующим таблицам после этапа 1 (create_all их не создаёт).
_ADDED_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("client_offers", "tier", "INTEGER NOT NULL DEFAULT 1"),
    ("client_offers", "planned_faults", "TEXT NOT NULL DEFAULT ''"),
    ("client_offers", "est_cost", "INTEGER NOT NULL DEFAULT 0"),
)


def _add_missing_columns(sync_connection: Any) -> None:
    """Добавляет недостающие колонки в существующие таблицы (идемпотентно)."""
    for table, column, ddl in _ADDED_COLUMNS:
        rows = sync_connection.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
        if rows and column not in {row[1] for row in rows}:
            sync_connection.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
            logger.info("Добавлена колонка %s.%s", table, column)


def _ensure_sqlite_directory(database_url: str) -> None:
    """Создаёт папку для файла SQLite, если её ещё нет."""
    url = make_url(database_url)
    if not url.drivername.startswith("sqlite"):
        return
    if not url.database or url.database == ":memory:":
        return
    Path(url.database).parent.mkdir(parents=True, exist_ok=True)


def _configure_sqlite(engine: AsyncEngine) -> None:
    """Включает внешние ключи, WAL и таймаут блокировки для каждого соединения."""

    @event.listens_for(engine.sync_engine, "connect")
    def _on_connect(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA journal_mode=WAL")
        finally:
            cursor.close()


def create_engine(settings: Settings) -> AsyncEngine:
    """Создаёт асинхронный движок SQLAlchemy."""
    _ensure_sqlite_directory(settings.database_url)
    engine = create_async_engine(settings.database_url, echo=settings.sql_echo)
    if engine.dialect.name == "sqlite":
        _configure_sqlite(engine)
    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Создаёт фабрику сессий. Объекты не «протухают» после commit."""
    return async_sessionmaker(engine, expire_on_commit=False)


async def init_db(engine: AsyncEngine) -> None:
    """Создаёт недостающие таблицы, проверяет версию схемы и загружает каталог.

    Безопасно вызывать при каждом запуске: существующие данные не затрагиваются.
    База этапа 1 (только таблица players) дополняется новыми таблицами автоматически.
    """
    is_sqlite = engine.dialect.name == "sqlite"
    async with engine.begin() as connection:
        current_version = 0
        if is_sqlite:
            result = await connection.exec_driver_sql("PRAGMA user_version")
            current_version = int(result.scalar_one())
            if current_version > SCHEMA_VERSION:
                raise DatabaseVersionError(
                    f"База данных имеет версию схемы {current_version}, а это приложение "
                    f"поддерживает версии до {SCHEMA_VERSION}. Обновите приложение."
                )
        await connection.run_sync(Base.metadata.create_all)
        if is_sqlite:
            await connection.run_sync(_add_missing_columns)
        if is_sqlite:
            for statement in _MONEY_GUARD_STATEMENTS:
                await connection.exec_driver_sql(statement)
        if is_sqlite and current_version < SCHEMA_VERSION:
            await connection.exec_driver_sql(f"PRAGMA user_version = {SCHEMA_VERSION}")
            logger.info("Схема БД обновлена: версия %s -> %s", current_version, SCHEMA_VERSION)

    # Импорт здесь, чтобы слой БД не зависел от сервисов на уровне модуля.
    from app.services.catalog_service import seed_catalog

    async with create_session_factory(engine)() as session:
        await seed_catalog(session)
    logger.info("База данных готова")
