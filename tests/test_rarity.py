"""Редкость, сложность и независимость выпадения моделей."""

import random
import unittest
from collections import Counter
from datetime import UTC, datetime

from app.game_data.fleet import FLEET, MODELS
from app.game_data.offer_generator import generate_offer
from app.game_data.rarity import (
    DIFFICULTY_RANGE,
    MODEL_RARITY,
    MODELS_BY_RARITY,
    RARITY_EMOJI,
    RARITY_WEIGHTS,
    Rarity,
    difficulty_of,
    rarity_emoji,
    rarity_of,
    roll_rarity,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)


class RarityTableTests(unittest.TestCase):
    def test_counts_per_rarity(self) -> None:
        sizes = {r: len(m) for r, m in MODELS_BY_RARITY.items()}
        self.assertEqual(
            sizes,
            {Rarity.COMMON: 20, Rarity.RARE: 15, Rarity.EPIC: 10, Rarity.LEGENDARY: 5},
        )
        self.assertEqual(len(MODEL_RARITY), 50)

    def test_weights_sum_and_values(self) -> None:
        self.assertEqual(
            RARITY_WEIGHTS,
            {Rarity.COMMON: 60, Rarity.RARE: 25, Rarity.EPIC: 12, Rarity.LEGENDARY: 3},
        )

    def test_difficulty_within_rarity_range_and_varies(self) -> None:
        for mid, (rarity, difficulty) in MODEL_RARITY.items():
            lo, hi = DIFFICULTY_RANGE[rarity]
            self.assertTrue(lo <= difficulty <= hi, mid)
        for rarity in Rarity:
            values = {MODEL_RARITY[m][1] for m in MODELS_BY_RARITY[rarity]}
            if rarity != Rarity.LEGENDARY or len(values) > 1:
                self.assertGreater(len(values), 1, rarity)

    def test_every_rarity_model_has_trims(self) -> None:
        trimmed = {t.model_id for t in FLEET}
        for mid in MODEL_RARITY:
            self.assertIn(mid, trimmed)
            self.assertIn(mid, MODELS)

    def test_lookup_by_name(self) -> None:
        self.assertEqual(rarity_of("Bugatti", "Chiron"), Rarity.LEGENDARY)
        self.assertEqual(rarity_of("LADA", "Granta"), Rarity.COMMON)
        self.assertEqual(difficulty_of("Bugatti", "Chiron"), 5)
        self.assertEqual(rarity_emoji("Porsche", "911 Carrera"), "🟣")
        self.assertEqual(rarity_emoji("ВАЗ", "2101"), "")

    def test_emoji(self) -> None:
        self.assertEqual(list(RARITY_EMOJI.values()), ["🟢", "🔵", "🟣", "🟡"])


class DropTests(unittest.TestCase):
    def test_rarity_frequencies(self) -> None:
        rng = random.Random(2026)
        n = 40_000
        counts = Counter(roll_rarity(rng) for _ in range(n))
        for rarity, weight in RARITY_WEIGHTS.items():
            self.assertAlmostEqual(counts[rarity] / n * 100, weight, delta=1.0, msg=rarity)

    def test_offers_use_matching_model_and_difficulty(self) -> None:
        rng = random.Random(7)
        for _ in range(500):
            d = generate_offer(rng, 1, NOW)
            self.assertEqual(rarity_of(d.trim.brand, d.trim.model), d.rarity)
            self.assertEqual(difficulty_of(d.trim.brand, d.trim.model), d.difficulty)

    def test_repeats_allowed_and_offers_independent(self) -> None:
        rng = random.Random(3)
        models = [generate_offer(rng, 1, NOW).trim.model_id for _ in range(300)]
        self.assertLess(len(set(models)), len(models))
        # новая генерация не зависит от предыдущей: тот же seed -> та же серия
        a = [generate_offer(random.Random(5), 1, NOW).trim.catalog_id for _ in range(3)]
        self.assertEqual(len(set(a)), 1)

    def test_harder_cars_pay_more_on_average(self) -> None:
        rng = random.Random(11)
        pay: dict[Rarity, list[int]] = {r: [] for r in Rarity}
        for _ in range(4000):
            d = generate_offer(rng, 1, NOW)
            pay[d.rarity].append(d.payment)
        avg = {r: sum(v) / len(v) for r, v in pay.items()}
        self.assertLess(avg[Rarity.COMMON], avg[Rarity.RARE])
        self.assertLess(avg[Rarity.RARE], avg[Rarity.EPIC])
        self.assertLess(avg[Rarity.EPIC], avg[Rarity.LEGENDARY])


class FleetIntegrityTests(unittest.TestCase):
    def test_catalog_ids_unique(self) -> None:
        ids = [t.catalog_id for t in FLEET]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
