"""Client capability contract on a real site: unrestricted, licensed, platform-narrowed, read-only; the licence
block in VanSaleX `me`, POS settings and MyBis context. Throwaway key outside sites/."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import getdate, nowdate, random_string

from zatgo_core.api.v1.licensing import capabilities as api
from zatgo_core.licensing import capabilities, crypto, edition_config, editions, entitlement, issuer, issuing
from zatgo_core.licensing import licence_policy, licences, site_identity


class TestCapabilities(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.tmp = tempfile.mkdtemp(prefix="zg-licence-caps-")
        cls.key_path = os.path.join(cls.tmp, "issuer.pem")
        cls.key = crypto.generate_private_key()
        crypto.write_private_key(cls.key, cls.key_path)
        cls.kid = crypto.key_id(cls.key.public_key())
        cls.site = site_identity.site_id(create=True)

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
        frappe.db.delete("DefaultValue", {"parent": "__default", "defkey": licence_policy.HWM_KEY})
        licences.clear_cache()

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        for key in (issuer.CONF_KEY, issuing.KEY_CONF, entitlement.CONF_KEY):
            frappe.local.conf.pop(key, None)
        frappe.db.delete("DefaultValue", {"parent": "__default", "defkey": licence_policy.HWM_KEY})
        licences.clear_cache()

    def _license(self, edition_id="sales", **kw):
        issued = issuing.issue(edition_id, "Caps Test Co", [self.site], **kw)
        licences.import_licence(issued["file"])
        frappe.local.conf[entitlement.CONF_KEY] = 1
        licences.clear_cache()
        return issued

    # -- shapes -------------------------------------------------------------------------------------------------

    def test_unrestricted_site(self) -> None:
        caps = capabilities.for_user("mobile")
        self.assertEqual((caps["schema_version"], caps["product_id"]), (1, "zatgo_erp"))
        self.assertFalse(caps["licence"]["enforced"])
        self.assertTrue(all(v is None for v in caps["modules"].values()))
        self.assertIsNone(caps["features"]["sales.invoice"]["licensed"])
        self.assertIn("submit", caps["features"]["sales.invoice"]["actions"])
        self.assertEqual(caps["platforms"], {"desk": 1, "desktop": 1, "mobile": 1})
        self.assertTrue(caps["platform_allowed"])
        self.assertEqual(caps["digest"], capabilities.for_user("mobile")["digest"])
        self.assertIn("System Manager", caps["user"]["roles"])

    def test_licensed_site(self) -> None:
        self._license()
        caps = capabilities.for_user("mobile")
        lic = caps["licence"]
        self.assertTrue(lic["enforced"] and lic["licensed"])
        self.assertEqual(lic["edition_id"], "sales")
        self.assertTrue(caps["features"]["sales.invoice"]["licensed"])
        self.assertFalse(caps["features"]["inventory.stock_transfer"]["licensed"])
        self.assertEqual(caps["features"]["inventory.stock_transfer"]["actions"], [])
        self.assertTrue(caps["modules"]["sales"])
        self.assertFalse(caps["modules"]["inventory"])
        sales_platforms = edition_config.get_preset("sales")["platforms"]
        self.assertEqual(caps["platforms"], sales_platforms)
        self.assertEqual(caps["platform_allowed"], bool(sales_platforms["mobile"]))
        self.assertFalse(caps["apps"].get("vansalex"), "VanSaleX is not in a Sales licence")

    def test_platforms_narrow_the_licence(self) -> None:
        cfg = edition_config.build_config(
            edition_id=f"desk_only_{random_string(5).lower()}", edition_name="Desk only", status="Active",
            platforms={"desk": 1},
            features={"vansalex.app": [], "vansalex.sales_invoice": [], "sales.invoice": [],
                      "accounting.payment_entry": []},
        )
        editions.save(cfg)
        self._license(cfg["edition_id"])
        ent = entitlement.active()
        self.assertIn("vansalex.app", ent.features, "desk + mobile: reachable on Desk")
        self.assertNotIn("vansalex.sales_invoice", ent.features, "mobile only: not licensed on a Desk-only licence")
        self.assertIn("sales.invoice", ent.features)
        caps = capabilities.for_user("mobile")
        self.assertFalse(caps["platform_allowed"])
        self.assertFalse(caps["features"]["vansalex.sales_invoice"]["licensed"])

    def test_read_only_is_in_the_block(self) -> None:
        self._license(expiry_date=str(getdate(nowdate()) + timedelta(days=1)), grace_days=0)
        later = datetime.combine(getdate(nowdate()) + timedelta(days=5), datetime.min.time()).replace(
            hour=12, tzinfo=timezone.utc)
        with patch("zatgo_core.services.subscription_gate.now_utc", return_value=later):
            block = capabilities.licence_block()
        self.assertTrue(block["read_only"])
        self.assertEqual(block["read_only_reason"], "licence_expired")
        self.assertIn("expired", block["message"])

    def test_safe_block_never_raises(self) -> None:
        with patch("zatgo_core.licensing.capabilities.licence_block", side_effect=RuntimeError("boom")):
            block = capabilities.safe_licence_block()
        self.assertTrue(block["error"])
        self.assertFalse(block["read_only"])

    # -- the existing client payloads ---------------------------------------------------------------------------

    def test_client_payloads_carry_the_block(self) -> None:
        from zatgo_core.api.v1 import pos_settings
        from zatgo_core.api.v1.vansalex import me

        self.assertIn("licence", me.context()["data"])
        from zatgo_core.services import app_state

        if app_state.is_on("zatgo_pos"):
            self.assertIn("licence", pos_settings.get()["data"])
        if app_state.is_on("mybis"):
            from zatgo_core.api.v1.mybis import context

            self.assertIn("licence", context.get_context()["data"])

    def test_api_needs_a_login(self) -> None:
        frappe.set_user("Guest")
        with self.assertRaises(frappe.PermissionError):
            api.get()
        frappe.set_user("Administrator")
        self.assertEqual(api.get("desk")["data"]["platform"], "desk")
