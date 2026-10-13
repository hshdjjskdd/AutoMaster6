"""Схемы автомобилей."""

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.game_data.enums import DriveType, FuelType, Transmission

# VIN: 17 символов, латиница и цифры, без I, O, Q.
_VIN_PATTERN = re.compile(r"[A-HJ-NPR-Z0-9]{17}")


class CarConfigurationData(BaseModel):
    """Техническая конфигурация автомобиля."""

    model_config = ConfigDict(frozen=True)

    brand: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=64)
    year: int = Field(ge=1950, le=2100)
    body_type: str = Field(min_length=1, max_length=32)
    engine_code: str = Field(min_length=1, max_length=32)
    engine_volume_cc: int = Field(ge=0)
    power_hp: int = Field(gt=0)
    fuel_type: FuelType
    transmission: Transmission
    drive_type: DriveType


class CarData(BaseModel):
    """Данные для регистрации автомобиля."""

    model_config = ConfigDict(frozen=True)

    vin: str
    plate: str = Field(min_length=1, max_length=16)
    mileage_km: int = Field(ge=0)
    color: str = Field(min_length=1, max_length=32)
    condition_pct: int = Field(default=100, ge=0, le=100)

    @field_validator("vin")
    @classmethod
    def _validate_vin(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not _VIN_PATTERN.fullmatch(normalized):
            raise ValueError("VIN: 17 символов, латиница и цифры, без букв I, O, Q")
        return normalized
