"""User-wise Sales Invoice print format (services/sales_invoice_print.py).

Resolution logic is exercised with in-memory rules (find_rule patched), so the
suite never touches a site's real naming settings.
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase

from zatgo_core.services import sales_invoice_print as sip

VANSALE_80 = "VanSale Tax Invoice 80mm"


def rule(**kw):
    base = dict(
        idx=1, enabled=1, user="u@x.com", company="C", print_format_a4="", print_format_80mm="",
        default_paper="", restrict_print_format=0,
    )
    base.update(kw)
    return frappe._dict(base)


def resolve(r, requested, user="u@x.com"):
    with patch.object(sip, "find_rule", return_value=r):
        return sip.resolve_print_format(user, "C", requested)


class TestSalesInvoicePrint(IntegrationTestCase):
    def test_no_rule_changes_nothing(self):
        self.assertEqual(resolve(None, ""), "")
        self.assertEqual(resolve(None, "Whatever"), "Whatever")
        self.assertEqual(resolve(None, "Standard"), "")

    def test_default_paper_fills_blank_request(self):
        r = rule(print_format_a4="A4 Fmt", print_format_80mm="Mine 80", default_paper="80mm")
        self.assertEqual(resolve(r, ""), "Mine 80")
        r.default_paper = "A4"
        self.assertEqual(resolve(r, ""), "A4 Fmt")
        # only an 80mm format assigned, no default: that one
        self.assertEqual(resolve(rule(print_format_80mm="Mine 80"), ""), "Mine 80")

    def test_vansalex_80mm_choice_maps_to_users_own_80mm(self):
        r = rule(print_format_80mm="Signx 80")
        self.assertEqual(resolve(r, VANSALE_80), "Signx 80")
        # no own 80mm format: stock one passes through
        self.assertEqual(resolve(rule(), VANSALE_80), VANSALE_80)

    def test_unrestricted_user_may_pick_anything(self):
        r = rule(print_format_a4="A4 Fmt")
        self.assertEqual(resolve(r, "Other Fmt"), "Other Fmt")

    def test_restricted_user_only_assigned_formats(self):
        r = rule(print_format_a4="A4 Fmt", print_format_80mm="Mine 80", restrict_print_format=1)
        self.assertEqual(resolve(r, "A4 Fmt"), "A4 Fmt")
        self.assertEqual(resolve(r, VANSALE_80), "Mine 80")
        with self.assertRaises(frappe.PermissionError):
            resolve(r, "Other Fmt")
        with self.assertRaises(frappe.PermissionError):
            resolve(rule(print_format_80mm="Mine 80", restrict_print_format=1), "A4 Fmt")

    def test_restricted_without_a4_cannot_use_site_default(self):
        r = rule(print_format_80mm="Mine 80", restrict_print_format=1, default_paper="A4")
        with self.assertRaises(frappe.PermissionError):
            resolve(r, "")

    def test_administrator_is_exempt_from_restriction(self):
        r = rule(print_format_a4="A4 Fmt", restrict_print_format=1)
        self.assertEqual(resolve(r, "Other Fmt", user="Administrator"), "Other Fmt")

    def test_is_80mm(self):
        self.assertTrue(sip.is_80mm(VANSALE_80))
        self.assertTrue(sip.is_80mm("Signx 80", rule(print_format_80mm="Signx 80")))
        self.assertFalse(sip.is_80mm("Signx 80"))
        self.assertFalse(sip.is_80mm(""))

    def test_validate_rule_formats(self):
        self.assertIsNone(sip.validate_rule_formats([rule()]))
        with self.assertRaises(frappe.ValidationError):
            sip.validate_rule_formats([rule(print_format_a4="No Such Format")])
        with self.assertRaises(frappe.ValidationError):
            sip.validate_rule_formats([rule(restrict_print_format=1)])
