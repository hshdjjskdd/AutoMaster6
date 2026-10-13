"""Каталоги этапа 5: автопарк, неисправности, ремонт, запчасти и их совместимость (без БД)."""

import random
import unittest
from collections import defaultdict
from dataclasses import asdict

from app.game_data.catalog import CAR_CONFIGURATIONS
from app.game_data.diagnostic_checks import CHECKS, check_available
from app.game_data.diagnostic_engine import VehicleContext, perform_check
from app.game_data.fault_catalog import (
    CAUSE_BY_CODE,
    CAUSES,
    SCENARIO_CAUSES,
    applicable_causes,
    generate_truth,
    matches,
)
from app.game_data.fleet import FLEET, MODELS, tags_for_configuration
from app.game_data.part_catalog import (
    PART_TYPE_BY_CODE,
    PART_TYPES,
    QUALITIES,
    car_skus,
    fit_value,
    is_compatible,
    make_sku,
    parse_sku,
    price_of,
    spec_for,
)
from app.game_data.repair_catalog import FAULT_INFO, OPS_BY_CODE, ops_for_cause
from app.game_data.scenarios import SCENARIOS
from app.schemas import CarConfigurationData

REQUIRED_MODELS = {
    ("ВАЗ", "2101"), ("ВАЗ", "2102"), ("ВАЗ", "2103"), ("ВАЗ", "2104"), ("ВАЗ", "2105"),
    ("ВАЗ", "2106"), ("ВАЗ", "2107"), ("ВАЗ", "2108"), ("ВАЗ", "2109"), ("ВАЗ", "2110"),
    ("ВАЗ", "2111"), ("ВАЗ", "2112"), ("ВАЗ", "2113"), ("ВАЗ", "2114"), ("ВАЗ", "2115"),
    ("LADA", "Priora"), ("LADA", "Kalina"), ("LADA", "Granta"), ("LADA", "Vesta"),
    ("LADA", "Largus"), ("LADA", "Niva Legend"), ("ГАЗ", "3110"), ("ГАЗ", "Газель"),
    ("УАЗ", "Patriot"), ("Chevrolet", "Niva"), ("Renault", "Logan"), ("Renault", "Duster"),
    ("Hyundai", "Solaris"), ("Kia", "Rio"), ("Volkswagen", "Polo"), ("Skoda", "Octavia"),
    ("Toyota", "Corolla"), ("Toyota", "Camry"), ("Nissan", "Almera"), ("Nissan", "Qashqai"),
    ("Ford", "Focus"), ("Chevrolet", "Lacetti"), ("Chevrolet", "Cobalt"), ("Daewoo", "Nexia"),
    ("Daewoo", "Matiz"), ("Mazda", "3"), ("Mazda", "6"), ("Mitsubishi", "Lancer"),
    ("Mitsubishi", "Outlander"), ("Honda", "Civic"), ("Honda", "CR-V"), ("Chery", "Tiggo"),
    ("Geely", "Coolray"), ("Geely", "Emgrand"), ("Haval", "Jolion"), ("Changan", "CS55"),
}


class FleetTests(unittest.TestCase):
    def test_required_models_present(self) -> None:
        present = {(t.brand, t.model) for t in FLEET}
        self.assertLessEqual(REQUIRED_MODELS, present)

    def test_catalog_ids_unique_and_every_model_has_trims(self) -> None:
        ids = [t.catalog_id for t in FLEET]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual({t.model_id for t in FLEET}, set(MODELS))

    def test_no_two_trims_share_configuration_identity_in_a_year(self) -> None:
        seen: dict[tuple, str] = {}
        for t in FLEET:
            for year in t.years:
                key = (t.brand, t.model, year, t.engine_code, t.transmission, t.drive_type)
                self.assertNotIn(key, seen, f"{t.catalog_id} пересекается с {seen.get(key)}")
                seen[key] = t.catalog_id

    def test_every_trim_builds_valid_configuration_and_tags(self) -> None:
        for t in FLEET:
            CarConfigurationData(**t.configuration_kwargs(t.years[0]))
            tags = t.tags
            for key in ("engine", "chassis", "plug", "battery", "trans", "injection", "ecu"):
                self.assertIn(key, tags, t.catalog_id)

    def test_stage2_configurations_resolve(self) -> None:
        for spec in CAR_CONFIGURATIONS:
            data = asdict(spec)
            tags = tags_for_configuration(
                data["brand"], data["model"], data["engine_code"], data["transmission"],
                data["engine_volume_cc"],
            )
            self.assertEqual(tags["engine"], data["engine_code"])
            self.assertTrue(any(
                is_compatible(sku, tags) for p in PART_TYPES for sku in car_skus(p, tags)
            ))

    def test_fleet_size(self) -> None:
        self.assertGreaterEqual(len(MODELS), 90)
        self.assertGreaterEqual(len(FLEET), 200)


class FaultCatalogTests(unittest.TestCase):
    def test_every_scenario_has_causes_and_every_cause_has_repair_info(self) -> None:
        self.assertEqual({s.code for s in SCENARIOS}, set(SCENARIO_CAUSES))
        self.assertEqual(set(FAULT_INFO), set(CAUSE_BY_CODE))
        for cause in CAUSES:
            self.assertTrue(ops_for_cause(cause.code), cause.code)
        self.assertGreaterEqual(len(CAUSES), 35)

    def test_ops_use_known_parts_and_are_unique(self) -> None:
        total = sum(len(i.ops) for i in FAULT_INFO.values())
        self.assertEqual(total, len(OPS_BY_CODE))
        for op in OPS_BY_CODE.values():
            for need in op.needs:
                self.assertIn(need.type_code, PART_TYPE_BY_CODE)

    def test_truth_is_deterministic_and_applicable(self) -> None:
        for trim in FLEET:
            tags = trim.tags
            for scenario in SCENARIOS:
                if not (scenario.fits(trim.model, trim.transmission, 10) and scenario.fits_tags(tags)):
                    continue
                a = generate_truth(f"{trim.catalog_id}:{scenario.code}", scenario.code, tags)
                b = generate_truth(f"{trim.catalog_id}:{scenario.code}", scenario.code, tags)
                self.assertEqual(a, b)
                self.assertTrue(a)
                for fault in a:
                    self.assertTrue(
                        matches(CAUSE_BY_CODE[fault.code].requires, tags),
                        f"{trim.catalog_id}: {fault.code} невозможна",
                    )

    def test_no_impossible_faults_on_special_cars(self) -> None:
        carb = next(t for t in FLEET if t.tags["injection"] == "carb")
        codes = {c.code for c in applicable_causes(carb.tags)}
        self.assertNotIn("COIL_FAIL", codes)
        self.assertNotIn("MAF_DIRTY", codes)
        self.assertNotIn("O2_SENSOR", codes)
        self.assertIn("CARB_DIRTY", codes)
        auto = next(t for t in FLEET if t.trans_tag == "AT")
        self.assertNotIn("CLUTCH_WORN", {c.code for c in applicable_causes(auto.tags)})
        diesel = next(t for t in FLEET if t.tags["fuel"] == "diesel")
        dcodes = {c.code for c in applicable_causes(diesel.tags)}
        self.assertIn("GLOW_FAIL", dcodes)
        self.assertNotIn("PLUGS_WORN", dcodes)

    def test_every_cause_is_reachable_and_detectable(self) -> None:
        reachable = {c for pool in SCENARIO_CAUSES.values() for c, _ in pool}
        self.assertEqual(reachable, set(CAUSE_BY_CODE))
        for cause in CAUSES:
            checks = FAULT_INFO[cause.code].checks
            self.assertTrue(checks, cause.code)

    def test_multiple_faults_occur(self) -> None:
        tags = next(t for t in FLEET if t.model_id == "kia-rio").tags
        sizes = {
            len(generate_truth(f"seed{i}", "misfire_cel", tags)) for i in range(300)
        }
        self.assertEqual(sizes, {1, 2})

    def test_obd_not_available_on_carburetor_cars(self) -> None:
        carb = next(t for t in FLEET if t.tags["injection"] == "carb").tags
        modern = next(t for t in FLEET if t.model_id == "kia-rio").tags
        obd = next(c for c in CHECKS if c.code == "obd")
        self.assertFalse(check_available(obd, carb))
        self.assertTrue(check_available(obd, modern))
        boost = next(c for c in CHECKS if c.code == "boost")
        self.assertFalse(check_available(boost, modern))

    def test_checks_run_on_every_trim(self) -> None:
        rng = random.Random(3)
        for trim in FLEET:
            ctx = VehicleContext(trim.model, trim.engine_code, trim.engine_volume_cc, 120_000, trim.tags)
            truth = {f.code: f.detail for f in generate_truth(trim.catalog_id, None, trim.tags)}
            for check in CHECKS:
                if check_available(check, trim.tags):
                    self.assertTrue(perform_check(check.code, ctx, truth, rng).readings)


class PartCatalogTests(unittest.TestCase):
    def test_every_repair_part_exists_and_fits_every_applicable_car(self) -> None:
        for trim in FLEET:
            tags = trim.tags
            for cause in applicable_causes(tags):
                for op in ops_for_cause(cause.code):
                    for need in op.needs:
                        ptype = PART_TYPE_BY_CODE[need.type_code]
                        skus = car_skus(ptype, tags)
                        self.assertEqual(len(skus), 3)
                        for sku in skus:
                            self.assertLessEqual(len(sku), 32)
                            self.assertTrue(is_compatible(sku, tags), sku)
                            spec = spec_for(sku)
                            self.assertIsNotNone(spec, sku)
                            self.assertGreater(spec.base_price, 0)  # type: ignore[union-attr]

    def test_quality_tiers_price_order(self) -> None:
        for ptype in PART_TYPES:
            fit = "ALL" if ptype.universal else "HK-RB"
            prices = [price_of(ptype, fit, q.level) for q in QUALITIES]
            self.assertEqual(prices, sorted(prices))
            self.assertLess(prices[0], prices[2])

    def test_incompatible_part_is_rejected(self) -> None:
        rio = next(t for t in FLEET if t.model_id == "kia-rio").tags
        granta = next(t for t in FLEET if t.model_id == "lada-granta").tags
        pads = PART_TYPE_BY_CODE["pads"]
        rio_pads = make_sku("pads", fit_value(pads, rio), 2)
        self.assertTrue(is_compatible(rio_pads, rio))
        self.assertFalse(is_compatible(rio_pads, granta))
        starter = PART_TYPE_BY_CODE["starter"]
        self.assertFalse(is_compatible(make_sku("starter", fit_value(starter, rio), 1), granta))
        # универсальные подходят всем
        self.assertTrue(is_compatible(make_sku("fuse", "ALL", 1), granta))

    def test_sku_parsing_rejects_garbage(self) -> None:
        for bad in ("pads:HK-RB", "nope:ALL:1", "pads:HK-RB:9", "fuse:HK-RB:1", "pads:ALL:1", "x"):
            self.assertIsNone(parse_sku(bad), bad)
        self.assertIsNotNone(parse_sku("pads:HK-RB:2"))

    def test_expensive_cars_have_expensive_parts(self) -> None:
        chiron = next(t for t in FLEET if t.model_id == "bugatti-chiron").tags
        rio = next(t for t in FLEET if t.model_id == "kia-rio").tags
        pads = PART_TYPE_BY_CODE["pads"]
        self.assertGreater(
            price_of(pads, fit_value(pads, chiron), 2), 3 * price_of(pads, fit_value(pads, rio), 2)
        )

    def test_part_counts(self) -> None:
        by_section: dict[str, int] = defaultdict(int)
        for p in PART_TYPES:
            by_section[p.section] += 1
        self.assertGreaterEqual(len(by_section), 10)
        self.assertGreaterEqual(len(PART_TYPES), 40)


if __name__ == "__main__":
    unittest.main()
