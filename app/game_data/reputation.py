"""Ступени репутации мастерской."""

from dataclasses import dataclass

from app.game_data.constants import MAX_REPUTATION, MIN_REPUTATION


@dataclass(frozen=True, slots=True)
class ReputationTier:
    """Ступень репутации: нижняя граница (включительно) и название."""

    min_value: int
    title: str


REPUTATION_TIERS: tuple[ReputationTier, ...] = (
    ReputationTier(min_value=0, title="Дурная слава"),
    ReputationTier(min_value=20, title="Спорная"),
    ReputationTier(min_value=40, title="Нейтральная"),
    ReputationTier(min_value=60, title="Хорошая"),
    ReputationTier(min_value=80, title="Отличная"),
)


def get_reputation_title(value: int) -> str:
    """Возвращает название ступени для значения репутации."""
    clamped = max(MIN_REPUTATION, min(value, MAX_REPUTATION))
    for tier in reversed(REPUTATION_TIERS):
        if clamped >= tier.min_value:
            return tier.title
    return REPUTATION_TIERS[0].title
