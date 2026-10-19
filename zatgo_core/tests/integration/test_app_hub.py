"""App Settings Hub: every sub-app module is in the catalog, switches derive
from it, and the hub API enforces System Manager."""

from __future__ import annotations

import os

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase

from zatgo_core.api.v1 import app_hub
from zatgo_core.services import app_catalog, bundled_apps
from zatgo_core.services.ui_apps import SETTINGS, SWITCH_FIELDS


class TestAppHub(IntegrationTestCase):
    def tearDown(self) -> None:
        frappe.set_user("Administrator")

    def test_every_module_with_doctypes_has_a_manifest(self) -> None:
        """A new module folder must ship app_manifest.py or it never shows in the hub."""
        modules = [m.strip() for m in open(frappe.get_app_path("zatgo_core", "modules.txt")) if m.strip()]
        for module in modules:
            folder = frappe.scrub(module)
            if folder == "zatgo_core":
                continue  # the core itself: plugins/manifests/core_apps.py
            if os.path.isdir(frappe.get_app_path("zatgo_core", folder, "doctype")):
                self.assertIn(folder, app_catalog.module_folders(), f"{folder} lacks app_manifest.py")

    def test_switches_derive_from_catalog(self) -> None:
        self.assertEqual(SWITCH_FIELDS, app_catalog.switch_fields())
        self.assertEqual(set(bundled_apps.BUNDLED), {a["key"] for a in app_catalog.catalog() if a["group"] == "bundled"})
        meta = frappe.get_meta(SETTINGS)
        for key, field in SWITCH_FIELDS.items():
            self.assertTrue(meta.has_field(field), f"{key}: {field} missing on {SETTINGS}")

    def test_listed_settings_doctypes_exist(self) -> None:
        for app in app_catalog.catalog():
            for dt, _label in app["settings"]:
                self.assertTrue(frappe.db.exists("DocType", dt), f"{app['key']}: {dt}")

    def test_hub_lists_every_app(self) -> None:
        frappe.set_user("Administrator")
        data = app_hub.get_hub()["data"]
        self.assertEqual({a["key"] for a in data["apps"]}, {a["key"] for a in app_catalog.catalog()})

    def test_non_manager_refused(self) -> None:
        frappe.set_user("Guest")
        self.assertFalse(app_hub.get_hub()["success"])
        self.assertFalse(app_hub.set_switch("tracker", 1)["success"])

    def test_set_switch_roundtrip_and_unknown_key(self) -> None:
        frappe.set_user("Administrator")
        before = frappe.db.get_single_value(SETTINGS, "enable_tracker")
        try:
            self.assertTrue(app_hub.set_switch("tracker", 1)["data"]["enabled"])
            self.assertFalse(app_hub.set_switch("tracker", 0)["data"]["enabled"])
            self.assertFalse(app_hub.set_switch("core_settings", 1)["success"])
        finally:
            frappe.db.set_single_value(SETTINGS, "enable_tracker", before or 0)
            frappe.clear_document_cache(SETTINGS, SETTINGS)
