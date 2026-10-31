"""MyBis administrator limits (ZG MyBis Settings): what `sanitize` makes of stored values, and that the DocType and the code
agree on the keys they share. No database rows are read or written."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from zatgo_core.services.mybis import insights, period, reports
from zatgo_core.zatgo_core.doctype.zg_mybis_settings import zg_mybis_settings as settings

DOCTYPE_JSON = Path(settings.__file__).with_suffix(".json")
OPEN = {
    "min_refresh_minutes": 0,
    "min_alert_severity": "low",
    "export_formats": ["csv", "xlsx", "pdf"],
    "kpis": list(settings.KPI_KEYS),
    "offline_copy": True,
}


def _fields() -> dict[str, dict]:
    return {f["fieldname"]: f for f in json.loads(DOCTYPE_JSON.read_text())["fields"]}


class TestSanitize(unittest.TestCase):
    def test_nothing_stored_restricts_nothing(self):
        self.assertEqual(settings.sanitize({}), OPEN)
        self.assertEqual(settings.sanitize(None), OPEN)

    def test_stored_values_become_limits(self):
        got = settings.sanitize(
            {
                "min_refresh_minutes": "15",
                "min_alert_severity": "high",
                "disable_export_pdf": "1",
                "hide_kpi_net_profit": "1",
                "hide_kpi_payables": "1",
                "disable_offline_copy": "1",
            }
        )
        self.assertEqual(got["min_refresh_minutes"], 15)
        self.assertEqual(got["min_alert_severity"], "high")
        self.assertEqual(got["export_formats"], ["csv", "xlsx"])
        self.assertNotIn("net_profit", got["kpis"])
        self.assertNotIn("payables", got["kpis"])
        self.assertEqual(len(got["kpis"]), len(settings.KPI_KEYS) - 2)
        self.assertFalse(got["offline_copy"])

    def test_unticked_values_do_not_restrict(self):
        raw = {f"hide_kpi_{k}": "0" for k in settings.KPI_KEYS}
        raw |= {f"disable_export_{f}": 0 for f in settings.EXPORT_FORMATS}
        raw |= {"disable_offline_copy": "0", "min_refresh_minutes": "0", "min_alert_severity": "low"}
        self.assertEqual(settings.sanitize(raw), OPEN)

    def test_garbage_means_no_restriction(self):
        got = settings.sanitize(
            {"min_refresh_minutes": "soon", "min_alert_severity": "urgent", "hide_kpi_total_sales": "yes", "disable_export_csv": "maybe"}
        )
        self.assertEqual(got, OPEN)

    def test_the_refresh_limit_stays_in_range(self):
        self.assertEqual(settings.sanitize({"min_refresh_minutes": "99999"})["min_refresh_minutes"], settings.MAX_REFRESH_MINUTES)
        self.assertEqual(settings.sanitize({"min_refresh_minutes": "-5"})["min_refresh_minutes"], 0)

    def test_every_card_hidden_is_a_mistake_not_a_policy(self):
        raw = {f"hide_kpi_{k}": "1" for k in settings.KPI_KEYS}
        self.assertEqual(settings.sanitize(raw)["kpis"], list(settings.KPI_KEYS))

    def test_all_formats_off_is_allowed(self):
        raw = {f"disable_export_{f}": "1" for f in settings.EXPORT_FORMATS}
        self.assertEqual(settings.sanitize(raw)["export_formats"], [])


class TestDoctypeAgreesWithTheCode(unittest.TestCase):
    def test_severities_and_formats_are_the_ones_the_services_use(self):
        self.assertEqual(settings.SEVERITIES, tuple(insights.SEVERITIES))
        self.assertEqual(set(settings.EXPORT_FORMATS), set(reports.FORMATS))

    def test_presets_are_the_ones_the_period_service_resolves(self):
        options = _fields()["default_preset"]["options"].split("\n")
        self.assertEqual(options, [p for p in period.PRESETS if p != "custom"])

    def test_severity_options_run_from_the_floor_up(self):
        self.assertEqual(_fields()["min_alert_severity"]["options"].split("\n"), list(reversed(settings.SEVERITIES)))

    def test_one_check_per_card_format_and_the_offline_copy(self):
        fields = _fields()
        expected = [f"hide_kpi_{k}" for k in settings.KPI_KEYS] + [f"disable_export_{f}" for f in settings.EXPORT_FORMATS]
        expected.append("disable_offline_copy")
        for name in expected:
            self.assertEqual(fields[name]["fieldtype"], "Check", name)

    def test_every_check_restricts(self):
        """A Check on a Single reads 0 until the form is saved, so a limit must be a tick that *adds* a restriction."""
        for name, f in _fields().items():
            if f["fieldtype"] == "Check":
                self.assertTrue(name.startswith(("hide_", "disable_")), f"{name} would restrict by default on a site that never saved")
                self.assertNotIn("default", f, name)

    def test_the_form_starts_with_its_tab(self):
        order = json.loads(DOCTYPE_JSON.read_text())["field_order"]
        self.assertEqual(order[0], "general_tab")
        self.assertEqual(_fields()["general_tab"]["fieldtype"], "Tab Break")
        self.assertEqual(sum(1 for f in _fields().values() if f["fieldtype"] == "Tab Break"), 1)


if __name__ == "__main__":
    unittest.main()
