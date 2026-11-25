"""The Licence page's data on a real site: overview, module access, warnings, history, exports, issuer section,
and the ZatGo sidebar entries. Throwaway signing key kept outside sites/."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import timedelta

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import getdate, nowdate, random_string

from zatgo_core.api.v1.licensing import licences as api
from zatgo_core.licensing import crypto, editions, entitlement, issuer, issuing, licence_format, licence_overview
from zatgo_core.licensing import licences, site_identity


class TestLicencePage(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.tmp = tempfile.mkdtemp(prefix="zg-licence-page-")
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
        # Start each test without a licence in force (rows roll back with the test class).
        frappe.db.set_value(licences.DOCTYPE, {"is_current": 1}, "is_current", 0, update_modified=False)
        licences.clear_cache()

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        for key in (issuer.CONF_KEY, issuing.KEY_CONF, entitlement.CONF_KEY):
            frappe.local.conf.pop(key, None)
        licences.clear_cache()

    def _import(self, **kw):
        kw.setdefault("site_ids", [self.site])
        issued = issuing.issue(kw.pop("edition_id", "sales"), "Page Test Co", kw.pop("site_ids"), **kw)
        licences.import_licence(issued["file"])
        return issued

    def _codes(self, data):
        return {w["code"]: w["level"] for w in data["warnings"]}

    # -- without a licence --------------------------------------------------------------------------------------

    def test_no_licence(self) -> None:
        data = licence_overview.overview()
        self.assertFalse(data["licence"]["present"])
        self.assertEqual(self._codes(data).get("no_licence"), "info")
        self.assertTrue(all(f["licensed"] in (None, True) for m in data["modules"] for f in m["features"]))
        frappe.local.conf[entitlement.CONF_KEY] = 1
        self.assertEqual(self._codes(licence_overview.overview()).get("no_licence"), "danger")

    def test_shipped_keys_note(self) -> None:
        codes = self._codes(licence_overview.overview())
        self.assertEqual("no_trusted_keys" in codes, not crypto.shipped_keys())

    # -- with a licence -----------------------------------------------------------------------------------------

    def test_overview_and_module_access(self) -> None:
        issued = self._import(limits={"max_users": 1})
        data = licence_overview.overview()
        lic = data["licence"]
        self.assertTrue(lic["present"])
        self.assertEqual(lic["licence_number"], issued["licence_number"])
        self.assertTrue(lic["verified"])
        self.assertEqual(lic["usage"]["companies"], frappe.db.count("Company"))
        modules = {m["id"]: m for m in data["modules"]}
        self.assertEqual(modules["inventory"]["licensed"], 0)
        self.assertGreater(modules["sales"]["licensed"], 0)
        self.assertEqual(modules["foundation"]["licensed"], modules["foundation"]["total"])
        invoice = next(f for f in modules["sales"]["features"] if f["id"] == "sales.invoice")
        self.assertIn("submit", invoice["actions"])
        codes = self._codes(data)
        self.assertEqual(codes.get("not_enforced"), "info")
        if licence_overview.active_users() > 1:
            self.assertEqual(codes.get("users_exceeded"), "warning")

    def test_expiry_warnings(self) -> None:
        soon = str(getdate(nowdate()) + timedelta(days=10))
        self._import(licence_type="Yearly", expiry_date=soon)
        self.assertEqual(self._codes(licence_overview.overview()).get("expiring"), "warning")
        trial_end = str(getdate(nowdate()) + timedelta(days=3))
        self._import(licence_type="Trial", expiry_date=trial_end)
        data = licence_overview.overview()
        self.assertEqual(data["licence"]["status"], "Trial")
        self.assertEqual(self._codes(data).get("trial_ending"), "warning")

    def test_revoked_and_broken_licences_warn(self) -> None:
        issued = self._import()
        licences.import_revocation(issuing.revocation_list([issued["licence_id"]])["file"])
        data = licence_overview.overview()
        self.assertEqual(self._codes(data).get("revoked"), "danger")
        self.assertEqual({m["id"]: m["licensed"] for m in data["modules"]}["sales"], 0)

        self._import()
        doc = licences.current_doc()
        frappe.db.set_value(licences.DOCTYPE, doc.name, "licence_file", doc.licence_file.replace('"format": 1', '"format": 2'),
                            update_modified=False)
        self.assertIn("danger", {w["level"] for w in licence_overview.overview()["warnings"]
                                 if w["code"].startswith("invalid_")})

    def test_history_exports_and_downloads(self) -> None:
        issued = self._import()
        hist = licence_overview.history()
        self.assertTrue(any(r["licence_number"] == issued["licence_number"] and r["is_current"] for r in hist["licences"]))
        self.assertTrue(any(e["event"] == "licence_imported" for e in hist["events"]))
        req = api.site_request()["data"]
        self.assertEqual((req["type"], req["site_id"], req["product_id"]), ("zatgo.site_request", self.site, "zatgo_erp"))
        info = api.licence_info()["data"]
        self.assertEqual(info["type"], "zatgo.licence_info")
        with self.assertRaises(licence_format.LicenceError):
            licence_format.open_envelope(json.dumps(info, default=str))  # an export is never importable
        name = licences.current_doc().name
        file = api.download_licence(name)["data"]
        self.assertEqual(licence_format.open_envelope(file["file"])[0]["licence_number"], issued["licence_number"])
        again = api.download_issued(issued["licence_number"])["data"]
        self.assertEqual(again["file"], issued["file"])

    # -- API roles ----------------------------------------------------------------------------------------------

    def test_page_for_readers_and_managers(self) -> None:
        self._import()
        data = api.get_page()["data"]
        self.assertTrue(data["can_manage"])
        self.assertTrue(data["is_issuer"])
        self.assertIn("sales", [e["name"] for e in data["issuer"]["editions"]])
        self.assertTrue(data["issuer"]["issued"])
        user = f"zg-lic-page-{random_string(6).lower()}@example.com"
        frappe.get_doc({"doctype": "User", "email": user, "first_name": "Licence page", "send_welcome_email": 0,
                        "roles": [{"role": "ZatGo Read Only"}]}).insert(ignore_permissions=True)
        frappe.set_user(user)
        data = api.get_page()["data"]
        self.assertFalse(data["can_manage"])
        self.assertNotIn("issuer", data)
        for call in (api.site_request, api.licence_info, lambda: api.download_licence("x")):
            with self.assertRaises(frappe.PermissionError):
                call()

    def test_sidebar_lists_the_pages(self) -> None:
        from zatgo_core.services.core_sidebar import general_links

        targets = [row["link_to"] for row in general_links()]
        self.assertIn("zg-licence", targets)
        self.assertIn("zg-edition-builder", targets)
        self.assertEqual(targets[0], "zg-app-hub")
