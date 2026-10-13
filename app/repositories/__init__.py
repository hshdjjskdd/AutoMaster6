"""Репозитории: доступ к данным БД."""

from app.repositories.board_repository import BoardRepository
from app.repositories.car_repository import CarRepository
from app.repositories.diagnostic_repository import DiagnosticRepository
from app.repositories.fault_repository import FaultRepository
from app.repositories.finance_repository import FinanceRepository
from app.repositories.history_repository import HistoryRepository
from app.repositories.inventory_repository import InventoryRepository
from app.repositories.offer_repository import OfferRepository
from app.repositories.order_repository import OrderRepository
from app.repositories.player_repository import PlayerRepository
from app.repositories.repair_repository import RepairRepository

__all__ = [
    "BoardRepository",
    "CarRepository",
    "DiagnosticRepository",
    "FaultRepository",
    "FinanceRepository",
    "HistoryRepository",
    "InventoryRepository",
    "OfferRepository",
    "OrderRepository",
    "PlayerRepository",
    "RepairRepository",
]
