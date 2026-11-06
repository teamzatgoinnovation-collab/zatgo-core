"""Seeding VanSale roles must not take a DocType away from everyone else: Frappe ignores a DocType's standard DocPerm rows
once it has any Custom DocPerm. Named roles keep theirs; rows opening other people's records to all staff stay out."""

from __future__ import annotations

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import random_string

from zatgo_core.setup.ensure_vansale_perms import ensure_vansale_perms


class TestVanSalePermSeeding(IntegrationTestCase):
    def setUp(self) -> None:
        self.users: list[str] = []
        ensure_vansale_perms()

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        for email in self.users:
            frappe.delete_doc("User", email, force=True, ignore_permissions=True)
        frappe.clear_cache()

    def _user(self, *roles: str) -> str:
        email = f"zgperm-{random_string(8).lower()}@example.test"
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "perm",
                "send_welcome_email": 0,
                "roles": [{"role": role} for role in roles],
            }
        ).insert(ignore_permissions=True)
        self.users.append(email)
        return email

    def _can(self, user: str, doctype: str, ptype: str) -> bool:
        return bool(frappe.has_permission(doctype, ptype, user=user))

    def test_named_roles_keep_their_standard_access(self) -> None:
        accounts = self._user("Accounts User")
        self.assertTrue(self._can(accounts, "Sales Invoice", "create"))
        self.assertTrue(self._can(accounts, "Payment Entry", "submit"))
        self.assertTrue(self._can(self._user("Stock User"), "Stock Entry", "create"))
        self.assertTrue(self._can(self._user("Sales User"), "Customer", "read"))

    def test_a_courier_with_only_the_delivery_role_can_work_stops(self) -> None:
        self.assertTrue(self._can(self._user("Delivery"), "ZG Delivery Stop", "write"))

    def test_system_manager_keeps_address_contact_and_trips(self) -> None:
        manager = self._user("System Manager")
        for doctype in ("Address", "Contact", "ZG Trip", "ZG Delivery Stop", "ZG Vehicle"):
            self.assertTrue(self._can(manager, doctype, "write"), doctype)

    def test_standard_rows_keep_their_exact_flags(self) -> None:
        """A role gets what ERPNext ships, no more: Accounts User may not delete a Sales Invoice."""
        accounts = self._user("Accounts User")
        self.assertFalse(self._can(accounts, "Sales Invoice", "delete"))
        self.assertFalse(self._can(self._user("Sales User"), "Stock Entry", "read"))

    def test_rows_opening_records_to_all_staff_stay_out(self) -> None:
        staff = self._user("Desk User")
        for doctype in ("ZG Vehicle", "ZG Delivery Stop"):
            self.assertFalse(self._can(staff, doctype, "write"), doctype)

    def test_field_users_gain_nothing_on_money_documents_or_vehicles(self) -> None:
        field = self._user("VanSale User")
        self.assertFalse(self._can(field, "ZG Vehicle", "write"))
        self.assertFalse(self._can(field, "Sales Invoice", "cancel"))
        self.assertFalse(self._can(field, "Payment Entry", "cancel"))
        self.assertFalse(self._can(field, "Stock Entry", "cancel"))
        self.assertFalse(self._can(field, "Account", "write"))
        self.assertFalse(self._can(field, "ZG Delivery Stop", "create"))

    def test_seeded_grants_are_still_there(self) -> None:
        self.assertTrue(self._can(self._user("VanSale User"), "Sales Invoice", "submit"))
        self.assertTrue(self._can(self._user("VanSale Admin"), "Sales Invoice", "cancel"))

    def test_a_row_the_admin_removes_stays_removed(self) -> None:
        filters = {"parent": "Stock Entry", "role": "Manufacturing User"}
        saved = frappe.get_all("Custom DocPerm", filters=filters, fields="*")
        self.assertTrue(saved)
        try:
            frappe.db.delete("Custom DocPerm", filters)
            ensure_vansale_perms()  # = the next migrate
            self.assertFalse(frappe.db.exists("Custom DocPerm", filters))
        finally:
            for row in saved:
                doc = frappe.new_doc("Custom DocPerm")
                doc.update({k: v for k, v in row.items() if k not in frappe.model.default_fields})
                doc.insert(ignore_permissions=True)
            frappe.db.commit()
            frappe.clear_cache()

    def test_a_run_on_a_repaired_site_adds_no_rows(self) -> None:
        before = frappe.db.count("Custom DocPerm")
        ensure_vansale_perms()
        self.assertEqual(frappe.db.count("Custom DocPerm"), before)
