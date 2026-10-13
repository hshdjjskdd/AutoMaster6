"""ORM-модели SQLAlchemy.

Все модели импортируются здесь, чтобы Base.metadata знала обо всех таблицах
до вызова create_all.
"""

from app.models.base import Base
from app.models.board import OrderBoardState
from app.models.car import Car, CarConfiguration
from app.models.diagnostics import DiagnosticCheckRun, DiagnosticSession, HiddenFault
from app.models.fault import DiagnosticResult, Fault
from app.models.finance import FinancialTransaction
from app.models.history import RepairHistory
from app.models.inventory import Equipment, Part, PlayerEquipment, StockItem
from app.models.offer import ClientOffer
from app.models.order import Order, OrderPart
from app.models.player import Player
from app.models.repair import RepairOperation

__all__ = [
    "Base",
    "Car",
    "ClientOffer",
    "CarConfiguration",
    "DiagnosticCheckRun",
    "DiagnosticResult",
    "DiagnosticSession",
    "Equipment",
    "Fault",
    "FinancialTransaction",
    "HiddenFault",
    "Order",
    "OrderBoardState",
    "OrderPart",
    "Part",
    "Player",
    "PlayerEquipment",
    "RepairHistory",
    "RepairOperation",
    "StockItem",
]
