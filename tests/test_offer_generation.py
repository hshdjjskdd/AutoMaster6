"""Тесты данных и генератора предложений (без БД)."""

import random
import re
import unittest
from datetime import UTC, datetime, timedelta

from app.game_data.economy import (
    CANCEL_AFTER_START_REPUTATION_PENALTY,
    cancellation_penalty,
    on_time_bonus,
    workshop_capacity,
)
from app.game_data.enums import OrderStatus
from app.game_data.fleet import FLEET, MODELS
from app.game_data.rarity import MODEL_RARITY
from app.game_data.offer_generator import generate_offer
from app.game_data.scenarios import SCENARIOS
from app.schemas import CarConfigurationData, CarData

REQUIRED_MODELS = {
    ("ВАЗ", "2114"),
    ("LADA", "Granta"),
    ("Toyota", "Corolla"),
    ("Volkswagen", "Polo"),
    ("Hyundai", "Solaris"),
}
NOW = datetime(2026, 1, 1, tzinfo=UTC)


class FleetTests(unittest.TestCase):
    def test_all_required_models_present(self) -> None:
        self.assertLessEqual(REQUIRED_MODELS, {(t.brand, t.model) for t in FLEET})

    def test_models_have_several_trims_with_differences(self) -> None:
        for brand, model in REQUIRED_MODELS:
            trims = [t for t in FLEET if (t.brand, t.model) == (brand, model)]
            self.assertGreaterEqual(len(trims), 3, model)
            variants = {(t.engine_code, t.power_hp, t.transmission) for t in trims}
            self.assertGreaterEqual(len(variants), 3, model)

    def test_every_trim_builds_valid_configuration(self) -> None:
        for trim in FLEET:
            for year in trim.years:
                CarConfigurationData(**trim.configuration_kwargs(year))

    def test_wrong_year_rejected(self) -> None:
        with self.assertRaises(ValueError):
            FLEET[0].configuration_kwargs(1990)

    def test_every_model_has_scenarios_at_level_1(self) -> None:
        for trim in FLEET:
            fitting = [
                s for s in SCENARIOS
                if s.fits(trim.model, trim.transmission, 1) and s.fits_tags(trim.tags)
            ]
            self.assertTrue(fitting, f"{trim.title} {trim.name}")


class GeneratorTests(unittest.TestCase):
    def test_drafts_are_valid_and_consistent(self) -> None:
        rng = random.Random(1)
        for level in (1, 3, 10):
            for _ in range(300):
                d = generate_offer(rng, level, NOW)
                CarData(
                    vin=d.vin,
                    plate=d.plate,
                    mileage_km=d.mileage_km,
                    color=d.color,
                    condition_pct=d.condition_pct,
                )
                self.assertIn(d.year, d.trim.years)
                self.assertTrue(d.scenario.fits(d.trim.model, d.trim.transmission, level))
                self.assertTrue(d.scenario.fits_tags(d.trim.tags))
                self.assertGreater(d.payment, 0)
                self.assertEqual(d.payment % 50, 0)
                self.assertTrue(d.scenario.symptoms)
                self.assertGreater(d.expires_at, NOW)

    def test_vin_format_and_plate(self) -> None:
        d = generate_offer(random.Random(5), 1, NOW)
        self.assertRegex(d.vin, r"^[A-HJ-NPR-Z0-9]{17}$")
        self.assertTrue(re.fullmatch(r"[АВЕКМНОРСТУХ]\d{3}[АВЕКМНОРСТУХ]{2} \d{2}", d.plate))

    def test_deterministic_with_seed(self) -> None:
        a = generate_offer(random.Random(7), 2, NOW)
        b = generate_offer(random.Random(7), 2, NOW)
        self.assertEqual(a, b)

    def test_all_models_appear(self) -> None:
        rng = random.Random(3)
        seen = {(d.trim.brand, d.trim.model) for d in (generate_offer(rng, 1, NOW) for _ in range(20_000))}
        expected = {(MODELS[m].brand, MODELS[m].model) for m in MODEL_RARITY}
        self.assertEqual(seen, expected)

    def test_manual_only_scenario_never_on_automatic(self) -> None:
        rng = random.Random(9)
        for _ in range(500):
            d = generate_offer(rng, 10, NOW)
            if d.scenario.code == "clutch_slip":
                self.assertEqual(d.trim.transmission.value, "manual")
            if d.scenario.code == "gearbox_jerk":
                self.assertNotEqual(d.trim.transmission.value, "manual")


class EconomyTests(unittest.TestCase):
    def test_capacity(self) -> None:
        self.assertEqual([workshop_capacity(n) for n in (1, 2, 3, 5, 6, 9, 10)], [1, 1, 2, 2, 3, 4, 4])

    def test_cancellation_rules(self) -> None:
        self.assertEqual(cancellation_penalty(OrderStatus.NEW), 0)
        for st in (OrderStatus.DIAGNOSTICS, OrderStatus.AWAITING_PARTS, OrderStatus.IN_REPAIR):
            self.assertEqual(cancellation_penalty(st), CANCEL_AFTER_START_REPUTATION_PENALTY)
        for st in (OrderStatus.READY, OrderStatus.COMPLETED, OrderStatus.CANCELLED):
            self.assertIsNone(cancellation_penalty(st))

    def test_on_time_bonus(self) -> None:
        self.assertEqual(on_time_bonus(1000, None, NOW), 0)
        self.assertEqual(on_time_bonus(1000, NOW + timedelta(hours=1), NOW), 150)
        self.assertEqual(on_time_bonus(1000, NOW - timedelta(seconds=1), NOW), 0)


if __name__ == "__main__":
    unittest.main()
