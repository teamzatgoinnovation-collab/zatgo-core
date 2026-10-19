"""An empty Source Warehouse (set_warehouse) gets the user's default."""

from __future__ import annotations

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase

from zatgo_core.events.default_source_warehouse import (
    default_source_warehouse,
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
