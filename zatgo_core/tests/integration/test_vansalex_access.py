"""Regression coverage for vansalex.me.context's has_vansale_access field.

It used to be hardcoded True regardless of role — any authenticated
ERPNext user, VanSale role or not, passed the Flutter client's login gate
(main.dart's _afterAuth). Confirms it now reflects the real role check.
"""

from __future__ import annotations

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import random_string


class TestVansalexAccess(IntegrationTestCase):
    def tearDown(self) -> None:
        frappe.set_user("Administrator")

    @classmethod
    def _make_user(cls, roles: list[str]) -> str:
        email = f"vansale.access.test.{random_string(6).lower()}@zatgo.test"
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "Access",
                "last_name": "Test",
                "send_welcome_email": 0,
                "roles": [{"role": r} for r in roles],
            }
        ).insert(ignore_permissions=True)
        return email

    def test_user_with_vansale_role_has_access(self) -> None:
        from zatgo_core.api.v1.vansalex.me import context

        user = self._make_user(["VanSale User"])
        frappe.set_user(user)
        result = context()
        self.assertTrue(result["data"]["has_vansale_access"])

    def test_admin_with_vansale_role_has_access(self) -> None:
        from zatgo_core.api.v1.vansalex.me import context

        user = self._make_user(["VanSale Admin"])
        frappe.set_user(user)
        result = context()
        self.assertTrue(result["data"]["has_vansale_access"])

    def test_user_without_vansale_role_has_no_access(self) -> None:
        from zatgo_core.api.v1.vansalex.me import context

        user = self._make_user(["Sales User"])
        frappe.set_user(user)
        result = context()
        self.assertFalse(result["data"]["has_vansale_access"])
