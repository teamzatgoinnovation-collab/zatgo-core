"""Settings management (Phase 7): the landing page, settings that do nothing are not offered, settings reads respect
Company User Permissions, and a save only sets the DocType's own editable fields."""

from __future__ import annotations

import json

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import random_string

from zatgo_core.repositories.settings_repository import writable_values
from zatgo_core.services import module_workspaces
from zatgo_core.services.settings_service import SettingsService

STUBS = ("ZatGo Security Settings", "Payment Settings", "Printer Settings", "Sync Settings", "Storage Settings")


class TestSettingsManagement(IntegrationTestCase):
    def test_landing_page_has_the_sections_and_only_existing_links(self) -> None:
        module_workspaces.ensure()
        ws = frappe.get_doc("Workspace", "ZatGo Settings")
        sections = [l.label for l in ws.links if l.type == "Card Break"]
        for needed in ("General", "Modules", "Sales", "Purchase", "Inventory", "Accounting", "Print",
                       "Tax and Compliance", "Users and Access", "Advanced"):
            self.assertIn(needed, sections)
        for link in ws.links:
            if link.type == "Link":
                self.assertTrue(frappe.db.exists(link.link_type, link.link_to), link.link_to)
        linked = {l.link_to for l in ws.links if l.type == "Link"}
        self.assertTrue({"System Settings", "Selling Settings", "Stock Settings", "Accounts Settings"} <= linked,
                        "ERPNext's own settings are linked, not copied")
        self.assertFalse(set(STUBS) & linked)

    def test_settings_that_do_nothing_say_so(self) -> None:
        for doctype in STUBS:
            meta = frappe.get_meta(doctype)
            notice = meta.get_field("zg_not_used_notice")
            self.assertTrue(notice and notice.fieldtype == "HTML", doctype)

    def test_copies_of_frappe_settings_are_hidden(self) -> None:
        meta = frappe.get_meta("ZatGo System Settings")
        for fieldname in ("timezone", "date_format", "rounding_method", "rounding_precision"):
            self.assertTrue(meta.get_field(fieldname).hidden, fieldname)

    def test_a_save_only_sets_editable_fields(self) -> None:
        kept = writable_values("ZatGo Notification Settings", {
            "push_enabled": 1, "name": "x", "owner": "someone@example.test", "docstatus": 2, "no_such_field": 1,
        })
        self.assertEqual(kept, {"push_enabled": 1})

    def test_company_settings_read_respects_company_user_permissions(self) -> None:
        companies = frappe.get_all("Company Settings", fields=["name", "company"], limit=2)
        if len(companies) < 2:
            self.skipTest("needs Company Settings for two companies")
        mine, other = companies[0], companies[1]
        email = f"zg-settings-{random_string(6).lower()}@example.test"
        frappe.get_doc({"doctype": "User", "email": email, "first_name": "s", "send_welcome_email": 0,
                        "roles": [{"role": "ZatGo Company Admin"}]}).insert(ignore_permissions=True)
        frappe.get_doc({"doctype": "User Permission", "user": email, "allow": "Company", "for_value": mine.company,
                        "apply_to_all_doctypes": 1}).insert(ignore_permissions=True)
        try:
            frappe.set_user(email)
            self.assertTrue(SettingsService.get_company_settings(mine.company))
            with self.assertRaises(frappe.PermissionError):
                SettingsService.get_company_settings(other.company)
        finally:
            frappe.set_user("Administrator")
            frappe.delete_doc("User", email, force=True, ignore_permissions=True)
