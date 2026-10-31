"""Brand / theme / language live in the app that owns them (ZG Theme Settings, ZG Language Settings) and every reader
still gets the same keys (services/ui_settings.py, patches/v0_4_10)."""

from __future__ import annotations

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase

from zatgo_core.patches.v0_4_10 import move_brand_theme_language_to_apps as patch
from zatgo_core.services import ui_settings
from zatgo_core.services.settings_service import SettingsService

THEME = "ZG Theme Settings"
LANG = "ZG Language Settings"


def _stored(doctype: str, field: str):
    rows = frappe.db.sql("select value from tabSingles where doctype = %s and field = %s", (doctype, field))
    return rows[0][0] if rows else None


def _put(doctype: str, field: str, value) -> None:
    frappe.db.sql("delete from tabSingles where doctype = %s and field = %s", (doctype, field))
    if value is not None:
        frappe.db.set_single_value(doctype, field, value)
    frappe.clear_document_cache(doctype, doctype)


class TestAppSettingsMove(IntegrationTestCase):
    FIELDS = ((THEME, "brand_name"), (THEME, "theme"), (LANG, "language"), ("ZG System Settings", "brand_name"), ("ZG System Settings", "theme"), ("ZG System Settings", "language"))

    def setUp(self) -> None:
        frappe.set_user("Administrator")
        self._before = {key: _stored(*key) for key in self.FIELDS}

    def tearDown(self) -> None:
        for (doctype, field), value in self._before.items():
            _put(doctype, field, value)

    def test_the_apps_own_settings_are_what_readers_get(self) -> None:
        _put(THEME, "brand_name", "Acme")
        _put(THEME, "theme", "Dark")
        _put(LANG, "language", "ar")
        got = ui_settings.values()
        self.assertEqual((got["brand_name"], got["theme"], got["language"]), ("Acme", "Dark", "ar"))

    def test_the_system_settings_payload_keeps_its_keys_with_the_new_values(self) -> None:
        _put(THEME, "brand_name", "Acme")
        data = SettingsService.get_system_settings()
        for key in ("brand_name", "company_logo", "theme", "language"):
            self.assertIn(key, data)
        self.assertEqual(data["brand_name"], "Acme")

    def test_the_patch_copies_what_a_site_had_and_keeps_what_the_app_already_has(self) -> None:
        for doctype, field in ((THEME, "brand_name"), (THEME, "theme"), (LANG, "language")):
            _put(doctype, field, None)
        _put("ZG System Settings", "brand_name", "Kasib Asia")
        _put("ZG System Settings", "theme", "Light")
        _put(THEME, "theme", "Dark")  # already set in the app: kept
        patch.execute()
        self.assertEqual(_stored(THEME, "brand_name"), "Kasib Asia")
        self.assertEqual(_stored(THEME, "theme"), "Dark")
        self.assertEqual(_stored("ZG System Settings", "brand_name"), "Kasib Asia", "the old field is left alone")
        patch.execute()  # idempotent
        self.assertEqual(_stored(THEME, "brand_name"), "Kasib Asia")

    def test_the_old_fields_are_hidden_on_system_settings(self) -> None:
        meta = frappe.get_meta("ZG System Settings")
        for field in ("brand_name", "company_logo", "theme", "language"):
            self.assertTrue(meta.get_field(field).hidden, field)
