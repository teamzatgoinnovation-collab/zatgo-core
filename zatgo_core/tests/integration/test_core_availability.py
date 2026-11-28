"""services/core/availability.py: one answer per app and industry, the same one the existing gates give."""

from __future__ import annotations

from unittest.mock import patch

from frappe.tests.classes.integration_test_case import IntegrationTestCase

from zatgo_core.industries import gate, registry
from zatgo_core.services import app_catalog, app_state
from zatgo_core.services.core import availability


class TestAvailability(IntegrationTestCase):
    def test_apps_agree_with_app_state(self) -> None:
        for app in app_catalog.catalog():
            key = app["key"]
            self.assertEqual(availability.is_available(key), app_state.is_on(key), key)

    def test_industries_agree_with_the_industry_gate(self) -> None:
        enabled = gate.enabled_keys()
        for key in registry.INDUSTRIES:
            if app_catalog.get(key) is None:  # an app of the same key would win in `of`
                self.assertEqual(availability.is_available(key), key in enabled, key)

    def test_unknown_key(self) -> None:
        found = availability.of("no_such_module")
        self.assertFalse(found.known)
        self.assertFalse(found.available)
        self.assertIn("not a ZatGo app", found.reason)

    def test_switched_off_app_says_so(self) -> None:
        with patch.object(app_state, "switch_on", return_value=False):
            found = availability.app("vansalex")
        self.assertFalse(found.available)
        self.assertTrue(found.licensed)
        self.assertIn("switched off", found.reason)

    def test_unlicensed_app_says_so(self) -> None:
        with (
            patch.object(app_state, "switch_on", return_value=True),
            patch("zatgo_core.licensing.gate.app_licensed", return_value=False),
        ):
            found = availability.app("vansalex")
        self.assertTrue(found.enabled)
        self.assertFalse(found.available)
        self.assertIn("licence", found.reason)

    def test_missing_requirement_is_reported_not_switched_on(self) -> None:
        with patch.object(app_state, "is_on", side_effect=lambda key: key != "vansalex"):
            found = availability.app("vansalex_web")
        self.assertIn("vansalex", found.missing_requirements)

    def test_switch_on_matches_is_on_when_unlicensed_is_ignored(self) -> None:
        for app in app_catalog.catalog():
            key = app["key"]
            with patch("zatgo_core.licensing.gate.app_licensed", return_value=True):
                self.assertEqual(app_state.switch_on(key), app_state.is_on(key), key)

    def test_summary_covers_every_app_and_industry(self) -> None:
        summary = availability.summary()
        for app in app_catalog.catalog():
            self.assertIn(app["key"], summary)
        for key in registry.INDUSTRIES:
            self.assertIn(key, summary)
        self.assertEqual(set(summary["vansalex"]), {"key", "kind", "known", "installed", "enabled", "licensed",
                                                     "module_enabled", "missing_requirements", "available", "reason"})
