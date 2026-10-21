"""An empty Source Warehouse (set_warehouse) gets the user's default."""

from __future__ import annotations

from unittest import mock

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase

from zatgo_core.events.default_source_warehouse import (
    autofill_enabled,
    default_source_warehouse,
    get_default_source_warehouse,
    set_source_warehouse,
)
from zatgo_core.services.vansalex_settings import resolve


class TestDefaultSourceWarehouse(IntegrationTestCase):
    def setUp(self) -> None:
        frappe.set_user("Administrator")
        self.default = resolve()["warehouse"]
        if not self.default:
            self.skipTest("no default warehouse resolvable on this site")

    def _doc(self, **kw):
        return frappe._dict(docstatus=0, company=kw.pop("company", None), **kw)

    def test_empty_gets_default(self) -> None:
        doc = self._doc(set_warehouse=None)
        set_source_warehouse(doc)
        self.assertEqual(doc.set_warehouse, self.default)

    def test_chosen_warehouse_kept(self) -> None:
        doc = self._doc(set_warehouse="Chosen - X")
        set_source_warehouse(doc)
        self.assertEqual(doc.set_warehouse, "Chosen - X")

    def test_submitted_doc_untouched(self) -> None:
        doc = frappe._dict(docstatus=1, set_warehouse=None, company=None)
        set_source_warehouse(doc)
        self.assertIsNone(doc.set_warehouse)

    def test_other_company_not_defaulted(self) -> None:
        self.assertIsNone(default_source_warehouse("No Such Company"))


SETTINGS, FIELD = "ZG System Settings", "autofill_source_warehouse"


class TestAutofillSwitch(IntegrationTestCase):
    """ZG System Settings -> Auto-fill Source Warehouse on Documents: on by default (and where never saved),
    off leaves the field blank in the form and on save."""

    def setUp(self) -> None:
        frappe.set_user("Administrator")
        # Independent of the site's own default-warehouse configuration: any real warehouse, resolver patched.
        self.default = frappe.db.get_value("Warehouse", {"is_group": 0, "disabled": 0}, "name")
        if not self.default:
            self.skipTest("no warehouse on this site")
        patcher = mock.patch("zatgo_core.events.default_source_warehouse.resolve", return_value={"warehouse": self.default})
        patcher.start()
        self.addCleanup(patcher.stop)
        rows = frappe.db.sql("SELECT value FROM `tabSingles` WHERE doctype = %s AND field = %s", (SETTINGS, FIELD))
        self._had_row, self._value = bool(rows), (rows[0][0] if rows else None)
        self.addCleanup(self._restore)

    def _restore(self) -> None:
        frappe.db.sql("DELETE FROM `tabSingles` WHERE doctype = %s AND field = %s", (SETTINGS, FIELD))
        if self._had_row:
            frappe.db.sql(
                "INSERT INTO `tabSingles` (doctype, field, value) VALUES (%s, %s, %s)", (SETTINGS, FIELD, self._value)
            )

    def _set(self, value) -> None:
        frappe.db.sql("DELETE FROM `tabSingles` WHERE doctype = %s AND field = %s", (SETTINGS, FIELD))
        if value is not None:
            frappe.db.sql("INSERT INTO `tabSingles` (doctype, field, value) VALUES (%s, %s, %s)", (SETTINGS, FIELD, value))

    def _doc(self, **kw):
        return frappe._dict(docstatus=0, company=kw.pop("company", None), **kw)

    def test_never_saved_means_on(self) -> None:
        self._set(None)
        self.assertTrue(autofill_enabled())
        doc = self._doc(set_warehouse=None)
        set_source_warehouse(doc)
        self.assertEqual(doc.set_warehouse, self.default)

    def test_ticked_fills_on_save_and_in_the_form(self) -> None:
        self._set("1")
        doc = self._doc(set_warehouse=None)
        set_source_warehouse(doc)
        self.assertEqual(doc.set_warehouse, self.default)
        self.assertEqual(get_default_source_warehouse(None), self.default)

    def test_unticked_leaves_it_blank_on_save_and_in_the_form(self) -> None:
        self._set("0")
        self.assertFalse(autofill_enabled())
        doc = self._doc(set_warehouse=None)
        set_source_warehouse(doc)
        self.assertIsNone(doc.set_warehouse)
        self.assertIsNone(get_default_source_warehouse(None))

    def test_unticked_never_touches_a_chosen_warehouse(self) -> None:
        self._set("0")
        doc = self._doc(set_warehouse="Chosen - X")
        set_source_warehouse(doc)
        self.assertEqual(doc.set_warehouse, "Chosen - X")

    def test_the_warehouse_picker_still_knows_the_default(self) -> None:
        """default_source_warehouse() is also the picker's "always offer this one" -- not switched by the setting."""
        self._set("0")
        self.assertEqual(default_source_warehouse(None), self.default)

    def test_the_setting_exists_and_is_on_by_default(self) -> None:
        df = frappe.get_meta(SETTINGS).get_field(FIELD)
        self.assertIsNotNone(df)
        self.assertEqual(str(df.default), "1")
        self.assertEqual(df.fieldtype, "Check")

    def test_the_patch_ticks_the_box_where_it_never_existed_and_keeps_an_explicit_off(self) -> None:
        from zatgo_core.patches.v0_4_5 import autofill_source_warehouse_on as patch

        self._set(None)  # a site that predates the field: no row, the form would show it unticked
        patch.execute()
        rows = frappe.db.sql("SELECT value FROM `tabSingles` WHERE doctype = %s AND field = %s", (SETTINGS, FIELD))
        self.assertEqual(rows[0][0], "1")
        self._set("0")  # an administrator who unticked it
        patch.execute()
        rows = frappe.db.sql("SELECT value FROM `tabSingles` WHERE doctype = %s AND field = %s", (SETTINGS, FIELD))
        self.assertEqual(rows[0][0], "0")
