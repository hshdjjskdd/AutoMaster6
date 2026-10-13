"""Тесты текстов диагностики (без БД и aiogram)."""

import unittest
from datetime import UTC, datetime, timedelta

from app.game_data.diagnostic_checks import CHECKS
from app.schemas import (
    CheckOption,
    CheckRunView,
    ConclusionFault,
    ConclusionResult,
    DiagnosticOverview,
    ReadingView,
    ToolOption,
)
from app.game_data.enums import OrderStatus
from app import texts_diagnostics as td

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def make_run(flag: str = "warn") -> CheckRunView:
    return CheckRunView(
        run_no=2, check_code="battery", title="Напряжение АКБ", emoji="🔋",
        tool_title="Мультиметр", tool_owned=False, minutes=5, cost=150,
        readings=(
            ReadingView(label="Напряжение покоя", value="11.90", unit="В", norm="12.40–12.80", flag=flag),
            ReadingView(label="Заметка <b>", value="x&y", flag="info", note="примечание"),
        ),
        interpretation="Подсказка", created_at=NOW,
    )


class TextTests(unittest.TestCase):
    def test_run_shows_values_norms_cost_and_escapes_html(self) -> None:
        text = td.render_run(make_run(), fresh=True)
        self.assertIn("11.90", text)
        self.assertIn("норма 12.40–12.80 В", text)
        self.assertIn("⚠️", text)
        self.assertIn("150", text)
        self.assertIn("аренда", text)
        self.assertIn("&lt;b&gt;", text)
        self.assertIn("Отклонений от нормы: 1", text)
        self.assertLess(len(text), 4096)

    def test_run_all_ok(self) -> None:
        text = td.render_run(make_run("ok"))
        self.assertIn("Все значения в пределах нормы", text)

    def test_journal_lists_runs_and_totals(self) -> None:
        text = td.render_journal(7, [make_run(), make_run("ok")])
        self.assertIn("заказ №7", text)
        self.assertIn("отклонений: 1", text)
        self.assertIn("в норме", text)
        self.assertIn("Итого: 10 мин", text)
        self.assertIn("Пока пусто", td.render_journal(7, []))

    def test_journal_truncates_long_history(self) -> None:
        runs = [make_run().model_copy(update={"run_no": i}) for i in range(1, 31)]
        text = td.render_journal(1, runs)
        self.assertIn("последние 10 из 30", text)
        self.assertLess(len(text), 4096)

    def test_menu(self) -> None:
        overview = DiagnosticOverview(
            order_id=5, order_status=OrderStatus.DIAGNOSTICS, car_title="LADA Granta, 2016",
            plate="А123ВС 77", complaint="Не заводится", runs=3, minutes_spent=95,
            money_spent=500, balance=14_500, deadline_at=NOW + timedelta(hours=2),
            concluded=False, can_run=True, options=(),
        )
        text = td.render_menu(overview, now=NOW)
        self.assertIn("1 ч 35 мин", text)
        self.assertIn("2 ч", text)
        self.assertIn("Не заводится", text)
        late = overview.model_copy(update={"deadline_at": NOW - timedelta(minutes=1)})
        self.assertIn("Срок заказа вышел", td.render_menu(late, now=NOW))
        done = overview.model_copy(update={"concluded": True, "can_run": False})
        self.assertIn("Заключение вынесено", td.render_menu(done, now=NOW))

    def test_check_info_rented_vs_owned(self) -> None:
        check = CHECKS[1]
        base = dict(
            code=check.code, title=check.title, emoji=check.emoji, group=check.group,
            description=check.description, interpretation=check.interpretation,
            minutes=check.minutes, tool_code=check.tool_code, tool_title="Мультиметр", times_done=0,
        )
        rented = CheckOption(fee=150, tool_owned=False, **base)  # type: ignore[arg-type]
        owned = CheckOption(fee=0, tool_owned=True, **base)  # type: ignore[arg-type]
        self.assertIn("аренду", td.render_check_info(rented, runs=0))
        text = td.render_check_info(owned, runs=0)
        self.assertIn("есть в мастерской", text)
        self.assertIn("бесплатно", text)

    def test_tools_and_conclusion(self) -> None:
        tools = [
            ToolOption(code="MULTIMETER", title="Мультиметр", owned=True, price=1200, required_level=1),
            ToolOption(code="FUEL-PRESSURE-KIT", title="Манометр", owned=False, price=4500, required_level=2),
        ]
        text = td.render_tools(tools)
        self.assertIn("✅ Мультиметр", text)
        self.assertIn("нужен уровень 2", text)
        result = ConclusionResult(
            order_id=3, faults=(ConclusionFault(code="BAT_WEAK", name="Изношенная АКБ", system="Электрика"),)
        )
        self.assertIn("Изношенная АКБ", td.render_conclusion_done(result))
        self.assertIn("Выбрано", td.render_conclusion_form([0]))


if __name__ == "__main__":
    unittest.main()
