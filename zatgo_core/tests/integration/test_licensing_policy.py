"""Licence time policy and limits on a real site: grace, read-only after expiry (through the subscription gate),
clock rollback, enforcement without a licence, user and company limits. Throwaway key outside sites/."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import getdate, nowdate, random_string

from zatgo_core.licensing import crypto, editions, entitlement, gate, issuer, issuing, licence_overview
from zatgo_core.licensing import licence_policy, licences, site_identity
from zatgo_core.services import subscription_gate
from zatgo_core.tests.integration._fixtures import get_or_create_test_company


def _clear_hwm() -> None:
    frappe.db.delete("DefaultValue", {"parent": "__default", "defkey": licence_policy.HWM_KEY})
    licences.clear_cache()


class TestLicencePolicy(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.tmp = tempfile.mkdtemp(prefix="zg-licence-policy-")
        cls.key_path = os.path.join(cls.tmp, "issuer.pem")
        cls.key = crypto.generate_private_key()
        crypto.write_private_key(cls.key, cls.key_path)
        cls.kid = crypto.key_id(cls.key.public_key())
        cls.site = site_identity.site_id(create=True)
        cls.company = get_or_create_test_company()
        cls.manager = f"zg-lic-pol-{random_string(6).lower()}@example.com"
        frappe.get_doc({"doctype": "User", "email": cls.manager, "first_name": "Licence policy",
                        "send_welcome_email": 0, "roles": [{"role": "System Manager"}]}).insert(ignore_permissions=True)

    @classmethod
    def tearDownClass(cls) -> None:
        crypto.trust_for_tests(None)
        try:
            os.remove(cls.key_path)
            os.rmdir(cls.tmp)
        except OSError:
            pass
        super().tearDownClass()

    def setUp(self) -> None:
        crypto.trust_for_tests({self.kid: crypto.b64e(crypto.raw_public(self.key.public_key()))})
        frappe.local.conf[issuer.CONF_KEY] = 1
        frappe.local.conf[issuing.KEY_CONF] = self.key_path
        editions.seed_presets()
        frappe.db.set_value(licences.DOCTYPE, {"is_current": 1}, "is_current", 0, update_modified=False)
        _clear_hwm()

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        for key in (issuer.CONF_KEY, issuing.KEY_CONF, entitlement.CONF_KEY, licence_policy.TOLERANCE_CONF):
            frappe.local.conf.pop(key, None)
        frappe.local.request = None
        _clear_hwm()

    def _import(self, **kw):
        issued = issuing.issue(kw.pop("edition_id", "sales"), "Policy Test Co", [self.site], **kw)
        licences.import_licence(issued["file"])
        licences.clear_cache()
        return issued

    @staticmethod
    def _at(days: int) -> datetime:
        base = datetime.combine(getdate(nowdate()), datetime.min.time()).replace(hour=12, tzinfo=timezone.utc)
        return base + timedelta(days=days)

    def _switch_on(self) -> None:
        frappe.local.conf[entitlement.CONF_KEY] = 1
        licences.clear_cache()

    # -- expiry and grace -------------------------------------------------------------------------------------

    def test_grace_then_read_only(self) -> None:
        self._import(expiry_date=str(getdate(nowdate()) + timedelta(days=1)), grace_days=2)
        self.assertFalse(subscription_gate.current(self._at(10))["read_only"], "switch off: never read-only")
        self._switch_on()
        self.assertFalse(subscription_gate.current(self._at(1))["read_only"])
        _clear_hwm()
        self.assertEqual(licence_policy.state(self._at(2))["state"], "grace")
        self.assertFalse(subscription_gate.current(self._at(3))["read_only"])
        _clear_hwm()
        info = subscription_gate.current(self._at(5))
        self.assertTrue(info["read_only"])
        self.assertEqual((info["reason"], info["managed"]), ("licence_expired", True))

    def test_expired_licence_blocks_writes_but_not_a_new_licence(self) -> None:
        self._import(expiry_date=str(getdate(nowdate()) + timedelta(days=1)), grace_days=0)
        self._switch_on()
        later = self._at(5)
        with patch("zatgo_core.services.subscription_gate.now_utc", return_value=later):
            self.assertIn("expired", subscription_gate.read_only_message())
            frappe.set_user(self.manager)
            with self.assertRaises(frappe.PermissionError):
                frappe.get_doc({"doctype": "ToDo", "description": "after expiry"}).insert(ignore_permissions=True)
            self.assertTrue(subscription_gate._exempt("Licence"))
            if not subscription_gate.raw_state():
                payload = subscription_gate.boot_payload()
                self.assertTrue(payload["read_only"])
                self.assertEqual(payload["reason"], "licence_expired")

    def test_perpetual_never_turns_read_only(self) -> None:
        self._import(licence_type="Perpetual")
        self._switch_on()
        self.assertFalse(subscription_gate.current(self._at(3650))["read_only"])

    # -- clock rollback ---------------------------------------------------------------------------------------

    def test_clock_rollback(self) -> None:
        self._import(licence_type="Perpetual")
        self._switch_on()
        licence_policy.write_mark(self._at(5))
        licences.clear_cache()
        info = subscription_gate.current(self._at(0))
        self.assertEqual((info["read_only"], info["reason"]), (True, "clock_rollback"))
        with patch("zatgo_core.services.subscription_gate.now_utc", return_value=self._at(0)):
            self.assertIn("clock", subscription_gate.read_only_message())
        frappe.local.conf[licence_policy.TOLERANCE_CONF] = 24 * 10
        licences.clear_cache()
        self.assertFalse(subscription_gate.current(self._at(0))["read_only"])

    def test_the_mark_only_moves_forward(self) -> None:
        self._import(licence_type="Perpetual")
        self._switch_on()
        licence_policy.state(self._at(2))
        licences.clear_cache()
        mark = licence_policy.high_water_mark()
        self.assertEqual(mark, self._at(2))
        licence_policy.state(self._at(1))
        licences.clear_cache()
        self.assertEqual(licence_policy.high_water_mark(), self._at(2))

    # -- enforcement without a licence ------------------------------------------------------------------------

    def test_switch_on_without_a_licence_gives_the_basics_only(self) -> None:
        self._switch_on()
        active = entitlement.active()
        self.assertEqual(active.source, "none")
        self.assertFalse(gate.decide("Sales Invoice", "create", frappe._dict(doctype="Sales Invoice", is_return=0),
                                     active)["allowed"])
        self.assertTrue(gate.decide("Company", "write", frappe._dict(doctype="Company"), active)["allowed"])
        self.assertFalse(entitlement.describe()["licensed"])
        codes = {w["code"]: w["level"] for w in licence_overview.overview()["warnings"]}
        self.assertEqual(codes.get("no_licence"), "danger")
        self.assertFalse(subscription_gate.current()["read_only"], "no licence is not read-only, just the basics")

    # -- limits -----------------------------------------------------------------------------------------------

    def _new_user(self, user_type="System User", enabled=1):
        # A System User needs a desk role: Frappe turns a user without one into a Website User.
        roles = [{"role": "Sales User"}] if user_type == "System User" else []
        return frappe.get_doc({"doctype": "User", "email": f"zg-lim-{random_string(6).lower()}@example.com",
                               "first_name": "Limit", "send_welcome_email": 0, "user_type": user_type,
                               "enabled": enabled, "roles": roles})

    def test_user_limit(self) -> None:
        disabled = self._new_user(enabled=0).insert(ignore_permissions=True)
        self._import(limits={"max_users": licence_overview.active_users()})
        self._switch_on()
        frappe.set_user(self.manager)
        with self.assertRaises(frappe.PermissionError) as ctx:
            self._new_user().insert(ignore_permissions=True)
        self.assertIn("users", str(ctx.exception))
        self._new_user(user_type="Website User").insert(ignore_permissions=True)  # not a licensed user
        doc = frappe.get_doc("User", disabled.name)
        doc.enabled = 1
        with self.assertRaises(frappe.PermissionError):
            doc.save(ignore_permissions=True)
        me = frappe.get_doc("User", self.manager)
        me.last_name = "Edited"
        me.save(ignore_permissions=True)  # an existing user is never refused

    def test_company_limit(self) -> None:
        self._import(limits={"max_companies": frappe.db.count("Company")})
        self._switch_on()
        frappe.set_user(self.manager)
        with self.assertRaises(frappe.PermissionError):
            frappe.get_doc({"doctype": "Company", "company_name": f"Limit Co {random_string(4)}",
                            "abbr": random_string(4).upper(), "default_currency": "SAR",
                            "country": "Saudi Arabia"}).insert(ignore_permissions=True)
        existing = frappe.get_doc("Company", self.company)
        existing.save(ignore_permissions=True)  # changing an existing company is fine

    def test_no_limits_without_enforcement(self) -> None:
        self._import(limits={"max_users": 1})
        frappe.set_user(self.manager)
        self._new_user().insert(ignore_permissions=True)

    # -- page -------------------------------------------------------------------------------------------------

    def test_page_warns_about_grace_and_read_only(self) -> None:
        self._import(expiry_date=str(getdate(nowdate()) + timedelta(days=1)), grace_days=3)
        self._switch_on()
        codes = {w["code"] for w in licence_overview.overview(self._at(2))["warnings"]}
        self.assertIn("grace", codes)
        codes = {w["code"] for w in licence_overview.overview(self._at(9))["warnings"]}
        self.assertIn("read_only", codes)
