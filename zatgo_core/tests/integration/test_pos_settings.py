"""ZatGo POS as a switchable app: on unless switched off, its settings reach the POS, off answers the gate."""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase

from zatgo_core.api.v1 import pos_settings as pos_settings_api
from zatgo_core.industries import gate
from zatgo_core.services import app_catalog, app_state, pos_settings
from zatgo_core.services.ui_apps import SETTINGS
from zatgo_core.tests.integration.test_industries import IndustryTestBase, _set_industries


def gate_keys() -> set[str]:
    frappe.clear_document_cache(gate.SETTINGS, gate.SETTINGS)
    return gate.enabled_keys()


class TestPOSSettings(IntegrationTestCase):
    def setUp(self) -> None:
        frappe.set_user("Administrator")
        # A Check on a Single reads 0 when nothing is stored: remember "nothing stored" so tearDown does not store a 0 (= app off).
        self.switch_before = frappe.db.sql(
            "select value from tabSingles where doctype = %s and field = 'enable_zatgo_pos'", (SETTINGS,)
        )
        # A never-saved Single reads 0 for these; restore "nothing stored" as nothing stored, not as 0.
        self.settings_before = {
            f: frappe.db.sql("select value from tabSingles where doctype = %s and field = %s", (pos_settings.SETTINGS, f))
            for f in ("allow_discounts", "max_discount_percent", "print_copies", "pos_type")
        }

    def tearDown(self) -> None:
        if self.switch_before:
            frappe.db.set_single_value(SETTINGS, "enable_zatgo_pos", self.switch_before[0][0])
        else:
            frappe.db.sql("delete from tabSingles where doctype = %s and field = 'enable_zatgo_pos'", (SETTINGS,))
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

    def test_counter_defaults_and_values(self) -> None:
        # nothing stored: the DocType defaults (80mm, grid, price change allowed, Phase 1 QR)
        for field in ("paper_size", "product_view", "allow_price_change", "invoice_qr"):
            frappe.db.sql("delete from tabSingles where doctype = %s and field = %s", (pos_settings.SETTINGS, field))
        frappe.clear_document_cache(pos_settings.SETTINGS, pos_settings.SETTINGS)
        self.assertEqual(
            pos_settings.effective()["counter"],
            {"paper_size": "80mm", "product_view": "grid", "allow_price_change": 1, "invoice_qr": "phase1"},
        )
        doc = frappe.get_doc(pos_settings.SETTINGS)
        doc.paper_size, doc.product_view, doc.allow_price_change, doc.invoice_qr = "A4", "Row", 1, "Off"
        doc.save()
        self.assertEqual(
            pos_settings.effective()["counter"],
            {"paper_size": "A4", "product_view": "row", "allow_price_change": 1, "invoice_qr": "off"},
        )
        for field in ("paper_size", "product_view", "allow_price_change", "invoice_qr"):
            frappe.db.sql("delete from tabSingles where doctype = %s and field = %s", (pos_settings.SETTINGS, field))
        frappe.clear_document_cache(pos_settings.SETTINGS, pos_settings.SETTINGS)

    def test_only_the_pos_screen_by_default_and_pages_follow_the_switches(self) -> None:
        fields = [f"page_{k}" for k in pos_settings.PAGE_KEYS]
        for field in fields:
            frappe.db.sql("delete from tabSingles where doctype = %s and field = %s", (pos_settings.SETTINGS, field))
        frappe.clear_document_cache(pos_settings.SETTINGS, pos_settings.SETTINGS)
        # nothing stored: every page is off
        self.assertEqual(pos_settings.effective()["pages"], {k: 0 for k in pos_settings.PAGE_KEYS})
        doc = frappe.get_doc(pos_settings.SETTINGS)
        doc.page_reports, doc.page_dashboard = 1, 1
        doc.save()
        got = pos_settings.effective()["pages"]
        self.assertEqual({k for k, v in got.items() if v}, {"reports", "dashboard"})
        for field in fields:
            frappe.db.sql("delete from tabSingles where doctype = %s and field = %s", (pos_settings.SETTINGS, field))
        frappe.clear_document_cache(pos_settings.SETTINGS, pos_settings.SETTINGS)

    def test_restaurant_sites_keep_their_pages_on_upgrade(self) -> None:
        from unittest.mock import patch

        from zatgo_core.patches.v0_5_2 import keep_pages_for_restaurant_sites as p

        fields = [f"page_{k}" for k in pos_settings.PAGE_KEYS]

        def clear() -> None:
            for field in fields:
                frappe.db.sql("delete from tabSingles where doctype = %s and field = %s", (pos_settings.SETTINGS, field))
            frappe.clear_document_cache(pos_settings.SETTINGS, pos_settings.SETTINGS)

        clear()
        with patch("zatgo_core.industries.gate.is_enabled", return_value=False):
            p.execute()
        self.assertEqual(sum(pos_settings.effective()["pages"].values()), 0)  # not a restaurant site: POS only
        with patch("zatgo_core.industries.gate.is_enabled", return_value=True):
            p.execute()
        self.assertEqual(sum(pos_settings.effective()["pages"].values()), len(fields))  # restaurant site: all kept
        frappe.db.set_single_value(pos_settings.SETTINGS, "page_reports", 0)  # the admin's own later choice
        frappe.clear_document_cache(pos_settings.SETTINGS, pos_settings.SETTINGS)
        with patch("zatgo_core.industries.gate.is_enabled", return_value=True):
            p.execute()
        self.assertEqual(pos_settings.effective()["pages"]["reports"], 0)  # a stored choice is never overwritten
        clear()

    def test_prices_and_tax_mode(self) -> None:
        frappe.db.sql("delete from tabSingles where doctype = %s and field = %s", (pos_settings.SETTINGS, "tax_mode"))
        frappe.clear_document_cache(pos_settings.SETTINGS, pos_settings.SETTINGS)
        self.assertIsNone(pos_settings.tax_inclusive_override())  # never chosen: follow the template

        def invoice():
            return frappe._dict(
                taxes=[
                    frappe._dict(charge_type="On Net Total", included_in_print_rate=0),
                    frappe._dict(charge_type="Actual", included_in_print_rate=0),
                ]
            )

        doc = frappe.get_doc(pos_settings.SETTINGS)
        doc.tax_mode = "Prices include tax"
        doc.save()
        self.assertIs(pos_settings.tax_inclusive_override(), True)
        si = invoice()
        pos_settings.apply_tax_mode(si)
        self.assertEqual([r.included_in_print_rate for r in si.taxes], [1, 0])  # an Actual row cannot be inclusive
        doc.tax_mode = "Prices exclude tax"
        doc.save()
        self.assertIs(pos_settings.tax_inclusive_override(), False)
        si = invoice()
        si.taxes[0].included_in_print_rate = 1  # the template said inclusive; the site chose exclusive
        pos_settings.apply_tax_mode(si)
        self.assertEqual([r.included_in_print_rate for r in si.taxes], [0, 0])
        doc.tax_mode = "Follow tax template"
        doc.save()
        si = invoice()
        si.taxes[0].included_in_print_rate = 1
        pos_settings.apply_tax_mode(si)
        self.assertEqual(si.taxes[0].included_in_print_rate, 1)  # untouched
        # the POS profile reports what the site chose, so the app and the invoice agree
        doc.tax_mode = "Prices exclude tax"
        doc.save()
        from zatgo_core.api.v1 import pos_profile

        got = pos_profile.get()
        self.assertEqual(got["data"]["tax_inclusive"], 0)
        frappe.db.sql("delete from tabSingles where doctype = %s and field = %s", (pos_settings.SETTINGS, "tax_mode"))
        frappe.clear_document_cache(pos_settings.SETTINGS, pos_settings.SETTINGS)

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


class TestPOSType(IndustryTestBase):
    """POS Type (Restaurant / Supermarket) of ZatGo POS Settings: decides the POS mode, switches its industry on."""

    def setUp(self) -> None:
        super().setUp()  # every industry off
        rows = frappe.db.sql("select value from tabSingles where doctype = %s and field = 'pos_type'", pos_settings.SETTINGS)
        self.type_before = rows[0][0] if rows else None
        self._store_type(None)

    def tearDown(self) -> None:
        self._store_type(self.type_before)
        super().tearDown()

    @staticmethod
    def _store_type(value: str | None) -> None:
        frappe.db.sql("delete from tabSingles where doctype = %s and field = 'pos_type'", pos_settings.SETTINGS)
        if value:
            frappe.db.set_single_value(pos_settings.SETTINGS, "pos_type", value)
        frappe.clear_document_cache(pos_settings.SETTINGS, pos_settings.SETTINGS)

    def _choose(self, pos_type: str):
        doc = frappe.get_doc(pos_settings.SETTINGS)
        doc.pos_type = pos_type
        doc.save()
        return doc

    def test_with_no_choice_the_industries_decide_as_before(self) -> None:
        self.assertIsNone(pos_settings.pos_mode())
        _set_industries("supermarket")
        self.assertEqual((pos_settings.pos_type(), pos_settings.pos_mode()), ("Supermarket", "retail"))
        _set_industries("supermarket", "restaurant")
        self.assertEqual((pos_settings.pos_type(), pos_settings.pos_mode()), ("Restaurant", "restaurant"))

    def test_a_chosen_type_wins_over_both_industries_being_on(self) -> None:
        _set_industries("supermarket", "restaurant")
        self._store_type("Supermarket")
        self.assertEqual(pos_settings.pos_mode(), "retail")
        self._store_type("Restaurant")
        self.assertEqual(pos_settings.pos_mode(), "restaurant")

    def test_a_chosen_type_whose_industry_is_off_leaves_the_pos_with_nothing(self) -> None:
        _set_industries("restaurant")
        self._store_type("Supermarket")
        self.assertIsNone(pos_settings.pos_mode())

    def test_saving_a_type_switches_its_industry_on_and_keeps_the_other(self) -> None:
        _set_industries("restaurant")
        self._choose("Supermarket")
        self.assertEqual(gate_keys(), {"restaurant", "supermarket"})
        self.assertEqual(pos_settings.pos_mode(), "retail")
        self.assertEqual(pos_settings.effective()["pos_mode"], "retail")

    def test_the_form_shows_the_derived_type_when_none_was_chosen(self) -> None:
        _set_industries("supermarket")
        doc = frappe.get_doc(pos_settings.SETTINGS)
        doc.run_method("onload")
        self.assertEqual(doc.pos_type, "Supermarket")

    def test_only_a_system_manager_may_change_the_type(self) -> None:
        _set_industries("restaurant")
        self._store_type("Restaurant")
        doc = frappe.get_doc(pos_settings.SETTINGS)
        doc.pos_type = "Supermarket"
        with patch("zatgo_core.services.app_authority.can_switch", return_value=False):
            self.assertRaises(frappe.PermissionError, doc.save)
        self.assertEqual(gate_keys(), {"restaurant"})

    def test_saving_other_fields_without_the_right_to_switch_is_fine(self) -> None:
        _set_industries("restaurant")
        doc = frappe.get_doc(pos_settings.SETTINGS)
        doc.print_copies = 2
        with patch("zatgo_core.services.app_authority.can_switch", return_value=False):
            doc.save()  # no type picked: nothing to switch
        self.assertEqual(pos_settings.pos_type(), "Restaurant")
        self.assertIsNone(pos_settings._chosen_type())

    def test_confirming_the_shown_type_is_not_a_change(self) -> None:
        _set_industries("supermarket")
        doc = frappe.get_doc(pos_settings.SETTINGS)
        doc.run_method("onload")  # the form shows Supermarket and sends it back
        with patch("zatgo_core.services.app_authority.can_switch", return_value=False):
            doc.save()
        self.assertEqual(pos_settings._chosen_type(), "Supermarket")

    def test_an_unavailable_industry_refuses_the_type(self) -> None:
        with patch("zatgo_core.industries.gate.validate_selection", side_effect=frappe.ValidationError("no stock module")):
            self.assertRaises(frappe.ValidationError, self._choose, "Supermarket")

    def test_cafe_and_general_retail_run_on_the_two_engines_with_their_own_vertical(self) -> None:
        _set_industries("restaurant", "supermarket")
        for chosen, mode, vertical in (
            ("Restaurant", "restaurant", "restaurant"),
            ("Cafe", "restaurant", "cafe"),
            ("Supermarket", "retail", "supermarket"),
            ("General Retail", "retail", "general"),
        ):
            self._store_type(chosen)
            self.assertEqual((pos_settings.pos_mode(), pos_settings.pos_vertical()), (mode, vertical), chosen)
            self.assertEqual(pos_settings.effective()["pos_vertical"], vertical)

    def test_choosing_cafe_switches_the_restaurant_industry_on(self) -> None:
        self._choose("Cafe")
        self.assertIn("restaurant", gate_keys())
        self.assertEqual(pos_settings.pos_vertical(), "cafe")

    def test_pharmacy_and_electrical_are_listed_but_cannot_be_chosen(self) -> None:
        options = frappe.get_meta(pos_settings.SETTINGS).get_field("pos_type").options.split("\n")
        for coming in pos_settings.COMING_SOON:
            self.assertIn(coming, options)
            self.assertRaises(frappe.ValidationError, self._choose, coming)
        self.assertIsNone(pos_settings._chosen_type())

    def test_with_no_choice_the_vertical_follows_the_industries(self) -> None:
        _set_industries("supermarket")
        self.assertEqual(pos_settings.pos_vertical(), "supermarket")
        _set_industries()
        self.assertIsNone(pos_settings.pos_vertical())
