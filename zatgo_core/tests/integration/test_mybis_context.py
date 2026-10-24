"""MyBis slice A end to end: the app switch (default off, 404 when off), the bootstrap context and company isolation.

Runs against a real site; the switch and the throwaway users / company are restored or removed per test."""

from __future__ import annotations

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import random_string

from zatgo_core.api.v1.mybis import context
from zatgo_core.services import app_catalog, app_gate, app_state
from zatgo_core.services.mybis import cache, scope

from ._fixtures import get_or_create_test_company

SETTINGS = "ZG System Settings"
FIELD = "enable_mybis"
METHOD = "/api/method/zatgo_core.api.v1.mybis.context.get_context"
OTHER_COMPANY = "ZatGo MyBis Test Co 2"


def _store(value) -> None:
    if value is None:
        frappe.db.delete("Singles", {"doctype": SETTINGS, "field": FIELD})
    else:
        frappe.db.set_single_value(SETTINGS, FIELD, value)
    frappe.clear_document_cache(SETTINGS, SETTINGS)


def _stored():
    rows = frappe.db.sql("select value from `tabSingles` where doctype = %s and field = %s", (SETTINGS, FIELD))
    return rows[0][0] if rows else None


def _other_company() -> str:
    if not frappe.db.exists("Company", OTHER_COMPANY):
        frappe.get_doc(
            {"doctype": "Company", "company_name": OTHER_COMPANY, "abbr": "ZMT2", "default_currency": "SAR", "country": "Saudi Arabia"}
        ).insert(ignore_permissions=True)
    return OTHER_COMPANY


def _user(*roles: str) -> str:
    email = f"mybis.{random_string(8).lower()}@zatgo.test"
    frappe.get_doc(
        {"doctype": "User", "email": email, "first_name": "MyBis", "send_welcome_email": 0, "roles": [{"role": r} for r in roles]}
    ).insert(ignore_permissions=True)
    return email


class TestMyBisSwitch(IntegrationTestCase):
    def setUp(self) -> None:
        frappe.set_user("Administrator")
        self._before = _stored()

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        _store(self._before)
        frappe.db.commit()

    def _gate(self) -> None:
        had = hasattr(frappe.local, "request")
        orig = getattr(frappe.local, "request", None)
        try:
            frappe.local.request = frappe._dict(path=METHOD)
            app_gate.gate_api()
        finally:
            if had:
                frappe.local.request = orig
            else:
                del frappe.local.request

    def test_catalog_entry_is_off_by_default(self) -> None:
        app = app_catalog.get("mybis")
        self.assertIsNotNone(app)
        self.assertEqual(app["switch_field"], FIELD)
        self.assertFalse(app["default_on"])
        self.assertTrue(frappe.get_meta(SETTINGS).has_field(FIELD))
        _store(None)
        self.assertFalse(app_state.is_on("mybis"))

    def test_off_answers_404_on_answers_through(self) -> None:
        _store(0)
        with self.assertRaises(frappe.DoesNotExistError):
            self._gate()
        _store(1)
        self._gate()  # no exception


class TestMyBisContext(IntegrationTestCase):
    def setUp(self) -> None:
        frappe.set_user("Administrator")
        self.company = get_or_create_test_company()
        self.other = _other_company()

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        frappe.db.rollback()

    def test_guest_is_refused(self) -> None:
        frappe.set_user("Guest")
        with self.assertRaises(frappe.PermissionError):
            context.get_context()

    def test_administrator_context(self) -> None:
        data = context.get_context()["data"]
        names = {c["name"] for c in data["companies"]}
        self.assertTrue({self.company, self.other} <= names)
        self.assertTrue(all(c["currency"] for c in data["companies"]))
        self.assertIn("this_month", data["presets"])
        self.assertTrue(data["areas"]["sales"])

    def test_company_user_permission_isolates_companies(self) -> None:
        user = _user("System Manager", "Accounts Manager")
        frappe.get_doc({"doctype": "User Permission", "user": user, "allow": "Company", "for_value": self.company}).insert(
            ignore_permissions=True
        )
        frappe.clear_cache(user=user)
        frappe.set_user(user)
        data = context.get_context()["data"]
        self.assertEqual([c["name"] for c in data["companies"]], [self.company])
        self.assertEqual(data["default_company"], self.company)
        with self.assertRaises(frappe.PermissionError):
            scope.resolve_scope(company=self.other)
        s = scope.resolve_scope(company=None)  # falls back to the only readable company
        self.assertEqual(s.company, self.company)
        self.assertEqual(s.currency, "SAR")

    def test_period_input_is_validated(self) -> None:
        with self.assertRaises(frappe.ValidationError):
            scope.resolve_scope(self.company, "custom", "2026-10-10", "2026-10-01")
        with self.assertRaises(frappe.ValidationError):
            scope.resolve_scope(self.company, "custom", "not-a-date", "2026-10-01")
        with self.assertRaises(frappe.ValidationError):
            scope.resolve_scope(self.company, "bogus")
        s = scope.resolve_scope(self.company, "this_month", compare=0)
        self.assertIsNone(s.previous)
        s = scope.resolve_scope(self.company, "this_month")
        self.assertIsNotNone(s.previous)
        self.assertEqual(context.resolve_period(self.company, "last_month")["data"]["preset"], "last_month")

    def test_cache_is_per_user_and_reports_its_age(self) -> None:
        calls = []

        def compute():
            calls.append(1)
            return {"v": len(calls)}

        a, meta_a = cache.cached("t", self.company, {"p": 1}, compute, ttl=60, refresh=True)
        b, meta_b = cache.cached("t", self.company, {"p": 1}, compute, ttl=60)
        self.assertEqual(a, b)
        self.assertTrue(meta_b["cached"] and not meta_a["cached"])
        self.assertEqual(meta_a["cached_at"], meta_b["cached_at"])
        c, meta_c = cache.cached("t", self.company, {"p": 1}, compute, ttl=60, refresh=True)
        self.assertFalse(meta_c["cached"])
        self.assertEqual(len(calls), 2)
        self.assertNotEqual(cache.make_key("t", "A", {}), cache.make_key("t", "B", {}))
