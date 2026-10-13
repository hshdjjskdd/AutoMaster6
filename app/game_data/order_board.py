"""Расписание и случайность обновления доски заказов (чистая логика, без БД)."""

import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.game_data.economy import (
    BOARD_SIZE,
    EASY,
    INITIAL_OFFERS,
    MAX_CATCHUP_REFRESHES,
    MEDIUM,
    PITY_GUARANTEE_AFTER,
    PITY_MAX_CHANCE,
    PITY_STEP,
    REFRESH_INTERVAL_HOURS,
    TIER_SPAWN_CHANCE,
    TIERS,
)


def spawn_chance(tier: int, empty_streak: int) -> float:
    """Вероятность появления заказа сложности tier при данной серии пустых обновлений."""
    base = TIER_SPAWN_CHANCE[tier]
    if empty_streak <= 0:
        return base
    return min(PITY_MAX_CHANCE, max(base, base + PITY_STEP * empty_streak))


def roll_tiers(rng: random.Random, empty_streak: int) -> list[int]:
    """Одно обновление: каждая сложность выпадает независимо от остальных.

    Если пустых обновлений подряд набралось PITY_GUARANTEE_AFTER и больше, а бросок снова
    ничего не дал, выдаётся лёгкий заказ — игрок не остаётся без работы.
    """
    tiers = [t for t in TIERS if rng.random() < spawn_chance(t, empty_streak)]
    if not tiers and empty_streak >= PITY_GUARANTEE_AFTER:
        tiers = [EASY]
    return tiers


def initial_tiers(rng: random.Random) -> list[int]:
    """Стартовая доска: обычный бросок, обязательно есть лёгкий, всего не меньше INITIAL_OFFERS."""
    tiers = roll_tiers(rng, 0)
    if EASY not in tiers:
        tiers.append(EASY)
    while len(tiers) < INITIAL_OFFERS:
        tiers.append(rng.choices((EASY, MEDIUM), (70, 30))[0])
    return sorted(tiers)[:BOARD_SIZE]


def missed_rounds(last_refresh_at: datetime | None, now: datetime) -> int:
    """Сколько обновлений пропущено, пока бот не работал (не больше MAX_CATCHUP_REFRESHES − 1)."""
    if last_refresh_at is None:
        return 0
    periods = int((now - last_refresh_at) / timedelta(hours=REFRESH_INTERVAL_HOURS))
    return max(0, min(periods - 1, MAX_CATCHUP_REFRESHES - 1))


@dataclass(frozen=True, slots=True)
class RefreshOutcome:
    tiers: tuple[int, ...]  # какие заказы создать (по одному на элемент)
    empty_streak: int  # новая серия пустых обновлений


def plan_refresh(
    rng: random.Random,
    *,
    empty_streak: int,
    free_slots: int,
    rounds: int = 1,
    initial: bool = False,
) -> RefreshOutcome:
    """Решает, какие заказы появятся при обновлении.

    Если доска заполнена, обновление ничего не создаёт и серию пустых обновлений не
    увеличивает: игрок не «без заказов», у него их просто достаточно.
    """
    created: list[int] = []
    streak = empty_streak
    free = free_slots
    if initial:
        created = initial_tiers(rng)[: max(0, free)]
        return RefreshOutcome(tuple(created), 0)
    for _ in range(max(1, rounds)):
        if free <= 0:
            break
        got = roll_tiers(rng, streak)[:free]
        created += got
        free -= len(got)
        streak = 0 if got else streak + 1
    return RefreshOutcome(tuple(created), streak)


def next_refresh_time(now: datetime) -> datetime:
    return now + timedelta(hours=REFRESH_INTERVAL_HOURS)


def format_countdown(next_at: datetime, now: datetime) -> str:
    """«1 ч 24 мин», «12 мин», «меньше минуты»."""
    seconds = int((next_at - now).total_seconds())
    if seconds <= 0:
        return "сейчас"
    minutes = (seconds + 59) // 60
    hours, mins = divmod(minutes, 60)
    if hours:
        return f"{hours} ч {mins:02d} мин" if mins else f"{hours} ч"
    return f"{mins} мин"
