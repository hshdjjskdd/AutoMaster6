"""Сервисы: игровая логика."""

from app.services.catalog_service import seed_catalog
from app.services.client_order_service import ClientOrderService
from app.services.diagnostic_service import DiagnosticService
from app.services.economy_service import EconomyService
from app.services.finance_service import FinanceService
from app.services.garage_service import GarageService
from app.services.inventory_service import InventoryService
from app.services.order_service import OrderService
from app.services.player_service import PlayerService
from app.services.progress_service import ProgressService
from app.services.repair_service import RepairService
from app.services.shop_service import ShopService

__all__ = [
    "ClientOrderService",
    "DiagnosticService",
    "EconomyService",
    "FinanceService",
    "GarageService",
    "InventoryService",
    "OrderService",
    "PlayerService",
    "ProgressService",
    "RepairService",
    "ShopService",
    "seed_catalog",
]
