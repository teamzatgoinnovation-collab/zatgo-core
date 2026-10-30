"""ZatGo POS as a switchable app: on unless switched off, its settings reach the POS, off answers the gate."""

from __future__ import annotations

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase

from zatgo_core.api.v1 import pos_settings as pos_settings_api
from zatgo_core.services import app_catalog, app_state, pos_settings
from zatgo_core.services.ui_apps import SETTINGS


class TestPOSSettings(IntegrationTestCase):
    def setUp(self) -> None:
        frappe.set_user("Administrator")
        self.switch_before = frappe.db.get_single_value(SETTINGS, "enable_zatgo_pos")
        # A never-saved Single reads 0 for these; restore "nothing stored" as nothing stored, not as 0.
        self.settings_before = {
            f: frappe.db.sql("select value from tabSingles where doctype = %s and field = %s", (pos_settings.SETTINGS, f))
            for f in ("allow_discounts", "max_discount_percent", "print_copies")
        }

    def tearDown(self) -> None:
        frappe.db.set_single_value(SETTINGS, "enable_zatgo_pos", self.switch_before)
        for field, rows in self.settings_before.items():
            if rows:
                frappe.db.set_single_value(pos_settings.SETTINGS, field, rows[0][0])
            else:
                frappe.db.sql("delete from tabSingles where doctype = %s and field = %s", (pos_settings.SETTINGS, field))
        frappe.clear_document_cache(SETTINGS, SETTINGS)
        frappe.clear_document_cache(pos_settings.SETTINGS, pos_settings.SETTINGS)
        frappe.set_user("Administrator")

    def test_it_is_a_catalog_app_with_a_default_on_switch_and_a_workspace(self) -> None:
        app = app_catalog.get("zatgo_pos")
        self.assertEqual(app["switch_field"], "enable_zatgo_pos")
        self.assertTrue(app["default_on"])
        self.assertTrue(frappe.get_meta(SETTINGS).has_field("enable_zatgo_pos"))
        self.assertTrue(frappe.db.exists("Workspace", "ZatGo POS"))
        self.assertTrue(frappe.get_meta(pos_settings.SETTINGS).issingle)

    def test_settings_are_delivered_as_set(self) -> None:
        doc = frappe.get_doc(pos_settings.SETTINGS)
        doc.allow_discounts, doc.max_discount_percent, doc.print_copies = 1, 15, 2
        doc.save()
        got = pos_settings_api.get()
        self.assertTrue(got["success"])
        self.assertEqual(got["data"]["max_discount_percent"], 15)
        self.assertEqual(got["data"]["print_copies"], 2)

    def test_no_discounts_means_a_zero_cap(self) -> None:
        doc = frappe.get_doc(pos_settings.SETTINGS)
        doc.allow_discounts, doc.max_discount_percent = 0, 40
        doc.save()
        self.assertEqual(pos_settings.effective()["max_discount_percent"], 0)

    def test_bad_values_are_refused(self) -> None:
        doc = frappe.get_doc(pos_settings.SETTINGS)
        doc.max_discount_percent = 120
        self.assertRaises(frappe.ValidationError, doc.save)
        doc.reload()
        doc.print_copies = 0
        self.assertRaises(frappe.ValidationError, doc.save)

    def test_off_refuses_the_settings_api(self) -> None:
        frappe.db.set_single_value(SETTINGS, "enable_zatgo_pos", 0)
        frappe.clear_document_cache(SETTINGS, SETTINGS)
        self.assertFalse(app_state.is_on("zatgo_pos"))
        self.assertRaises(frappe.PermissionError, pos_settings_api.get)
