"""MyBis security contract: every endpoint needs a login, honours the app switch, is read-only and refuses a user with no rights.

The endpoints are discovered from the package, so a new whitelisted function is covered without touching this file -- and one
that forgets `require_login` / the guard fails here.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from typing import Any, Callable

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import random_string

from zatgo_core.api.v1 import mybis as mybis_pkg
from zatgo_core.services import app_gate, app_state
from zatgo_core.tests.integration.test_mybis_dashboard import COMPANY, _company

PREFIX = "zatgo_core.api.v1.mybis."

# Static reference data -- no company figures -- that any signed-in user may read.
STATIC = {"context.get_context", "context.resolve_period", "forecast.methods", "reports.catalog"}

# Required arguments that must look real so a call gets past input validation to the permission check.
SAMPLE = {"kind": "receivable", "party": "x", "name": "x", "q": "abc", "type": "customer", "report": "sales_summary", "format": "csv"}


def endpoints() -> dict[str, Callable]:
    """dotted name (relative to the package) -> whitelisted function, for every MyBis API module."""
    found: dict[str, Callable] = {}
    for info in pkgutil.iter_modules(mybis_pkg.__path__):
        if info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{PREFIX}{info.name}")
        for name, fn in inspect.getmembers(module, inspect.isfunction):
            if fn.__module__ == module.__name__ and fn in frappe.whitelisted:
                found[f"{info.name}.{name}"] = fn
    return found


def call(fn: Callable, **extra: Any) -> Any:
    """Call with a sample value for each required argument and the function's own defaults for the rest."""
    kwargs = {n: SAMPLE.get(n, "x") for n, p in inspect.signature(fn).parameters.items() if p.default is inspect.Parameter.empty}
    kwargs.update({k: v for k, v in extra.items() if k in inspect.signature(fn).parameters})
    return fn(**kwargs)


class TestMyBisSecurity(IntegrationTestCase):
    def setUp(self) -> None:
        frappe.set_user("Administrator")
        _company()

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        frappe.db.rollback()

    def test_endpoints_are_discovered(self) -> None:
        names = set(endpoints())
        self.assertGreaterEqual(len(names), 37)
        for expected in ("sales.movers", "purchase.movers", "dashboard.kpis", "finance.balance_sheet", "reports.export", "search.record", "alerts.feed"):
            self.assertIn(expected, names)

    def test_every_endpoint_is_read_only_http(self) -> None:
        for name, fn in endpoints().items():
            methods = set(frappe.allowed_http_methods_for_whitelisted_func.get(fn, []))
            self.assertTrue(methods and methods <= {"GET", "POST"}, f"{name}: {methods}")

    def test_a_guest_is_refused_by_every_endpoint(self) -> None:
        frappe.set_user("Guest")
        for name, fn in endpoints().items():
            with self.assertRaises((frappe.PermissionError, frappe.AuthenticationError), msg=name):
                call(fn, company=COMPANY)

    def _nobody(self) -> str:
        """A desk user whose only role grants no DocType permission at all."""
        role = f"MyBis NoAccess {random_string(6)}"
        frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)
        email = f"mybis.sec.{random_string(8).lower()}@zatgo.test"
        frappe.get_doc({"doctype": "User", "email": email, "first_name": "S", "send_welcome_email": 0, "roles": [{"role": role}]}).insert(ignore_permissions=True)
        frappe.clear_cache(user=email)
        return email

    def test_a_user_with_no_accounting_rights_gets_no_company_data(self) -> None:
        frappe.set_user(self._nobody())
        for name, fn in endpoints().items():
            if name in STATIC:
                continue
            with self.assertRaises((frappe.PermissionError, frappe.ValidationError), msg=name):
                call(fn, company=COMPANY)

    def test_static_endpoints_carry_no_company_figures(self) -> None:
        frappe.set_user(self._nobody())
        eps = endpoints()
        ctx = call(eps["context.get_context"])["data"]
        self.assertFalse(ctx.get("companies"), "a user who can read no company is shown none")
        self.assertFalse(any(ctx.get("areas", {}).values()), "and no area of the app")
        self.assertFalse(ctx["has_access"], "so the app shows its no-access screen rather than an error")

    def test_a_switched_off_app_answers_404_for_every_endpoint(self) -> None:
        original = app_state.is_on
        try:
            app_state.is_on = lambda key: False if key == "mybis" else original(key)  # type: ignore[assignment]
            for name in endpoints():
                frappe.local.form_dict = frappe._dict(cmd=f"{PREFIX}{name}")
                with self.assertRaises(frappe.DoesNotExistError, msg=name):
                    app_gate.gate_api()
        finally:
            app_state.is_on = original  # type: ignore[assignment]
            frappe.local.form_dict = frappe._dict()

    def test_the_switch_is_off_by_default_and_the_gate_follows_the_stored_value(self) -> None:
        self.assertIn("mybis", {a["key"] for a in __import__("zatgo_core.services.app_catalog", fromlist=["catalog"]).catalog()})
        was = frappe.db.get_single_value("ZG System Settings", "enable_mybis")
        try:
            frappe.db.set_single_value("ZG System Settings", "enable_mybis", 0)
            frappe.clear_document_cache("ZG System Settings")
            self.assertFalse(app_state.is_on("mybis"))
            frappe.local.form_dict = frappe._dict(cmd=f"{PREFIX}dashboard.kpis")
            with self.assertRaises(frappe.DoesNotExistError):
                app_gate.gate_api()
            frappe.db.set_single_value("ZG System Settings", "enable_mybis", 1)
            frappe.clear_document_cache("ZG System Settings")
            self.assertTrue(app_state.is_on("mybis"))
            app_gate.gate_api()  # on: passes through
        finally:
            frappe.db.set_single_value("ZG System Settings", "enable_mybis", was or 0)
            frappe.clear_document_cache("ZG System Settings")
            frappe.local.form_dict = frappe._dict()
