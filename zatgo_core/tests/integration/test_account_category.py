"""Accounts inherit their parent's Account Category (events/account_category.py, patch v0_4_3)."""

from __future__ import annotations

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import random_string

from zatgo_core.patches.v0_4_3.inherit_account_category import execute as backfill
from zatgo_core.tests.integration._fixtures import get_or_create_test_company


class TestAccountCategory(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.company = get_or_create_test_company()
        cls.parent = frappe.db.get_value(
            "Account",
            {"company": cls.company, "is_group": 1, "account_category": ["is", "set"], "root_type": "Asset"},
            "name",
        )

    def _account(self, **extra):
        doc = frappe.get_doc(
            {
                "doctype": "Account",
                "account_name": f"ZG Cat {random_string(5)}",
                "company": self.company,
                "parent_account": self.parent,
                "account_currency": "SAR",
                **extra,
            }
        )
        return doc.insert(ignore_permissions=True)

    def test_new_account_inherits_parent_category(self) -> None:
        if not self.parent:
            self.skipTest("no categorised asset group in this chart")
        acc = self._account()
        self.assertEqual(acc.account_category, frappe.db.get_value("Account", self.parent, "account_category"))

    def test_explicit_category_is_kept(self) -> None:
        if not self.parent:
            self.skipTest("no categorised asset group in this chart")
        other = "Other Current Assets"
        if frappe.db.get_value("Account", self.parent, "account_category") == other:
            self.skipTest("parent already has the alternative category")
        acc = self._account(account_category=other)
        self.assertEqual(acc.account_category, other)

    def test_backfill_fills_only_missing(self) -> None:
        if not self.parent:
            self.skipTest("no categorised asset group in this chart")
        acc = self._account()
        frappe.db.set_value("Account", acc.name, "account_category", None)
        backfill()
        self.assertEqual(
            frappe.db.get_value("Account", acc.name, "account_category"),
            frappe.db.get_value("Account", self.parent, "account_category"),
        )
