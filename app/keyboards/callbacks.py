"""Данные callback-кнопок диагностики."""

from aiogram.filters.callback_data import CallbackData


class DiagCb(CallbackData, prefix="dg"):
    # menu | info | run | journal | entry | concl | tog | concl_ok | tools | buy
    action: str
    order_id: int = 0
    arg: str = ""
    n: int = 0


class ShopCb(CallbackData, prefix="shp", sep="|"):
    # home | sec | type | buy | stock | plan | orders
    action: str
    a: str = ""  # индекс раздела или код типа детали
    order: int = 0  # заказ, под автомобиль которого подбираются детали
    q: int = 0  # качество 1..3
    n: int = 0  # количество
    ver: int = 0  # номер последней записи журнала на момент показа экрана


class RepairCb(CallbackData, prefix="rpr"):
    # open | do | verify | finish
    action: str
    order_id: int = 0
    arg: str = ""
