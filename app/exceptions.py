"""Доменные ошибки. Тексты рассчитаны на показ игроку."""

from app.game_data.enums import OrderStatus


class DomainError(Exception):
    """Базовая ошибка игровой логики: ожидаемая, не требует traceback в логе."""


class PlayerNotFound(DomainError):
    def __init__(self, player_id: int) -> None:
        super().__init__(f"Игрок {player_id} не найден")
        self.player_id = player_id


class CarNotFound(DomainError):
    def __init__(self, car_id: int) -> None:
        super().__init__(f"Автомобиль {car_id} не найден")
        self.car_id = car_id


class CarAlreadyExists(DomainError):
    def __init__(self, vin: str) -> None:
        super().__init__(f"Автомобиль с VIN {vin} уже зарегистрирован")
        self.vin = vin


class CarBusy(DomainError):
    def __init__(self, car_id: int) -> None:
        super().__init__("Для этого автомобиля уже есть незавершённый заказ")
        self.car_id = car_id


class OrderNotFound(DomainError):
    def __init__(self, order_id: int) -> None:
        super().__init__(f"Заказ {order_id} не найден")
        self.order_id = order_id


class FaultNotFound(DomainError):
    def __init__(self, fault_id: int) -> None:
        super().__init__(f"Неисправность {fault_id} не найдена")
        self.fault_id = fault_id


class FaultAlreadyRecorded(DomainError):
    def __init__(self, code: str) -> None:
        super().__init__(f"Неисправность {code} уже внесена в этот заказ")
        self.code = code


class FaultAlreadyResolved(DomainError):
    def __init__(self, fault_id: int) -> None:
        super().__init__(f"Неисправность {fault_id} уже устранена")
        self.fault_id = fault_id


class PartNotFound(DomainError):
    def __init__(self, sku: str) -> None:
        super().__init__(f"Запчасть {sku} не найдена в каталоге")
        self.sku = sku


class EquipmentNotFound(DomainError):
    def __init__(self, code: str) -> None:
        super().__init__(f"Оборудование {code} не найдено в каталоге")
        self.code = code


class InsufficientFunds(DomainError):
    def __init__(self, required: int) -> None:
        super().__init__("Недостаточно денег для этой операции")
        self.required = required


class InsufficientStock(DomainError):
    def __init__(self, sku: str, required: int) -> None:
        super().__init__(f"На складе недостаточно деталей {sku} (нужно {required})")
        self.sku = sku
        self.required = required


class EquipmentAlreadyOwned(DomainError):
    def __init__(self, code: str) -> None:
        super().__init__("Это оборудование у тебя уже есть")
        self.code = code


class LevelTooLow(DomainError):
    def __init__(self, required: int, actual: int) -> None:
        super().__init__(f"Нужен уровень {required}, сейчас у тебя {actual}")
        self.required = required
        self.actual = actual


class InvalidStatusTransition(DomainError):
    def __init__(self, current: OrderStatus, new: OrderStatus) -> None:
        super().__init__(f"Нельзя перевести заказ из «{current.value}» в «{new.value}»")
        self.current = current
        self.new = new


class InvalidOrderState(DomainError):
    """Операция недопустима в текущем статусе заказа."""

    def __init__(self, order_id: int, status: OrderStatus) -> None:
        super().__init__(f"Эта операция недоступна для заказа в статусе «{status.value}»")
        self.order_id = order_id
        self.status = status


class OrderStateConflict(DomainError):
    """Статус заказа изменился параллельно: операцию нужно повторить."""

    def __init__(self, order_id: int) -> None:
        super().__init__("Заказ только что был изменён. Обнови данные и повтори действие.")
        self.order_id = order_id


class OrderNotReady(DomainError):
    def __init__(self, order_id: int, unresolved: int) -> None:
        super().__init__(f"Нельзя сдать заказ: не устранено неисправностей — {unresolved}")
        self.order_id = order_id
        self.unresolved = unresolved


class IdempotencyConflict(DomainError):
    """Тот же ключ операции уже использован с другими параметрами."""

    def __init__(self, key: str) -> None:
        super().__init__("Ключ операции уже использован для другой операции")
        self.key = key


class OfferNotFound(DomainError):
    def __init__(self, offer_id: int) -> None:
        super().__init__("Такого предложения нет")
        self.offer_id = offer_id


class OfferUnavailable(DomainError):
    """Предложение уже принято, отклонено или клиент не дождался."""

    def __init__(self, offer_id: int) -> None:
        super().__init__("Это предложение уже недоступно. Обнови список заказов.")
        self.offer_id = offer_id


class WorkshopFull(DomainError):
    def __init__(self, capacity: int) -> None:
        super().__init__(
            f"В мастерской нет места: одновременно можно вести заказов — {capacity}. "
            "Заверши или отмени текущий заказ."
        )
        self.capacity = capacity


class UnknownCheck(DomainError):
    def __init__(self, code: str) -> None:
        super().__init__("Такой проверки не существует")
        self.code = code


class DiagnosticsConcluded(DomainError):
    def __init__(self, order_id: int) -> None:
        super().__init__("Диагностика по этому заказу уже завершена заключением")
        self.order_id = order_id


class DiagnosticsNotStarted(DomainError):
    def __init__(self, order_id: int) -> None:
        super().__init__("Сначала выполни хотя бы одну проверку")
        self.order_id = order_id


class InvalidConclusion(DomainError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)


class DiagnosticStale(DomainError):
    """Журнал изменился после показа кнопки (например, двойное нажатие)."""

    def __init__(self, order_id: int) -> None:
        super().__init__("Журнал диагностики уже изменился. Открой меню диагностики заново.")
        self.order_id = order_id


class UnknownOperation(DomainError):
    def __init__(self, code: str) -> None:
        super().__init__("Такой ремонтной операции нет для этого заказа")
        self.code = code


class OperationAlreadyDone(DomainError):
    def __init__(self, code: str) -> None:
        super().__init__("Эта операция уже выполнена")
        self.code = code


class MissingParts(DomainError):
    """Для операции не хватает подходящих деталей на складе."""

    def __init__(self, missing: list[str]) -> None:
        super().__init__("Не хватает деталей на складе: " + ", ".join(missing))
        self.missing = missing


class NothingToVerify(DomainError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)


class UnknownPart(DomainError):
    def __init__(self, sku: str) -> None:
        super().__init__("Такой детали нет в каталоге")
        self.sku = sku


class ShopStale(DomainError):
    """Экран магазина устарел (деньги или склад изменились после показа кнопки)."""

    def __init__(self) -> None:
        super().__init__("Экран устарел. Открой магазин заново.")
