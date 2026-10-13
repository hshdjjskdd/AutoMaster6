"""Таблица уровней игрока."""

from dataclasses import dataclass

from app.game_data.constants import START_LEVEL


@dataclass(frozen=True, slots=True)
class LevelInfo:
    """Описание уровня: номер, звание и опыт, нужный для достижения."""

    level: int
    title: str
    experience_required: int


LEVELS: tuple[LevelInfo, ...] = (
    LevelInfo(level=1, title="Подмастерье", experience_required=0),
    LevelInfo(level=2, title="Автослесарь", experience_required=100),
    LevelInfo(level=3, title="Механик", experience_required=250),
    LevelInfo(level=4, title="Опытный механик", experience_required=500),
    LevelInfo(level=5, title="Мастер", experience_required=900),
    LevelInfo(level=6, title="Старший мастер", experience_required=1_400),
    LevelInfo(level=7, title="Главный механик", experience_required=2_100),
    LevelInfo(level=8, title="Эксперт", experience_required=3_000),
    LevelInfo(level=9, title="Легенда района", experience_required=4_200),
    LevelInfo(level=10, title="Король автосервиса", experience_required=6_000),
)

MAX_LEVEL = LEVELS[-1].level

_LEVELS_BY_NUMBER: dict[int, LevelInfo] = {info.level: info for info in LEVELS}


def get_level_info(level: int) -> LevelInfo:
    """Возвращает описание уровня; номер за пределами таблицы приводится к границе."""
    clamped = max(START_LEVEL, min(level, MAX_LEVEL))
    return _LEVELS_BY_NUMBER[clamped]


def level_for_experience(experience: int) -> int:
    """Возвращает уровень, который соответствует накопленному опыту."""
    reached = START_LEVEL
    for info in LEVELS:
        if experience >= info.experience_required:
            reached = info.level
    return reached


def get_next_level_info(level: int) -> LevelInfo | None:
    """Возвращает следующий уровень или None, если достигнут максимальный."""
    if level >= MAX_LEVEL:
        return None
    return _LEVELS_BY_NUMBER[max(START_LEVEL, level) + 1]
