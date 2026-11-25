"""Licences end to end on a real site: issue on the issuer, import on the customer, binding, replacement,
revocation, tampering, and the licence driving enforcement. Uses a throwaway signing key kept outside sites/."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import timedelta

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import getdate, nowdate, random_string

from zatgo_core.api.v1.licensing import licences as api
from zatgo_core.licensing import crypto, editions, entitlement, gate, issuer, issuing, licence_format, licences
from zatgo_core.licensing import site_identity
from zatgo_core.services import subscription_gate


class TestLicences(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.tmp = tempfile.mkdtemp(prefix="zg-licence-test-")
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
        licences.clear_cache()

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        for key in (issuer.CONF_KEY, issuing.KEY_CONF, entitlement.CONF_KEY):
            frappe.local.conf.pop(key, None)
        entitlement.use(None)
        licences.clear_cache()

    def _issue(self, **kw):
        kw.setdefault("site_ids", [self.site])
        return issuing.issue(kw.pop("edition_id", "sales"), kw.pop("customer_name", "Acme Test"), kw.pop("site_ids"),
                             **kw)

    def _sealed(self, **fields):
        """A hand-made payload (dates the issuer would not produce), signed with the test key."""
        body = {
            "schema_version": 1, "licence_id": str(uuid.uuid4()), "licence_number": f"T-{random_string(6)}",
            "licence_version": 1, "product_id": "zatgo_erp", "customer_id": "", "customer_name": "Acme",
            "site_ids": [self.site], "site_names": [], "edition_id": "sales", "edition_name": "ZatGo Sales",
            "edition_version": 1, "features": {"sales.invoice": []}, "modules": ["sales"], "licence_type": "Yearly",
            "issue_date": "2020-01-01", "start_date": "2020-01-01", "expiry_date": "2020-12-31", "grace_days": 0,
            "platforms": {"desk": 1, "desktop": 0, "mobile": 0},
            "limits": {"max_users": 5, "max_companies": 1, "max_sites": 1}, "device_policy": "none",
            "issued_at": "2020-01-01T00:00:00", "key_id": self.kid,
        }
        body.update(fields)
        return licence_format.seal(body, self.key)

    # -- issue -> import ------------------------------------------------------------------------------------

    def test_issue_and_import_round_trip(self) -> None:
        issued = self._issue(customer_id="C-77")
        self.assertTrue(issued["filename"].endswith(".zglicence"))
        hist = frappe.get_doc(issuing.HISTORY, issued["licence_number"])
        self.assertEqual(hist.licence_file, issued["file"])
        self.assertNotIn("PRIVATE", issued["file"])
        result = licences.import_licence(issued["file"])
        self.assertTrue(result["present"])
        self.assertEqual(result["licence_number"], issued["licence_number"])
        self.assertEqual(result["edition_id"], "sales")
        self.assertIn(result["status"], ("Active", "Expiring"))
        self.assertEqual(licences.current_doc().licence_number, issued["licence_number"])
        events = frappe.get_all("Audit Log", filters={"fieldname": ["in", ["licence_issued", "licence_imported"]],
                                                         "document_name": ["in", [issued["licence_number"],
                                                                                  licences.current_doc().name]]},
                                pluck="fieldname")
        self.assertEqual(sorted(events), ["licence_imported", "licence_issued"])

    def test_the_licence_drives_enforcement(self) -> None:
        licences.import_licence(self._issue()["file"])
        self.assertIsNone(entitlement.active(), "no switch: still unrestricted")
        frappe.local.conf[entitlement.CONF_KEY] = 1
        licences.clear_cache()
        active = entitlement.active()
        self.assertIsNotNone(active)
        self.assertTrue(active.source.startswith("licence:"))
        si = frappe._dict(doctype="Sales Invoice", is_return=0)
        se = frappe._dict(doctype="Stock Entry", purpose="Material Receipt")
        self.assertTrue(gate.decide("Sales Invoice", "submit", si, active)["allowed"])
        self.assertFalse(gate.decide("Stock Entry", "create", se, active)["allowed"])

    def test_a_licence_for_another_site_is_refused(self) -> None:
        other = self._issue(site_ids=[str(uuid.uuid4())])
        with self.assertRaises(frappe.ValidationError) as ctx:
            licences.import_licence(other["file"])
        self.assertIn("another site", str(ctx.exception))
        named = self._issue(site_names=["not-this-site.example.com"])
        with self.assertRaises(frappe.ValidationError):
            licences.import_licence(named["file"])

    def test_tampered_files_and_untrusted_keys_are_refused(self) -> None:
        env = json.loads(self._issue()["file"])
        body = json.loads(crypto.b64d(env["payload"]))
        body["features"]["inventory.stock_transfer"] = []
        env["payload"] = crypto.b64e(licence_format.canonical(body))
        with self.assertRaises(frappe.ValidationError) as ctx:
            licences.import_licence(json.dumps(env))
        self.assertIn("signature", str(ctx.exception))
        stranger = crypto.generate_private_key()
        with self.assertRaises(frappe.ValidationError) as ctx:
            licences.import_licence(licence_format.seal(json.loads(crypto.b64d(json.loads(self._issue()["file"])["payload"])),
                                                        stranger))
        self.assertIn("does not trust", str(ctx.exception))
        rejected = frappe.get_all("Audit Log", filters={"fieldname": "licence_rejected"}, pluck="new_value")
        self.assertTrue(any("bad_signature" in r for r in rejected))

    def test_expired_and_not_yet_valid_are_refused(self) -> None:
        with self.assertRaises(frappe.ValidationError) as ctx:
            licences.import_licence(self._sealed())
        self.assertIn("expired", str(ctx.exception))
        future = str(getdate(nowdate()) + timedelta(days=30))
        later = self._issue(start_date=future)
        with self.assertRaises(frappe.ValidationError) as ctx:
            licences.import_licence(later["file"])
        self.assertIn("starts on", str(ctx.exception))

    def test_replacement_versions_only_move_forward(self) -> None:
        v1 = self._issue()
        v2 = self._issue(replaces=v1["licence_id"], licence_type="Perpetual")
        self.assertEqual(v2["licence_version"], 2)
        licences.import_licence(v2["file"])
        with self.assertRaises(frappe.ValidationError) as ctx:
            licences.import_licence(v1["file"])
        self.assertIn("newer version", str(ctx.exception))
        with self.assertRaises(frappe.ValidationError):
            licences.import_licence(v2["file"])  # already imported
        self.assertEqual(licences.current_doc().licence_version, 2)
        self.assertIsNone(licences.current_doc().expiry_date)

    def test_revocation(self) -> None:
        issued = self._issue()
        licences.import_licence(issued["file"])
        revocation = issuing.revocation_list([issued["licence_id"]])
        self.assertTrue(frappe.db.get_value(issuing.HISTORY, issued["licence_number"], "revoked_on"))
        out = licences.import_revocation(revocation["file"])
        self.assertEqual(len(out["revoked"]), 1)
        self.assertEqual(licences.current_doc().status, "Revoked")
        frappe.local.conf[entitlement.CONF_KEY] = 1
        licences.clear_cache()
        active = entitlement.active()
        self.assertEqual(set(active.features), {f for f in active.features if f.startswith("foundation.")},
                         "a revoked licence gives the foundation only")
        newer = self._issue(replaces=issued["licence_id"])
        with self.assertRaises(frappe.ValidationError):
            licences.import_licence(newer["file"])
        with self.assertRaises(frappe.ValidationError):
            licences.import_revocation(issued["file"])  # a licence is not a revocation list

    def test_an_edited_record_grants_nothing(self) -> None:
        licences.import_licence(self._issue()["file"])
        doc = licences.current_doc()
        env = json.loads(doc.licence_file)
        body = json.loads(crypto.b64d(env["payload"]))
        body["features"] = {"inventory.stock_transfer": []}
        env["payload"] = crypto.b64e(licence_format.canonical(body))
        frappe.db.set_value(licences.DOCTYPE, doc.name, "licence_file", json.dumps(env), update_modified=False)
        licences.clear_cache()
        self.assertFalse(licences.verify_stored(licences.current_doc())["ok"])
        frappe.local.conf[entitlement.CONF_KEY] = 1
        active = entitlement.active()
        self.assertNotIn("inventory.stock_transfer", active.features)
        self.assertNotIn("sales.invoice", active.features)
        self.assertFalse(api.verify_licence()["data"]["ok"])

    def test_records_cannot_be_written_by_hand(self) -> None:
        licences.import_licence(self._issue()["file"])
        doc = licences.current_doc()
        doc.max_users = 0
        with self.assertRaises(frappe.PermissionError):
            doc.save(ignore_permissions=True)
        with self.assertRaises(frappe.PermissionError):
            frappe.delete_doc(licences.DOCTYPE, doc.name, ignore_permissions=True)
        hist = frappe.get_last_doc(issuing.HISTORY)
        hist.customer_name = "x"
        with self.assertRaises(frappe.PermissionError):
            hist.save(ignore_permissions=True)

    # -- issuer guards ----------------------------------------------------------------------------------------

    def test_issuing_needs_the_issuer_site_an_active_edition_and_a_trusted_safe_key(self) -> None:
        frappe.local.conf.pop(issuer.CONF_KEY)
        with self.assertRaises(frappe.PermissionError):
            self._issue()
        frappe.local.conf[issuer.CONF_KEY] = 1
        with self.assertRaises(frappe.ValidationError):
            self._issue(edition_id="custom")  # a Draft
        crypto.trust_for_tests(None)
        with self.assertRaises(frappe.ValidationError) as ctx:
            self._issue()
        self.assertIn("public_keys.json", str(ctx.exception))
        crypto.trust_for_tests({self.kid: crypto.b64e(crypto.raw_public(self.key.public_key()))})
        inside = frappe.get_site_path("private", f"zg-test-{random_string(6)}.pem")
        crypto.write_private_key(self.key, inside)
        try:
            frappe.local.conf[issuing.KEY_CONF] = inside
            with self.assertRaises(frappe.ValidationError) as ctx:
                self._issue()
            self.assertIn("sites/", str(ctx.exception))
        finally:
            os.remove(inside)

    # -- API and other gates ----------------------------------------------------------------------------------

    def test_api_permissions(self) -> None:
        file = self._issue()["file"]
        user = f"zg-lic-api-{random_string(6).lower()}@example.com"
        frappe.get_doc({"doctype": "User", "email": user, "first_name": "Licence API", "send_welcome_email": 0,
                        "roles": [{"role": "ZatGo Read Only"}]}).insert(ignore_permissions=True)
        frappe.set_user(user)
        self.assertIn("present", api.current_licence()["data"])
        for call in (lambda: api.import_licence(file), lambda: api.site_identity_info(), lambda: api.verify_licence()):
            with self.assertRaises(frappe.PermissionError):
                call()
        frappe.set_user("Administrator")
        data = api.site_identity_info()["data"]
        self.assertEqual(data["site_id"], self.site)
        self.assertEqual(data["product_id"], "zatgo_erp")

    def test_a_read_only_subscription_still_takes_a_licence(self) -> None:
        self.assertTrue(subscription_gate._exempt("Licence"))
