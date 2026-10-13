"""Схемы диагностики: измерения, журнал, меню проверок."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.game_data.enums import OrderStatus


class ReadingView(BaseModel):
    model_config = ConfigDict(frozen=True)

    label: str
    value: str
    unit: str = ""
    norm: str = ""
    flag: str = "info"
    note: str = ""


class CheckRunView(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_no: int
    check_code: str
    title: str
    emoji: str
    tool_title: str | None
    tool_owned: bool
    minutes: int
    cost: int
    readings: tuple[ReadingView, ...]
    interpretation: str
    created_at: datetime


class CheckOption(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    title: str
    emoji: str
    group: str
    description: str
    interpretation: str
    minutes: int
    fee: int
    tool_code: str | None
    tool_title: str | None
    tool_owned: bool
    times_done: int


class ToolOption(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    title: str
    owned: bool
    price: int
    required_level: int


class DiagnosticOverview(BaseModel):
    model_config = ConfigDict(frozen=True)

    order_id: int
    order_status: OrderStatus
    car_title: str
    plate: str
    complaint: str
    runs: int
    minutes_spent: int
    money_spent: int
    balance: int
    deadline_at: datetime | None
    concluded: bool
    can_run: bool
    options: tuple[CheckOption, ...]


class ConclusionFault(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    name: str
    system: str


class ConclusionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    order_id: int
    faults: tuple[ConclusionFault, ...]
