"""Тесты движка диагностики и данных (без БД, выполняются без внешних библиотек)."""

import random
import unittest

from app.game_data.diagnostic_checks import (
    CHECK_BY_CODE,
    CHECKS,
    DIAGNOSTIC_EQUIPMENT,
    TOOL_CODES,
    check_fee,
)
from app.game_data.diagnostic_engine import BAD, INFO, OK, WARN, VehicleContext, perform_check
from app.game_data.fault_catalog import (
    CAUSE_BY_CODE,
    CAUSES,
    FUSE_CIRCUITS_BY_SCENARIO,
    SCENARIO_CAUSES,
    generate_truth,
)
from app.game_data.scenarios import SCENARIOS

CTX = VehicleContext(model="Granta", engine_code="11186", engine_volume_cc=1596, mileage_km=90_000)
N = 300
HERRINGS = {"P0420", "P0455"}


def run(check: str, truth: dict[str, str], seed: int, ctx: VehicleContext = CTX):  # type: ignore[no-untyped-def]
    return perform_check(check, ctx, truth, random.Random(seed))


DIESEL_CTX = VehicleContext(
    model="Duster", engine_code="K9K", engine_volume_cc=1461, mileage_km=90_000,
    tags={"fuel": "diesel", "cylinders": 4},
)


def bad_rows(check: str, truth: dict[str, str], seed: int):  # type: ignore[no-untyped-def]
    ctx = DIESEL_CTX if "GLOW_FAIL" in truth else CTX
    return [
        r for r in run(check, truth, seed, ctx).readings
        if r.flag in (WARN, BAD) and r.label not in HERRINGS
    ]


def by_label(
    check: str, truth: dict[str, str], seed: int, ctx: VehicleContext = CTX
) -> dict[str, float]:
    out: dict[str, float] = {}
    for r in run(check, truth, seed, ctx).readings:
        try:
            out[r.label] = float(r.value)
        except ValueError:
            pass
    return out


class DataTests(unittest.TestCase):
    def test_all_requested_checks_exist(self) -> None:
        codes = set(CHECK_BY_CODE)
        self.assertGreaterEqual(
            codes,
            {"battery", "alternator", "fuses", "starter", "plugs", "obd", "fuel", "intake",
             "cooling", "brakes", "suspension"},
        )

    def test_all_tools_exist_and_priced(self) -> None:
        self.assertEqual(
            set(TOOL_CODES),
            {"TOOLSET-BASIC", "MULTIMETER", "OBD-SCANNER", "FUEL-PRESSURE-KIT", "BRAKE-SUSP-TESTER",
             "COMPRESSION-TESTER", "AC-MANIFOLD"},
        )
        new = {e.code for e in DIAGNOSTIC_EQUIPMENT}
        self.assertEqual(
            new,
            {"MULTIMETER", "FUEL-PRESSURE-KIT", "BRAKE-SUSP-TESTER", "COMPRESSION-TESTER", "AC-MANIFOLD"},
        )

    def test_checks_cost_time_and_money(self) -> None:
        for c in CHECKS:
            self.assertGreater(c.minutes, 0)
            owned, rented = check_fee(c, True), check_fee(c, False)
            self.assertEqual(owned, c.consumable_cost)
            self.assertGreaterEqual(rented, owned)
            if c.tool_code is not None:
                self.assertGreater(rented, owned, c.code)
        self.assertEqual(check_fee(CHECK_BY_CODE["visual"], False), 0)
        self.assertEqual(check_fee(CHECK_BY_CODE["fuel"], False), 600)
        self.assertEqual(check_fee(CHECK_BY_CODE["fuel"], True), 0)
        self.assertEqual(check_fee(CHECK_BY_CODE["intake"], True), 100)  # расходники

    def test_every_scenario_has_ambiguous_causes(self) -> None:
        self.assertEqual({s.code for s in SCENARIOS}, set(SCENARIO_CAUSES))
        for code, pool in SCENARIO_CAUSES.items():
            self.assertGreaterEqual(len(pool), 2, code)
            outcomes = {generate_truth(f"{code}:{i}", code)[0].code for i in range(N)}
            self.assertGreaterEqual(len(outcomes), 2, code)

    def test_every_cause_reachable_from_some_scenario(self) -> None:
        reachable = {c for pool in SCENARIO_CAUSES.values() for c, _ in pool}
        self.assertEqual(reachable, set(CAUSE_BY_CODE))


class TruthTests(unittest.TestCase):
    def test_truth_valid_and_deterministic(self) -> None:
        for code in SCENARIO_CAUSES:
            for i in range(100):
                a = generate_truth(f"s{i}", code)
                self.assertEqual(a, generate_truth(f"s{i}", code))
                self.assertTrue(1 <= len(a) <= 2)
                self.assertEqual(len({t.code for t in a}), len(a))
                for t in a:
                    self.assertIn(t.code, CAUSE_BY_CODE)
                    if t.code == "FUSE_BLOWN":
                        allowed = FUSE_CIRCUITS_BY_SCENARIO.get(code, ("ignition", "fuel_pump", "fan", "lights"))
                        self.assertIn(t.detail, allowed)

    def test_unknown_scenario_falls_back_to_any_cause(self) -> None:
        seen = {generate_truth(f"x{i}", None)[0].code for i in range(600)}
        self.assertGreater(len(seen), 10)
        self.assertTrue(generate_truth("y", "old_removed_scenario"))

    def test_second_fault_happens_sometimes_but_rarely(self) -> None:
        sizes = [len(generate_truth(f"z{i}", "no_start_cold")) for i in range(2000)]
        share = sizes.count(2) / len(sizes)
        self.assertTrue(0.1 < share < 0.5, share)

    def test_alternator_often_drains_battery(self) -> None:
        pairs = 0
        total = 0
        for i in range(2000):
            truth = generate_truth(f"a{i}", "battery_drain")
            if truth[0].code == "ALT_FAIL":
                total += 1
                pairs += any(t.code == "BAT_WEAK" for t in truth)
        self.assertGreater(total, 100)
        self.assertTrue(0.35 < pairs / total < 0.75)


class MeasurementTests(unittest.TestCase):
    def test_healthy_car_has_no_real_deviations(self) -> None:
        for check in CHECK_BY_CODE:
            for seed in range(N):
                rows = [
                    r for r in run(check, {}, seed).readings
                    if r.flag in (WARN, BAD) and r.label not in HERRINGS
                ]
                self.assertEqual(rows, [], f"{check} seed={seed}: {rows}")

    def test_every_cause_shows_up_somewhere(self) -> None:
        details = {
            "FUSE_BLOWN": "fuel_pump", "COIL_FAIL": "cyl:2", "THERMOSTAT_STUCK": "open",
            "INTAKE_LEAK": "hose", "ALT_FAIL": "no_charge", "SUSP_STRUT": "left",
            "SUSP_LINK": "left", "BRAKE_PADS_WORN": "both", "WHEEL_BEARING": "left",
            "CV_JOINT": "left", "TIE_ROD": "left", "INJECTORS": "cyl:2", "AC_COMP": "worn",
        }
        for cause in CAUSES:
            truth = {cause.code: details.get(cause.code, "")}
            detected = sum(
                any(bad_rows(check, truth, seed) for check in CHECK_BY_CODE) for seed in range(N)
            )
            # течь масла видна только при осмотре, и осмотр не всегда её замечает
            minimum = 0.85 if cause.code == "OIL_LEAK" else 0.95
            self.assertGreaterEqual(detected / N, minimum, cause.code)

    def test_readings_have_expected_structure(self) -> None:
        for check in CHECK_BY_CODE:
            outcome = run(check, {"BAT_WEAK": ""}, 1)
            self.assertTrue(outcome.readings)
            self.assertTrue(outcome.interpretation)
            for r in outcome.readings:
                self.assertIn(r.flag, {OK, WARN, BAD, INFO})
                self.assertTrue(r.label and r.value)

    def test_noise_differs_between_attempts_but_is_reproducible(self) -> None:
        a = run("battery", {}, 1)
        self.assertEqual(a, run("battery", {}, 1))
        values = {run("battery", {}, s).readings[0].value for s in range(20)}
        self.assertGreater(len(values), 5)

    # --- принципы реализма -------------------------------------------------

    def test_battery_voltage_alone_cannot_separate_battery_from_alternator(self) -> None:
        bat = [by_label("battery", {"BAT_WEAK": ""}, s)["Напряжение покоя на клеммах"] for s in range(N)]
        alt = [
            by_label("battery", {"ALT_FAIL": "no_charge"}, s)["Напряжение покоя на клеммах"]
            for s in range(N)
        ]
        self.assertGreater(max(bat), min(alt))  # диапазоны пересекаются
        # а зарядка генератора их различает
        chg_bat = [by_label("alternator", {"BAT_WEAK": ""}, s)["Напряжение бортсети, холостой ход"] for s in range(N)]
        chg_alt = [
            by_label("alternator", {"ALT_FAIL": "no_charge"}, s)["Напряжение бортсети, холостой ход"]
            for s in range(N)
        ]
        self.assertGreater(min(chg_bat), 14.0)
        self.assertLess(max(chg_alt), 13.0)

    def test_starter_current_separates_weak_battery_from_starter(self) -> None:
        amps_bat = [by_label("starter", {"BAT_WEAK": ""}, s)["Ток стартера"] for s in range(N)]
        amps_st = [by_label("starter", {"STARTER_FAIL": ""}, s)["Ток стартера"] for s in range(N)]
        self.assertLess(max(amps_bat), 125)
        self.assertGreater(min(amps_st), 200)

    def test_wire_corrosion_shows_voltage_drop_not_bad_battery(self) -> None:
        labels = by_label("starter", {"WIRE_CORR": ""}, 3)
        self.assertGreater(labels["Падение напряжения АКБ — стартер"], 1.5)
        self.assertGreater(by_label("battery", {"WIRE_CORR": ""}, 3)["Напряжение покоя на клеммах"], 12.3)

    def test_obd_is_not_proof(self) -> None:
        # 1) один и тот же код выдают разные причины
        causes_with_p0171 = set()
        for cause in ("INTAKE_LEAK", "MAF_DIRTY", "FUEL_PUMP_WEAK", "FUEL_FILTER_CLOG"):
            for s in range(N):
                if any(r.label == "P0171" for r in run("obd", {cause: "hose"}, s).readings):
                    causes_with_p0171.add(cause)
                    break
        self.assertEqual(len(causes_with_p0171), 4)
        # 2) при реальной поломке код может отсутствовать
        missing = sum(
            not any(r.label == "P0171" for r in run("obd", {"INTAKE_LEAK": "hose"}, s).readings)
            for s in range(N)
        )
        self.assertGreater(missing, N * 0.05)
        # 3) у исправной машины бывают посторонние коды
        stray = sum(
            any(r.label in HERRINGS for r in run("obd", {}, s).readings) for s in range(N)
        )
        self.assertGreater(stray, 0)
        # 4) код не называет деталь: в описании всегда оговорка про область
        for r in run("obd", {"COIL_FAIL": "cyl:2"}, 1).readings:
            if r.label.startswith("P0"):
                self.assertIn("Это не приговор конкретной детали", r.note)

    def test_intake_leak_needs_spray_test_to_separate_from_dirty_maf(self) -> None:
        leak = [by_label("intake", {"INTAKE_LEAK": "hose"}, s) for s in range(N)]
        maf = [by_label("intake", {"MAF_DIRTY": ""}, s) for s in range(N)]
        key = "Прирост оборотов при распылении очистителя"
        self.assertGreater(min(x[key] for x in leak), 100)
        self.assertLess(max(x[key] for x in maf), 40)
        # трудный случай: пропуски зажигания тоже занижают разрежение
        misfire = [by_label("intake", {"COIL_FAIL": "cyl:1"}, s)["Разрежение на холостом ходу"] for s in range(N)]
        self.assertLess(min(misfire), 56)

    def test_coil_vs_plugs(self) -> None:
        coil = run("plugs", {"COIL_FAIL": "cyl:3"}, 5).readings
        fouled = [r for r in coil if "вид свечи" in r.label and "чёрный" in r.value]
        self.assertEqual([r.label for r in fouled], ["Цилиндр 3: вид свечи"])
        bad_coil = [r for r in coil if "катушки" in r.label and r.flag == BAD]
        self.assertEqual([r.label for r in bad_coil], ["Цилиндр 3: вторичная обмотка катушки"])
        worn = run("plugs", {"PLUGS_WORN": ""}, 5).readings
        self.assertEqual(sum("зазор" in r.label and r.flag != OK for r in worn), 4)
        self.assertEqual([r for r in worn if "катушки" in r.label and r.flag != OK], [])

    def test_fuel_pressure_depends_on_model_and_cause(self) -> None:
        polo = VehicleContext("Polo", "CFNA", 1598, 90_000)
        vaz = VehicleContext("2114", "2111", 1499, 90_000)
        key = "Давление в рампе, холостой ход"
        self.assertGreater(by_label("fuel", {}, 1, polo)[key], by_label("fuel", {}, 1, vaz)[key] + 0.4)
        pump = by_label("fuel", {"FUEL_PUMP_WEAK": ""}, 2)
        self.assertLess(pump[key], 2.6)
        filt = by_label("fuel", {"FUEL_FILTER_CLOG": ""}, 2)
        self.assertGreater(filt[key], 2.5)  # на холостых фильтр «не виден»
        self.assertLess(filt["Давление при резком открытии дросселя"], 2.4)  # под нагрузкой виден

    def test_blown_fuel_pump_fuse_shows_zero_pressure_and_is_found_on_circuits(self) -> None:
        truth = {"FUSE_BLOWN": "fuel_pump"}
        self.assertEqual(by_label("fuel", truth, 1)["Давление в рампе, холостой ход"], 0.0)
        rows = run("fuses", truth, 1).readings
        blown = [r for r in rows if r.value == "перегорел"]
        self.assertEqual([r.label for r in blown], ["Предохранитель цепи топливного насоса"])

    def test_fan_failure_and_fan_fuse_look_identical_in_cooling_check(self) -> None:
        a = [r for r in run("cooling", {"FAN_FAIL": ""}, 1).readings if "вентилятор" in r.label.lower()]
        b = [r for r in run("cooling", {"FUSE_BLOWN": "fan"}, 1).readings if "вентилятор" in r.label.lower()]
        self.assertEqual([r.value for r in a], [r.value for r in b])
        fuses = run("fuses", {"FUSE_BLOWN": "fan"}, 1).readings
        self.assertTrue(any(r.value == "перегорел" for r in fuses))
        self.assertFalse(any(r.value == "перегорел" for r in run("fuses", {"FAN_FAIL": ""}, 1).readings))

    def test_thermostat_variants(self) -> None:
        opened = by_label("cooling", {"THERMOSTAT_STUCK": "open"}, 1)
        closed = by_label("cooling", {"THERMOSTAT_STUCK": "closed"}, 1)
        self.assertLess(opened["Максимум за 15 мин прогрева"], 80)
        self.assertGreater(closed["Максимум за 15 мин прогрева"], 100)

    def test_coolant_leak_needs_pressure_test(self) -> None:
        drop = by_label("cooling", {"COOLANT_LEAK": ""}, 1)["Падение давления при опрессовке за 5 мин"]
        self.assertGreater(drop, 0.2)

    def test_brakes_and_suspension_differ_per_side(self) -> None:
        left = by_label("suspension", {"SUSP_STRUT": "left"}, 1)
        self.assertLess(left["Эффективность амортизатора, левый"], 40)
        self.assertGreater(left["Эффективность амортизатора, правый"], 58)
        link = by_label("suspension", {"SUSP_LINK": "right"}, 1)
        self.assertGreater(link["Люфт стойки стабилизатора, правая"], 1.5)
        self.assertLess(link["Люфт стойки стабилизатора, левая"], 0.8)
        pads = by_label("brakes", {"BRAKE_PADS_WORN": "left"}, 1)
        self.assertLess(pads["Толщина колодки, левая передняя"], 3.0)
        self.assertGreater(pads["Толщина колодки, правая передняя"], 3.0)
        fluid = by_label("brakes", {"BRAKE_FLUID_OLD": ""}, 1)
        self.assertGreater(fluid["Вода в тормозной жидкости"], 3.0)

    def test_visual_inspection_is_unreliable(self) -> None:
        hits = sum(bool(bad_rows("visual", {"COOLANT_LEAK": ""}, s)) for s in range(N))
        self.assertTrue(N * 0.3 < hits < N * 0.7, hits)
        hits = sum(bool(bad_rows("visual", {"FUSE_BLOWN": "fan"}, s)) for s in range(N))
        self.assertLess(hits, N * 0.3)

    def test_plug_gap_norm_depends_on_engine(self) -> None:
        vw = VehicleContext("Polo", "CFNA", 1598, 50_000)
        lada = VehicleContext("Granta", "11186", 1596, 50_000)
        vw_norm = run("plugs", {}, 1, vw).readings[0].norm
        lada_norm = run("plugs", {}, 1, lada).readings[0].norm
        self.assertNotEqual(vw_norm, lada_norm)


if __name__ == "__main__":
    unittest.main()
