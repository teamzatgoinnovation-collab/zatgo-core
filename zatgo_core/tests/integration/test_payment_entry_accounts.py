"""Account Paid To / Paid From on Payment Entry follow the chart's Bank Accounts
(services/payment_entry_accounts.py), switchable in ZG System Settings."""

from __future__ import annotations

from unittest import mock

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase

from zatgo_core.api.v1.accounting import payment_methods
from zatgo_core.services import payment_entry_accounts as svc

COMPANY = "ZatGo Core Test Co"
GROUP = "Bank Accounts - ZCTC"
SETTINGS, FIELD = "ZG System Settings", "autofill_payment_entry_account"
BANK_MODE, CASH_MODE = "Wire Transfer", "Cash"


def _account(name: str, **kw) -> str:
    doc = frappe.get_doc(
        {"doctype": "Account", "account_name": name, "parent_account": GROUP, "company": COMPANY, "account_type": "", **kw}
    )
    doc.insert(ignore_permissions=True)
    return doc.name


class TestPaymentEntryAccounts(IntegrationTestCase):
    def setUp(self) -> None:
        frappe.set_user("Administrator")
        if not frappe.db.exists("Account", GROUP) or frappe.db.get_value("Mode of Payment", BANK_MODE, "type") != "Bank":
            self.skipTest("test chart / modes of payment not present on this site")
        self.listed = {n for n, _ in svc.chart_ledgers(COMPANY, "Bank")}
        self.assertTrue(self.listed, "the test company should have bank ledgers")
        rows = frappe.db.sql("SELECT value FROM `tabSingles` WHERE doctype = %s AND field = %s", (SETTINGS, FIELD))
        self._had, self._value = bool(rows), (rows[0][0] if rows else None)
        self.addCleanup(self._restore)
        self._company_default = frappe.db.get_value("Company", COMPANY, "default_bank_account")
        self.addCleanup(frappe.db.set_value, "Company", COMPANY, "default_bank_account", self._company_default)
        frappe.db.set_value("Company", COMPANY, "default_bank_account", None)

    def _restore(self) -> None:
        frappe.db.sql("DELETE FROM `tabSingles` WHERE doctype = %s AND field = %s", (SETTINGS, FIELD))
        if self._had:
            frappe.db.sql("INSERT INTO `tabSingles` (doctype, field, value) VALUES (%s, %s, %s)", (SETTINGS, FIELD, self._value))

    def _set(self, value) -> None:
        frappe.db.sql("DELETE FROM `tabSingles` WHERE doctype = %s AND field = %s", (SETTINGS, FIELD))
        if value is not None:
            frappe.db.sql("INSERT INTO `tabSingles` (doctype, field, value) VALUES (%s, %s, %s)", (SETTINGS, FIELD, value))

    def _first_in_chart(self) -> str:
        return min(svc._chart_rows(COMPANY, "Bank"), key=lambda r: r.lft).name

    # -- the chart definition ---------------------------------------------------------------------------
    def test_a_ledger_without_account_type_under_bank_accounts_is_listed_and_a_disabled_one_is_not(self) -> None:
        untyped = _account("ZG PE Untyped Bank")
        disabled = _account("ZG PE Disabled Bank", account_type="Bank", disabled=1)
        self.addCleanup(frappe.delete_doc, "Account", untyped, force=1)
        self.addCleanup(frappe.delete_doc, "Account", disabled, force=1)
        names = {n for n, _ in svc.chart_ledgers(COMPANY, "Bank")}
        self.assertIn(untyped, names)
        self.assertNotIn(disabled, names)
        self.assertFalse(names & {"Cash - ZCTC"}, "cash ledgers are not Bank Accounts")

    # -- the default ----------------------------------------------------------------------------------
    def test_a_bank_mode_without_a_default_gets_the_first_ledger_in_chart_order(self) -> None:
        self._set("1")
        got = svc.resolve(BANK_MODE, COMPANY)
        self.assertEqual((got["enabled"], got["mode_type"]), (True, "Bank"))
        self.assertEqual(got["account"], self._first_in_chart())

    def test_the_modes_own_default_wins_when_it_is_a_bank_ledger(self) -> None:
        self._set("1")
        other = sorted(self.listed)[-1]
        with mock.patch.object(svc.payment_allocation, "allowed_accounts", return_value=[{"account": other, "is_default": True}]):
            self.assertEqual(svc.resolve(BANK_MODE, COMPANY)["account"], other)

    def test_a_mode_default_outside_bank_accounts_is_ignored(self) -> None:
        self._set("1")
        with mock.patch.object(svc.payment_allocation, "allowed_accounts", return_value=[{"account": "Cash - ZCTC", "is_default": True}]):
            self.assertEqual(svc.resolve(BANK_MODE, COMPANY)["account"], self._first_in_chart())

    def test_the_company_default_bank_account_comes_before_chart_order(self) -> None:
        self._set("1")
        last = max(svc._chart_rows(COMPANY, "Bank"), key=lambda r: r.lft).name
        frappe.db.set_value("Company", COMPANY, "default_bank_account", last)
        self.assertEqual(svc.resolve(BANK_MODE, COMPANY)["account"], last)

    def test_a_cash_mode_is_left_to_erpnext(self) -> None:
        self._set("1")
        got = svc.resolve(CASH_MODE, COMPANY)
        self.assertEqual((got["enabled"], got["mode_type"], got["account"]), (True, "Cash", None))

    def test_unticked_means_blank_for_every_mode(self) -> None:
        self._set("0")
        for mode in (BANK_MODE, CASH_MODE):
            got = svc.resolve(mode, COMPANY)
            self.assertEqual((got["enabled"], got["account"]), (False, None), mode)

    def test_never_saved_means_on(self) -> None:
        self._set(None)
        self.assertTrue(svc.autofill_enabled())
        self.assertEqual(svc.resolve(BANK_MODE, COMPANY)["account"], self._first_in_chart())

    def test_no_company_or_mode_is_harmless(self) -> None:
        self._set("1")
        self.assertIsNone(svc.resolve(None, COMPANY)["account"])
        self.assertIsNone(svc.resolve(BANK_MODE, None)["account"])

    # -- the picker -----------------------------------------------------------------------------------
    def _query(self, mode, txt=""):
        rows = payment_methods.payment_entry_account_query(
            "Account", txt, "name", 0, 50, {"company": COMPANY, "mode_of_payment": mode}
        )
        return {r[0] for r in rows}

    def test_a_bank_mode_offers_only_the_bank_accounts(self) -> None:
        self._set("1")
        names = self._query(BANK_MODE)
        self.assertEqual(names, self.listed)
        self.assertNotIn("Cash - ZCTC", names)

    def test_a_cash_mode_or_no_mode_gets_erpnexts_bank_and_cash_list(self) -> None:
        self._set("1")
        for mode in (CASH_MODE, None):
            names = self._query(mode)
            self.assertIn("Cash - ZCTC", names, mode)
            self.assertTrue(self.listed <= names, mode)

    def test_unticked_the_picker_is_erpnexts_even_for_a_bank_mode(self) -> None:
        self._set("0")
        self.assertIn("Cash - ZCTC", self._query(BANK_MODE))

    def test_the_picker_search_text_narrows_the_list(self) -> None:
        self._set("1")
        one = sorted(self.listed)[0]
        self.assertEqual(self._query(BANK_MODE, one), {one})

    def test_the_invoice_pickers_still_return_what_they_did(self) -> None:
        rows = payment_methods.payment_account_query("Account", "", "name", 0, 50, {"company": COMPANY, "account_type": "Bank"})
        self.assertEqual({r[0] for r in rows}, self.listed)

    # -- the setting + patch ---------------------------------------------------------------------------
    def test_the_setting_exists_and_is_on_by_default(self) -> None:
        df = frappe.get_meta(SETTINGS).get_field(FIELD)
        self.assertIsNotNone(df)
        self.assertEqual((df.fieldtype, str(df.default)), ("Check", "1"))

    def test_the_patch_ticks_the_box_where_it_never_existed_and_keeps_an_explicit_off(self) -> None:
        from zatgo_core.patches.v0_4_6 import autofill_payment_entry_account_on as patch

        self._set(None)
        patch.execute()
        self.assertEqual(frappe.db.sql("SELECT value FROM `tabSingles` WHERE doctype=%s AND field=%s", (SETTINGS, FIELD))[0][0], "1")
        self._set("0")
        patch.execute()
        self.assertEqual(frappe.db.sql("SELECT value FROM `tabSingles` WHERE doctype=%s AND field=%s", (SETTINGS, FIELD))[0][0], "0")
