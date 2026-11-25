"""The rollout usage audit: read-only, and right about what an edition would refuse."""

from __future__ import annotations

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import random_string

from zatgo_core.licensing import usage_audit
from zatgo_core.tests.integration._fixtures import get_or_create_test_company


class TestUsageAudit(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        frappe.set_user("Administrator")
        company = get_or_create_test_company()
        abbr = frappe.db.get_value("Company", company, "abbr")
        warehouse = f"UsageAudit - {abbr}"
        if not frappe.db.exists("Warehouse", warehouse):
            frappe.get_doc({"doctype": "Warehouse", "warehouse_name": "UsageAudit", "company": company}).insert(
                ignore_permissions=True)
        item = f"USAGE-AUDIT-{random_string(5).upper()}"
        frappe.get_doc({"doctype": "Item", "item_code": item, "item_name": item, "stock_uom": "Nos",
                        "item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
                        "is_stock_item": 1}).insert(ignore_permissions=True)
        frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "company": company,
                        "items": [{"item_code": item, "qty": 1, "t_warehouse": warehouse, "basic_rate": 5}]}).insert(
            ignore_permissions=True).submit()

    def test_a_sales_edition_would_refuse_this_sites_stock_entries(self) -> None:
        data = usage_audit.audit("sales", days=1)
        refused = {(r["doctype"], tuple((r["when"] or {}).items())): r for r in data["refused"]}
        key = ("Stock Entry", (("purpose", "Material Receipt"),))
        self.assertIn(key, refused)
        self.assertGreaterEqual(refused[key]["created"], 1)
        self.assertEqual(refused[key]["needs_one_of"], ["inventory.stock_receipt"])
        self.assertEqual(data["totals"]["refused_doctypes"], len(data["refused"]))

    def test_an_edition_that_covers_the_use_refuses_nothing_for_it(self) -> None:
        data = usage_audit.audit("enterprise", days=1)
        self.assertFalse([r for r in data["refused"] if r["doctype"] == "Stock Entry"])
        self.assertTrue([r for r in data["allowed"] if r["doctype"] == "Stock Entry"])

    def test_it_only_reads(self) -> None:
        before = (frappe.db.count("Stock Entry"), frappe.db.count("Audit Log"))
        usage_audit.audit("sales", days=30)
        usage_audit.report("sales", 30)
        self.assertEqual((frappe.db.count("Stock Entry"), frappe.db.count("Audit Log")), before)

    def test_unknown_edition_and_feature_maps(self) -> None:
        with self.assertRaises(ValueError):
            usage_audit.audit("no_such_edition")
        data = usage_audit.audit(features={"inventory.stock_receipt": []}, days=1)
        self.assertFalse([r for r in data["refused"]
                          if r["doctype"] == "Stock Entry" and r["when"] == {"purpose": "Material Receipt"}])
