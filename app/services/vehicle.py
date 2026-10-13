"""Общие вычисления по автомобилю заказа."""

from app.game_data.fleet import tags_for_configuration
from app.models import CarConfiguration


def configuration_tags(config: CarConfiguration) -> dict[str, object]:
    """Теги совместимости автомобиля: от них зависят детали, проверки и неисправности."""
    return tags_for_configuration(
        config.brand, config.model, config.engine_code, config.transmission, config.engine_volume_cc
    )
