"""Этап 6 без БД: расписание обновлений, вероятности, «жалость», неисправности заказов,
оплата/смета и симуляция экономики на 10, 30 и 100 заказов."""

import random
import statistics
import unittest
from datetime import UTC, datetime, timedelta

from app.game_data import economy as eco
from app.game_data.economy_sim import simulate, summarize
from app.game_data.fault_catalog import CAUSE_BY_CODE, truth_from_plan
from app.game_data.fleet import FLEET
from app.game_data.offer_generator import generate_offer
from app.game_data.order_board import (
    format_countdown,
    initial_tiers,
    missed_rounds,
    next_refresh_time,
    plan_refresh,
    roll_tiers,
    spawn_chance,
)
from app.game_data.order_planner import (
    fitting_scenarios,
    parse_plan,
    parts_supported,
    plan_faults,
    tier_for_count,
    serialize_plan,
)
from app.schemas import OfferCard

NOW = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)


class ScheduleTests(unittest.TestCase):
    def test_interval_is_two_hours(self) -> None:
        self.assertEqual(eco.REFRESH_INTERVAL_HOURS, 2)
        self.assertEqual(next_refresh_time(NOW), NOW + timedelta(hours=2))

    def test_board_holds_ten(self) -> None:
        self.assertEqual(eco.BOARD_SIZE, 10)

    def test_countdown_format(self) -> None:
        self.assertEqual(format_countdown(NOW + timedelta(hours=1, minutes=24), NOW), "1 ч 24 мин")
        self.assertEqual(format_countdown(NOW + timedelta(minutes=12), NOW), "12 мин")
        self.assertEqual(format_countdown(NOW + timedelta(hours=2), NOW), "2 ч")
        self.assertEqual(format_countdown(NOW - timedelta(seconds=1), NOW), "сейчас")
        self.assertEqual(format_countdown(NOW + timedelta(seconds=10), NOW), "1 мин")

    def test_missed_rounds_are_capped(self) -> None:
        self.assertEqual(missed_rounds(None, NOW), 0)
        self.assertEqual(missed_rounds(NOW - timedelta(hours=2, minutes=1), NOW), 0)
        self.assertEqual(missed_rounds(NOW - timedelta(hours=4, minutes=1), NOW), 1)
        self.assertEqual(missed_rounds(NOW - timedelta(days=30), NOW), eco.MAX_CATCHUP_REFRESHES - 1)


class ProbabilityTests(unittest.TestCase):
    def test_base_chances(self) -> None:
        self.assertEqual(eco.TIER_SPAWN_CHANCE, {1: 0.70, 2: 0.40, 3: 0.15})

    def test_independent_rolls_match_probabilities(self) -> None:
        rng = random.Random(11)
        n = 30_000
        rolls = [roll_tiers(rng, 0) for _ in range(n)]
        for tier, p in eco.TIER_SPAWN_CHANCE.items():
            freq = sum(tier in r for r in rolls) / n
            self.assertAlmostEqual(freq, p, delta=0.015, msg=f"tier {tier}")
        # независимость: P(лёгкий и сложный) ≈ 0.70 × 0.15
        both = sum(1 in r and 3 in r for r in rolls) / n
        self.assertAlmostEqual(both, 0.70 * 0.15, delta=0.012)
        self.assertTrue(any(len(r) == 3 for r in rolls))  # бывают сразу все три сложности

    def test_pity_raises_chances_gradually_and_is_capped(self) -> None:
        for tier in eco.TIERS:
            values = [spawn_chance(tier, s) for s in range(0, 12)]
            self.assertEqual(values, sorted(values))
            self.assertGreater(values[2], values[0])
            self.assertLessEqual(max(values), eco.PITY_MAX_CHANCE)

    def test_empty_streak_is_guaranteed_to_end(self) -> None:
        rng = random.Random(3)
        for _ in range(2000):
            streak = 0
            while True:
                got = roll_tiers(rng, streak)
                if got:
                    break
                streak += 1
                self.assertLessEqual(streak, eco.PITY_GUARANTEE_AFTER)

    def test_longest_drought_shrinks_with_pity(self) -> None:
        def longest(use_pity: bool) -> int:
            rng, best, run, streak = random.Random(5), 0, 0, 0
            for _ in range(20_000):
                got = [t for t in eco.TIERS if rng.random() < eco.TIER_SPAWN_CHANCE[t]] if not use_pity else roll_tiers(rng, streak)
                streak = 0 if got else streak + 1
                run = 0 if got else run + 1
                best = max(best, run)
            return best

        self.assertLessEqual(longest(True), eco.PITY_GUARANTEE_AFTER)
        self.assertGreater(longest(False), eco.PITY_GUARANTEE_AFTER)

    def test_full_board_creates_nothing_and_keeps_streak(self) -> None:
        out = plan_refresh(random.Random(1), empty_streak=2, free_slots=0)
        self.assertEqual((out.tiers, out.empty_streak), ((), 2))

    def test_free_slots_limit_new_orders(self) -> None:
        for seed in range(200):
            out = plan_refresh(random.Random(seed), empty_streak=0, free_slots=1)
            self.assertLessEqual(len(out.tiers), 1)

    def test_streak_counts_empty_refreshes_and_resets(self) -> None:
        rng = random.Random(0)
        out = plan_refresh(rng, empty_streak=3, free_slots=5, rounds=1)
        self.assertEqual(out.empty_streak, 0 if out.tiers else 4)

    def test_initial_board(self) -> None:
        for seed in range(100):
            tiers = initial_tiers(random.Random(seed))
            self.assertIn(eco.EASY, tiers)
            self.assertGreaterEqual(len(tiers), eco.INITIAL_OFFERS)
            self.assertLessEqual(len(tiers), eco.BOARD_SIZE)


class GenerationTests(unittest.TestCase):
    def test_fault_count_by_difficulty(self) -> None:
        rng = random.Random(21)
        seen: dict[int, set[int]] = {1: set(), 2: set(), 3: set()}
        for tier in eco.TIERS:
            for _ in range(300):
                draft = generate_offer(rng, 10, NOW, tier)
                n = len(draft.plan)
                self.assertEqual(draft.tier, tier)
                low, high = eco.TIER_FAULT_RANGE[tier]
                self.assertTrue(low <= n <= high, (tier, n))
                seen[tier].add(n)
        self.assertEqual(seen[1], {1})
        self.assertEqual(seen[2], {2, 3})
        self.assertTrue(min(seen[3]) >= 4 and len(seen[3]) > 1)

    def test_no_duplicate_or_incompatible_faults(self) -> None:
        rng = random.Random(8)
        for _ in range(600):
            plan = generate_offer(rng, 10, NOW, rng.choice(eco.TIERS)).plan
            codes = [f.code for f in plan]
            self.assertEqual(len(codes), len(set(codes)))
            for a in codes:
                for b in codes:
                    self.assertNotIn(frozenset({a, b}), eco.INCOMPATIBLE_CAUSES)

    def test_faults_fit_the_car_and_its_parts(self) -> None:
        rng = random.Random(9)
        for _ in range(500):
            draft = generate_offer(rng, rng.randint(1, 10), NOW, rng.choice(eco.TIERS))
            tags = draft.trim.tags
            for fault in draft.plan:
                from app.game_data.fault_catalog import matches

                self.assertTrue(matches(CAUSE_BY_CODE[fault.code].requires, tags), fault.code)
                self.assertTrue(parts_supported(fault.code, tags), fault.code)

    def test_count_is_capped_by_what_the_car_supports(self) -> None:
        for trim in FLEET[::7]:
            tags = trim.tags
            scenarios = fitting_scenarios(trim.model, trim.transmission, 10, tags)
            everything = plan_faults(random.Random(1), scenarios, tags, 99)
            self.assertGreaterEqual(len(everything), 4, trim.title)
            self.assertEqual(len({f.code for f in everything}), len(everything))
        # на первом уровне сложный заказ честно получает меньшую сложность, а не фиктивные поломки
        rng = random.Random(4)
        for _ in range(100):
            d = generate_offer(rng, 1, NOW, eco.HARD)
            self.assertEqual(d.tier, tier_for_count(len(d.plan)))
            self.assertLessEqual(len(d.plan), eco.TIER_FAULT_RANGE[eco.HARD][1])

    def test_complaint_only_has_symptoms_not_real_faults(self) -> None:
        rng = random.Random(2)
        for _ in range(200):
            draft = generate_offer(rng, 10, NOW, rng.choice(eco.TIERS))
            text = (draft.complaint + " " + " ".join(draft.symptoms)).lower()
            for fault in draft.plan:
                cause = CAUSE_BY_CODE[fault.code]
                self.assertNotIn(fault.code.lower(), text)
                self.assertNotIn(cause.name.lower(), text)

    def test_offer_card_has_no_field_that_reveals_faults(self) -> None:
        fields = set(OfferCard.model_fields)
        self.assertFalse({"plan", "planned_faults", "faults", "causes", "scenario_code"} & fields)

    def test_variety(self) -> None:
        rng = random.Random(6)
        drafts = [generate_offer(rng, 10, NOW, rng.choice(eco.TIERS)) for _ in range(400)]
        self.assertGreater(len({d.trim.model for d in drafts}), 30)
        self.assertGreater(len({d.complaint for d in drafts}), 200)
        self.assertGreater(len({tuple(sorted(f.code for f in d.plan)) for d in drafts}), 150)
        self.assertGreater(len({d.payment for d in drafts}), 100)

    def test_plan_roundtrip_and_truth(self) -> None:
        draft = generate_offer(random.Random(13), 10, NOW, eco.HARD)
        again = parse_plan(serialize_plan(list(draft.plan)))
        self.assertEqual(tuple(again), draft.plan)
        truth = truth_from_plan("1:VIN", [(f.code, f.scenario_code) for f in again], draft.trim.tags)
        self.assertEqual([t.code for t in truth], [f.code for f in draft.plan])
        # воспроизводимо
        self.assertEqual(truth, truth_from_plan("1:VIN", [(f.code, f.scenario_code) for f in again], draft.trim.tags))
        self.assertEqual(parse_plan(""), [])
        self.assertEqual(parse_plan(None), [])

    def test_price_and_expenses_grow_with_difficulty_on_average(self) -> None:
        rng = random.Random(10)
        med = {}
        for tier in eco.TIERS:
            ds = [generate_offer(rng, 10, NOW, tier) for _ in range(500)]
            self.assertTrue(all(d.payment > 0 and d.est_cost >= 0 for d in ds))
            med[tier] = (statistics.median(d.payment for d in ds), statistics.median(d.est_cost for d in ds))
        self.assertLess(med[1][0], med[2][0])
        self.assertLess(med[2][0], med[3][0])
        self.assertLess(med[1][1], med[2][1])
        self.assertLess(med[2][1], med[3][1])

    def test_parameters_are_configurable(self) -> None:
        self.assertEqual(set(eco.PARTS_MARKUP_PCT), set(eco.TIERS))
        self.assertEqual(set(eco.TIER_FAULT_RANGE), set(eco.TIERS))
        original = eco.TIER_FAULT_RANGE[eco.EASY]
        self.assertEqual(original, (1, 1))


class EconomySimulationTests(unittest.TestCase):
    def test_profit_formula(self) -> None:
        for order in simulate(100, seed=7):
            self.assertEqual(order.net, order.payment - order.parts - order.waste - order.diagnostics)

    def test_simulations_10_30_100(self) -> None:
        for n, seed in ((10, 1), (30, 2), (100, 3)):
            orders = simulate(n, seed=seed)
            stats = summarize(orders)
            self.assertEqual(stats["orders"], n)
            self.assertEqual(stats["profit"], stats["revenue"] - stats["expenses"])
            self.assertGreater(stats["profit"], 0, f"экономика в минусе на {n} заказах")
            self.assertLess(stats["loss_share"], 0.30)
            print(f"\n  симуляция {n:>3} заказов: выручка {stats['revenue']:,}, расходы {stats['expenses']:,}, "
                  f"прибыль {stats['profit']:,}, медиана {stats['median_net']:,.0f}, убыточных {stats['loss_share']:.0%}")

    def test_hard_orders_are_not_guaranteed_more_profitable(self) -> None:
        orders = simulate(4500, seed=2, tiers=eco.TIERS)
        by = {t: [o.net for o in orders if o.tier == t] for t in eco.TIERS}
        loss = {t: sum(n < 0 for n in v) / len(v) for t, v in by.items()}
        # риск растёт со сложностью…
        self.assertLess(loss[1], loss[2] + 0.01)
        self.assertGreater(loss[3], loss[1] * 3)
        self.assertGreater(loss[3], 0.05)
        # …а выигрыш от сложности не гарантирован: у заметной доли сложных заказов прибыль
        # ниже медианной прибыли лёгких.
        easy_median = statistics.median(by[1])
        below = sum(n < easy_median for n in by[3]) / len(by[3])
        self.assertGreater(below, 0.25)
        # и медиана сложных не выше «средних» с запасом
        self.assertLess(statistics.median(by[3]), statistics.median(by[2]) * 1.15)


if __name__ == "__main__":
    unittest.main()
