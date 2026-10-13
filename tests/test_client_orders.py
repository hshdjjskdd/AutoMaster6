"""Тесты клиентских заказов: доска, принятие, мастерская, отмена, изоляция игроков."""

import asyncio
import random
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.exceptions import (
    InvalidOrderState,
    OfferNotFound,
    OfferUnavailable,
    OrderNotFound,
    WorkshopFull,
)
from app.game_data.economy import BOARD_SIZE, INITIAL_OFFERS, OFFER_LIFETIME_HOURS
from app.game_data.enums import OfferStatus, OrderStatus
from app.services import ClientOrderService, OrderService
from tests.base import DatabaseTestCase


class ClientOrderTests(DatabaseTestCase):
    async def board(self, player_id: int, seed: int = 1, now: datetime | None = None):  # type: ignore[no-untyped-def]
        async with self.factory() as session:
            return await ClientOrderService(session, random.Random(seed)).get_board(
                player_id, now=now
            )

    async def accept(self, player_id: int, offer_id: int):  # type: ignore[no-untyped-def]
        async with self.factory() as session:
            return await ClientOrderService(session).accept_offer(player_id, offer_id)

    async def workshop(self, player_id: int):  # type: ignore[no-untyped-def]
        async with self.factory() as session:
            return await ClientOrderService(session).list_workshop(player_id)

    # --- доска ---------------------------------------------------------

    async def test_board_has_full_cards(self) -> None:
        pid = await self.make_player()
        board = await self.board(pid)
        self.assertGreaterEqual(len(board.offers), INITIAL_OFFERS)
        self.assertLessEqual(len(board.offers), BOARD_SIZE)
        self.assertEqual(board.capacity, 1)
        self.assertIsNotNone(board.next_refresh_at)
        for offer in board.offers:
            self.assertEqual(offer.status, OfferStatus.AVAILABLE)
            self.assertTrue(offer.customer_name)
            self.assertTrue(offer.complaint)
            self.assertTrue(offer.symptoms)
            self.assertGreater(offer.payment, 0)
            self.assertGreater(offer.potential_bonus, 0)
            car = offer.car
            self.assertTrue(car.brand and car.model and car.engine_code and car.trim_name)
            self.assertGreaterEqual(car.mileage_km, 0)

    async def test_board_stable_and_persistent(self) -> None:
        pid = await self.make_player()
        first = await self.board(pid, seed=1)
        second = await self.board(pid, seed=2)  # доска уже полна — новые не создаются
        self.assertEqual([o.offer_id for o in first.offers], [o.offer_id for o in second.offers])
        await self.restart()
        third = await self.board(pid, seed=3)
        self.assertEqual([o.offer_id for o in first.offers], [o.offer_id for o in third.offers])

    async def test_decline_does_not_refill_before_refresh_and_keeps_reputation(self) -> None:
        pid = await self.make_player()
        board = await self.board(pid)
        victim = board.offers[0].offer_id
        async with self.factory() as session:
            await ClientOrderService(session).decline_offer(pid, victim)
        again = await self.board(pid, seed=9)
        self.assertEqual(len(again.offers), len(board.offers) - 1)
        self.assertNotIn(victim, [o.offer_id for o in again.offers])
        self.assertEqual(await self.scalar("SELECT reputation FROM players WHERE id=:i", i=pid), 50)
        with self.assertRaises(OfferUnavailable):
            async with self.factory() as session:
                await ClientOrderService(session).decline_offer(pid, victim)

    async def test_expired_offers_replaced(self) -> None:
        pid = await self.make_player()
        board = await self.board(pid)
        later = datetime.now(UTC) + timedelta(hours=OFFER_LIFETIME_HOURS + 1)
        fresh = await self.board(pid, seed=5, now=later)
        old_ids = {o.offer_id for o in board.offers}
        self.assertTrue(old_ids.isdisjoint(o.offer_id for o in fresh.offers))
        expired = await self.scalar(
            "SELECT COUNT(*) FROM client_offers WHERE player_id=:i AND status='expired'", i=pid
        )
        self.assertEqual(expired, len(board.offers))

    # --- принятие и мастерская -------------------------------------------

    async def test_accept_puts_car_in_workshop(self) -> None:
        pid = await self.make_player()
        board = await self.board(pid)
        offer = board.offers[0]
        result = await self.accept(pid, offer.offer_id)

        orders = await self.workshop(pid)
        self.assertEqual([o.order_id for o in orders], [result.order_id])
        card = orders[0]
        self.assertEqual(card.status, OrderStatus.NEW)
        self.assertEqual(card.reward, offer.payment)
        self.assertEqual(card.complaint, offer.complaint)
        self.assertEqual(card.symptoms, offer.symptoms)
        self.assertEqual(card.customer_name, offer.customer_name)
        self.assertEqual(card.car.vin, offer.car.vin)
        self.assertEqual(card.car.model, offer.car.model)
        self.assertEqual(card.car.engine_code, offer.car.engine_code)
        self.assertEqual(card.car.mileage_km, offer.car.mileage_km)
        self.assertEqual(card.car.trim_name, offer.car.trim_name)
        self.assertEqual(card.cancel_penalty, 0)
        self.assertIsNotNone(card.deadline_at)

        async with self.factory() as session:
            same = await ClientOrderService(session).get_workshop_order(pid, result.order_id)
        self.assertEqual(same, card)
        cars = await self.scalar("SELECT COUNT(*) FROM cars WHERE player_id=:i", i=pid)
        self.assertEqual(cars, 1)
        status = await self.scalar(
            "SELECT status FROM client_offers WHERE id=:i", i=offer.offer_id
        )
        self.assertEqual(status, "accepted")

    async def test_order_survives_restart_and_is_normal_order(self) -> None:
        pid = await self.make_player()
        offer = (await self.board(pid)).offers[0]
        result = await self.accept(pid, offer.offer_id)
        await self.restart()
        orders = await self.workshop(pid)
        self.assertEqual(len(orders), 1)
        async with self.factory() as session:
            order = await OrderService(session).get_order(pid, result.order_id)
        self.assertEqual(order.status, OrderStatus.NEW)
        self.assertEqual(order.reward, offer.payment)

    async def test_accept_twice_fails(self) -> None:
        pid = await self.make_player()
        offer = (await self.board(pid)).offers[0]
        await self.accept(pid, offer.offer_id)
        with self.assertRaises(OfferUnavailable):
            await self.accept(pid, offer.offer_id)
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM orders"), 1)

    async def test_concurrent_accept_creates_one_order(self) -> None:
        pid = await self.make_player()
        offer = (await self.board(pid)).offers[0]
        results = await asyncio.gather(
            *(self.accept(pid, offer.offer_id) for _ in range(5)), return_exceptions=True
        )
        ok = [r for r in results if not isinstance(r, BaseException)]
        self.assertEqual(len(ok), 1, results)
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM orders"), 1)
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM cars"), 1)

    async def test_workshop_capacity_limits_and_rolls_back(self) -> None:
        pid = await self.make_player()  # уровень 1: одно место
        offers = (await self.board(pid)).offers
        await self.accept(pid, offers[0].offer_id)
        with self.assertRaises(WorkshopFull):
            await self.accept(pid, offers[1].offer_id)
        # неудачная попытка не «съела» предложение и не создала машину
        status = await self.scalar(
            "SELECT status FROM client_offers WHERE id=:i", i=offers[1].offer_id
        )
        self.assertEqual(status, "available")
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM cars"), 1)

    async def test_higher_level_has_more_slots(self) -> None:
        pid = await self.make_player()
        async with self.factory() as session:
            await session.execute(text("UPDATE players SET level=3 WHERE id=:i"), {"i": pid})
            await session.commit()
        offers = (await self.board(pid)).offers
        await self.accept(pid, offers[0].offer_id)
        await self.accept(pid, offers[1].offer_id)
        with self.assertRaises(WorkshopFull):
            await self.accept(pid, offers[2].offer_id)

    async def test_expired_offer_cannot_be_accepted(self) -> None:
        pid = await self.make_player()
        offer = (await self.board(pid)).offers[0]
        async with self.factory() as session:
            await session.execute(
                text("UPDATE client_offers SET expires_at='2000-01-01 00:00:00' WHERE id=:i"),
                {"i": offer.offer_id},
            )
            await session.commit()
        with self.assertRaises(OfferUnavailable):
            await self.accept(pid, offer.offer_id)

    # --- изоляция игроков -----------------------------------------------

    async def test_players_see_only_own_data(self) -> None:
        a = await self.make_player(1)
        b = await self.make_player(2)
        board_a = await self.board(a, seed=1)
        board_b = await self.board(b, seed=2)
        ids_a = {o.offer_id for o in board_a.offers}
        ids_b = {o.offer_id for o in board_b.offers}
        self.assertTrue(ids_a.isdisjoint(ids_b))

        foreign = next(iter(ids_a))
        with self.assertRaises(OfferNotFound):
            await self.accept(b, foreign)
        async with self.factory() as session:
            with self.assertRaises(OfferNotFound):
                await ClientOrderService(session).get_offer(b, foreign)
            with self.assertRaises(OfferNotFound):
                await ClientOrderService(session).decline_offer(b, foreign)

        result = await self.accept(a, board_a.offers[0].offer_id)
        self.assertEqual(await self.workshop(b), [])
        async with self.factory() as session:
            with self.assertRaises(OrderNotFound):
                await ClientOrderService(session).get_workshop_order(b, result.order_id)
            with self.assertRaises(OrderNotFound):
                await ClientOrderService(session).cancel_order(b, result.order_id)
        self.assertEqual(len(await self.workshop(a)), 1)

    # --- отмена ---------------------------------------------------------

    async def accepted_order(self, pid: int) -> int:
        offer = (await self.board(pid)).offers[0]
        return (await self.accept(pid, offer.offer_id)).order_id

    async def cancel(self, pid: int, order_id: int):  # type: ignore[no-untyped-def]
        async with self.factory() as session:
            return await ClientOrderService(session).cancel_order(pid, order_id)

    async def test_cancel_new_order_is_free(self) -> None:
        pid = await self.make_player()
        order_id = await self.accepted_order(pid)
        result = await self.cancel(pid, order_id)
        self.assertEqual(result.reputation_penalty, 0)
        self.assertEqual(result.reputation_after, 50)
        self.assertEqual(await self.workshop(pid), [])
        self.assertEqual(
            await self.scalar("SELECT status FROM orders WHERE id=:i", i=order_id), "cancelled"
        )
        # место освободилось — можно принять следующий заказ
        offer = (await self.board(pid, seed=4)).offers[0]
        await self.accept(pid, offer.offer_id)

    async def test_cancel_started_order_costs_reputation_once(self) -> None:
        pid = await self.make_player()
        order_id = await self.accepted_order(pid)
        await self.move_order(pid, order_id, OrderStatus.IN_REPAIR)
        result = await self.cancel(pid, order_id)
        self.assertEqual(result.reputation_penalty, 5)
        self.assertEqual(result.reputation_after, 45)
        with self.assertRaises(InvalidOrderState):
            await self.cancel(pid, order_id)
        self.assertEqual(await self.scalar("SELECT reputation FROM players WHERE id=:i", i=pid), 45)

    async def test_cannot_cancel_ready_or_completed(self) -> None:
        pid = await self.make_player()
        order_id = await self.accepted_order(pid)
        await self.move_order(pid, order_id, OrderStatus.READY)
        with self.assertRaises(InvalidOrderState):
            await self.cancel(pid, order_id)
        self.assertEqual(
            await self.scalar("SELECT status FROM orders WHERE id=:i", i=order_id), "ready"
        )
        async with self.factory() as session:
            done = await OrderService(session).complete_order(player_id=pid, order_id=order_id)
        self.assertGreater(done.reward_paid, 0)
        with self.assertRaises(InvalidOrderState):
            await self.cancel(pid, order_id)

    async def test_concurrent_cancel_penalizes_once(self) -> None:
        pid = await self.make_player()
        order_id = await self.accepted_order(pid)
        await self.move_order(pid, order_id, OrderStatus.IN_REPAIR)
        results = await asyncio.gather(
            *(self.cancel(pid, order_id) for _ in range(4)), return_exceptions=True
        )
        self.assertEqual(len([r for r in results if not isinstance(r, BaseException)]), 1, results)
        self.assertEqual(await self.scalar("SELECT reputation FROM players WHERE id=:i", i=pid), 45)

    async def test_on_time_bonus_paid_once_on_completion(self) -> None:
        pid = await self.make_player()
        offer = (await self.board(pid)).offers[0]
        order_id = (await self.accept(pid, offer.offer_id)).order_id
        await self.move_order(pid, order_id, OrderStatus.READY)
        async with self.factory() as session:
            done = await OrderService(session).complete_order(player_id=pid, order_id=order_id)
            again = await OrderService(session).complete_order(player_id=pid, order_id=order_id)
        self.assertEqual(done.bonus, offer.potential_bonus)
        self.assertEqual(done.reward_paid, offer.payment + offer.potential_bonus)
        self.assertTrue(again.already_completed)
        self.assertEqual(await self.balance(pid), 15_000 + done.reward_paid)
