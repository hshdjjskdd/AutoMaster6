"""Конфигурация приложения: загрузка и валидация переменных окружения."""

from __future__ import annotations

import os
import re
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, SecretStr, ValidationError, field_validator

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"
DEFAULT_DATABASE_PATH = BASE_DIR / "data" / "auto_master.db"

_TOKEN_PATTERN = re.compile(r"\d{3,}:[A-Za-z0-9_-]{20,}")
_LOG_LEVELS = frozenset({"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"})


class ConfigError(Exception):
    """Ошибка конфигурации. Текст рассчитан на показ пользователю."""


class Settings(BaseModel):
    """Проверенные настройки приложения."""

    model_config = ConfigDict(frozen=True)

    bot_token: SecretStr
    database_url: str
    log_level: str = "INFO"
    sql_echo: bool = False

    @field_validator("bot_token")
    @classmethod
    def _validate_bot_token(cls, value: SecretStr) -> SecretStr:
        if not _TOKEN_PATTERN.fullmatch(value.get_secret_value()):
            raise ValueError("неверный формат токена, ожидается вид 123456789:AAH...")
        return value

    @field_validator("database_url")
    @classmethod
    def _validate_database_url(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("строка подключения не может быть пустой")
        return value

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in _LOG_LEVELS:
            allowed = ", ".join(sorted(_LOG_LEVELS))
            raise ValueError(f"допустимые значения: {allowed}")
        return normalized


def load_settings() -> Settings:
    """Читает .env и переменные окружения, возвращает проверенные настройки.

    Переменные окружения имеют приоритет над значениями из .env.
    """
    load_dotenv(ENV_FILE)

    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise ConfigError(
            "Переменная BOT_TOKEN не задана. Скопируйте .env.example в .env "
            "и впишите токен, полученный у @BotFather."
        )

    database_url = (
        os.getenv("DATABASE_URL", "").strip()
        or f"sqlite+aiosqlite:///{DEFAULT_DATABASE_PATH.as_posix()}"
    )

    try:
        return Settings(
            bot_token=token,
            database_url=database_url,
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            sql_echo=os.getenv("SQL_ECHO", "false"),
        )
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']).upper()}: {error['msg']}"
            for error in exc.errors()
        )
        raise ConfigError(f"Некорректная конфигурация — {details}") from exc
