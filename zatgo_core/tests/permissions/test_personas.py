"""Access personas (Phase 8): what each may and may not do, tested on documents, lists, the ZatGo API and reports.
Visibility is not security: every refusal below is a server-side check."""

from __future__ import annotations

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import random_string

from zatgo_core.setup import ensure_role_profiles as personas
from zatgo_core.tests.integration._fixtures import get_or_create_test_company


class TestPersonas(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        frappe.set_user("Administrator")
        personas.ensure_role_profiles()
        cls.company = get_or_create_test_company()
        cls.tag = random_string(5).upper()
        cls.users = {}
        for key, profile in (("sales", "ZatGo Sales User"), ("manager", "ZatGo Sales Manager"), ("stock", "ZatGo Stock User"),
                             ("cold", "ZatGo Restricted Stock User"), ("admin", "ZatGo Administrator")):
            email = f"zg-persona-{key}-{cls.tag.lower()}@example.test"
            frappe.get_doc({"doctype": "User", "email": email, "first_name": key, "send_welcome_email": 0,
                            "role_profiles": [{"role_profile": profile}]}).insert(ignore_permissions=True)
            cls.users[key] = email
        leaf = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
        cls.frozen_group = frappe.get_doc({"doctype": "Item Group", "item_group_name": f"Frozen {cls.tag}",
                                           "parent_item_group": frappe.db.get_value("Item Group", {"is_group": 1}, "name")}
                                          ).insert(ignore_permissions=True).name
        cls.frozen_item = cls._item(f"FROZEN-{cls.tag}", cls.frozen_group)
        cls.other_item = cls._item(f"DRY-{cls.tag}", leaf)
        abbr = frappe.db.get_value("Company", cls.company, "abbr")
        cls.cold_store = cls._warehouse(f"Cold {cls.tag}", abbr)
        cls.dry_store = cls._warehouse(f"Dry {cls.tag}", abbr)
        personas.restrict_user(cls.users["cold"], item_groups=[cls.frozen_group], warehouses=[cls.cold_store])
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls) -> None:
        frappe.set_user("Administrator")
        for email in cls.users.values():
            frappe.delete_doc("User", email, force=True, ignore_permissions=True)
        frappe.db.commit()
        super().tearDownClass()

    @classmethod
    def _item(cls, code: str, group: str) -> str:
        return frappe.get_doc({"doctype": "Item", "item_code": code, "item_name": code, "item_group": group,
                               "stock_uom": "Nos", "is_stock_item": 1}).insert(ignore_permissions=True).name

    @classmethod
    def _warehouse(cls, label: str, abbr: str) -> str:
        return frappe.get_doc({"doctype": "Warehouse", "warehouse_name": label, "company": cls.company}
                              ).insert(ignore_permissions=True).name

    def tearDown(self) -> None:
        frappe.set_user("Administrator")

    def can(self, key: str, doctype: str, ptype: str, doc: str | None = None) -> bool:
        return bool(frappe.has_permission(doctype, ptype, doc=doc, user=self.users[key]))

    def test_profiles_exist_and_a_rerun_creates_none(self) -> None:
        for name in personas.PROFILES:
            self.assertTrue(frappe.db.exists("Role Profile", name), name)
        self.assertEqual(personas.ensure_role_profiles(), [])

    def test_sales_user(self) -> None:
        for doctype, ptype in (("Sales Invoice", "create"), ("Sales Order", "create"), ("Customer", "read"), ("Item", "read")):
            self.assertTrue(self.can("sales", doctype, ptype), f"{doctype} {ptype}")
        for doctype, ptype in (("Stock Entry", "create"), ("Journal Entry", "create"), ("Purchase Invoice", "create")):
            self.assertFalse(self.can("sales", doctype, ptype), f"{doctype} {ptype} must be refused")

    def test_stock_user(self) -> None:
        self.assertTrue(self.can("stock", "Stock Entry", "create"))
        self.assertTrue(self.can("stock", "Warehouse", "read"))
        self.assertFalse(self.can("stock", "Sales Invoice", "create"))
        self.assertFalse(self.can("stock", "Journal Entry", "create"))

    def test_restricted_stock_user_sees_only_assigned_items_and_warehouses(self) -> None:
        frappe.set_user(self.users["cold"])
        items = frappe.get_list("Item", filters={"name": ["in", [self.frozen_item, self.other_item]]}, pluck="name")
        self.assertEqual(items, [self.frozen_item])
        self.assertFalse(frappe.has_permission("Item", "read", doc=self.other_item))
        warehouses = frappe.get_list("Warehouse", filters={"name": ["in", [self.cold_store, self.dry_store]]}, pluck="name")
        self.assertEqual(warehouses, [self.cold_store])

    def test_restricted_stock_user_on_the_pos_stock_list(self) -> None:
        from zatgo_core.services.resto_pos_admin_service import _stock_rows

        frappe.set_user(self.users["cold"])
        ids = {r["id"] for r in _stock_rows(self.company, None)}
        self.assertIn(self.frozen_item, ids)
        self.assertNotIn(self.other_item, ids)

    def test_sales_manager_reads_sales_reports_a_sales_user_does_not_configure_modules(self) -> None:
        report = frappe.get_doc("Report", "Sales Analytics")
        frappe.set_user(self.users["manager"])
        self.assertTrue(report.is_permitted())
        frappe.set_user("Administrator")
        self.assertFalse(self.can("sales", "Module Settings", "write"))

    def test_administrator_persona_configures_zatgo(self) -> None:
        self.assertTrue(self.can("admin", "Module Settings", "write"))
        self.assertTrue(self.can("admin", "ZatGo System Settings", "write"))

    def test_the_zatgo_api_refuses_what_the_role_may_not_do(self) -> None:
        from zatgo_core.api.v1.accounting import invoices

        frappe.set_user(self.users["stock"])
        with self.assertRaises(frappe.PermissionError):
            invoices.create(customer="any", items=[{"item_code": self.frozen_item, "qty": 1, "rate": 1}], company=self.company)

    def test_a_user_with_no_role_reads_no_zatgo_report(self) -> None:
        email = f"zg-persona-none-{self.tag.lower()}@example.test"
        frappe.get_doc({"doctype": "User", "email": email, "first_name": "none", "send_welcome_email": 0}
                       ).insert(ignore_permissions=True)
        try:
            frappe.set_user(email)
            self.assertFalse(frappe.get_doc("Report", "Business Summary Report").is_permitted())
        finally:
            frappe.set_user("Administrator")
            frappe.delete_doc("User", email, force=True, ignore_permissions=True)
