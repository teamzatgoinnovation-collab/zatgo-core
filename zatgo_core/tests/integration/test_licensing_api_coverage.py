"""Every whitelisted zatgo_core API endpoint has a licensing decision, and the licensing API itself is closed to
those who may not use it (Phase 9)."""

from __future__ import annotations

import importlib
import inspect
import pkgutil

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import random_string

import zatgo_core.api.v1 as api_root
from zatgo_core.licensing import api_coverage


def _endpoints(package) -> dict[str, object]:
    found: dict[str, object] = {}
    for info in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
        module = importlib.import_module(info.name)
        for name, fn in vars(module).items():
            if callable(fn) and fn in frappe.whitelisted and getattr(fn, "__module__", None) == module.__name__:
                found[f"{module.__name__}.{name}"] = fn
    return found


class TestApiCoverage(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.endpoints = _endpoints(api_root)

    def test_every_endpoint_has_a_licensing_decision(self) -> None:
        self.assertGreater(len(self.endpoints), 250)
        missing = sorted(m for m in self.endpoints if api_coverage.classify(m) is None)
        self.assertEqual(missing, [], "add the endpoint to a feature's api_prefixes or to api_coverage.NOT_LICENSED")

    def test_no_stale_exemptions(self) -> None:
        unused = [p for p in api_coverage.NOT_LICENSED if p not in api_coverage.OPTIONAL
                  and not any((m + ".").startswith(p) for m in self.endpoints)]
        self.assertEqual(unused, [])

    def test_exemptions_do_not_shadow_licensed_prefixes(self) -> None:
        licensed = [p for p, _owner in api_coverage.owners()]
        overlap = [p for p in api_coverage.NOT_LICENSED if any(p.startswith(q) or q.startswith(p) for q in licensed)
                   and not p.endswith(".health.")]
        self.assertEqual(overlap, [])

    def test_classification(self) -> None:
        self.assertEqual(api_coverage.classify("zatgo_core.api.v1.accounting.invoices.create")["owner"], "sales.invoice")
        self.assertEqual(api_coverage.classify("zatgo_core.api.v1.vansalex.orders.create")["owner"], "app:vansalex")
        self.assertEqual(api_coverage.classify("zatgo_core.api.v1.licensing.licences.import_licence")["kind"],
                         "not_licensed")
        self.assertIsNone(api_coverage.classify("zatgo_core.api.v1.made_up.thing"))


class TestLicensingApiAccess(IntegrationTestCase):
    """Every licensing endpoint refuses Guest, and all but the client contract refuse a user without a ZatGo or
    System Manager role."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        import zatgo_core.api.v1.licensing as licensing_api

        cls.endpoints = _endpoints(licensing_api)
        cls.plain = f"zg-lic-plain-{random_string(6).lower()}@example.com"
        frappe.get_doc({"doctype": "User", "email": cls.plain, "first_name": "Plain", "send_welcome_email": 0,
                        "roles": [{"role": "Sales User"}]}).insert(ignore_permissions=True)

    def tearDown(self) -> None:
        frappe.set_user("Administrator")

    @staticmethod
    def _call(fn):
        args = {name: "x" for name, p in inspect.signature(fn).parameters.items()
                if p.default is inspect.Parameter.empty}
        return fn(**args)

    def _refused(self, user: str, skip: tuple[str, ...] = ()) -> list[str]:
        frappe.set_user(user)
        open_ = []
        for path, fn in sorted(self.endpoints.items()):
            if path.endswith(skip):
                continue
            try:
                self._call(fn)
                open_.append(path)
            except frappe.PermissionError:
                pass
            except Exception:
                open_.append(f"{path} (raised something other than PermissionError)")
        return open_

    def test_guest_is_refused_everywhere(self) -> None:
        self.assertGreater(len(self.endpoints), 20)
        self.assertEqual(self._refused("Guest"), [])

    def test_a_user_without_licensing_roles_only_reads_the_client_contract(self) -> None:
        self.assertEqual(self._refused(self.plain, skip=("capabilities.get",)), [])
        frappe.set_user(self.plain)
        self.assertIn("features", self.endpoints["zatgo_core.api.v1.licensing.capabilities.get"]()["data"])
