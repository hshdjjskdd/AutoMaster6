"""Схемы данных игрока."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TelegramUserData(BaseModel):
    """Данные Telegram-пользователя, нужные для регистрации."""

    model_config = ConfigDict(frozen=True)

    telegram_id: int
    username: str | None = None
    first_name: str | None = None


class PlayerProfile(BaseModel):
    """Готовые к показу данные профиля игрока."""

    model_config = ConfigDict(frozen=True)

    telegram_id: int
    display_name: str
    username: str | None
    money: int
    level: int
    level_title: str
    experience: int
    experience_for_next_level: int | None
    reputation: int
    reputation_max: int
    reputation_title: str
    registered_at: datetime


class RegistrationResult(BaseModel):
    """Итог обращения к /start: профиль и признак новой регистрации."""

    model_config = ConfigDict(frozen=True)

    profile: PlayerProfile
    is_new: bool
