"""ZG Edition on a real site: issuer gate, controller rules, versioning, duplicate / archive, import / export, API."""

from __future__ import annotations

import json

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import random_string

from zatgo_core.api.v1.licensing import editions as api
from zatgo_core.licensing import edition_config, editions, issuer
from zatgo_core.licensing.sync import sync_registry

DOCTYPE = "ZG Edition"


def _id(prefix: str = "t") -> str:
    return f"{prefix}_{random_string(8).lower()}"


class _Issuer:
    """Make this site the issuer for the duration of a test (site_config is bench-owned in real life)."""

    def __enter__(self):
        self.before = frappe.local.conf.get(issuer.CONF_KEY)
        frappe.local.conf[issuer.CONF_KEY] = 1
        return self

    def __exit__(self, *exc):
        if self.before is None:
            frappe.local.conf.pop(issuer.CONF_KEY, None)
        else:
            frappe.local.conf[issuer.CONF_KEY] = self.before


class TestEditions(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        frappe.set_user("Administrator")
        sync_registry()

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        frappe.local.conf.pop(issuer.CONF_KEY, None)

    def _config(self, **kw):
        base = dict(edition_id=_id(), edition_name="Test edition", features={"sales.invoice": [], "sales.order": []})
        base.update(kw)
        return edition_config.build_config(**base)

    # -- issuer gate ------------------------------------------------------------------------------------------

    def test_a_customer_site_cannot_write_editions(self) -> None:
        self.assertFalse(issuer.is_issuer_site())
        with self.assertRaises(frappe.PermissionError):
            editions.save(self._config())
        doc = frappe.new_doc(DOCTYPE)
        doc.update({"edition_id": _id(), "edition_name": "x"})
        with self.assertRaises(frappe.PermissionError):
            doc.insert(ignore_permissions=True)  # the controller refuses, permissions or not
        self.assertEqual(editions.seed_presets(), 0)

    def test_only_a_system_manager_writes_on_the_issuer(self) -> None:
        with _Issuer():
            frappe.set_user(self._user("ZG Application Admin"))
            with self.assertRaises(frappe.PermissionError):
                editions.save(self._config())

    # -- presets ----------------------------------------------------------------------------------------------

    def test_presets_seed_once_and_never_overwrite(self) -> None:
        with _Issuer():
            editions.seed_presets()
            for p in edition_config.presets():
                self.assertTrue(frappe.db.exists(DOCTYPE, p["edition_id"]), p["edition_id"])
            self.assertEqual(frappe.db.get_value(DOCTYPE, "sales", "status"), "Active")
            self.assertEqual(frappe.db.get_value(DOCTYPE, "custom", "status"), "Draft")
            frappe.db.set_value(DOCTYPE, "sales", "edition_name", "Our Sales", update_modified=False)
            self.assertEqual(editions.seed_presets(), 0)
            self.assertEqual(frappe.db.get_value(DOCTYPE, "sales", "edition_name"), "Our Sales")

    # -- controller rules -------------------------------------------------------------------------------------

    def test_active_needs_its_dependencies_draft_does_not(self) -> None:
        with _Issuer():
            cfg = self._config(features={"pos.zatgo_pos": []}, status="Active")
            with self.assertRaises(frappe.ValidationError):
                editions.save(cfg)
            saved = editions.save({**cfg, "status": "Draft"})
            doc = frappe.get_doc(DOCTYPE, saved["edition_id"])
            self.assertEqual(doc.missing_count, 4)
            report = json.loads(doc.dependency_report)
            self.assertEqual({m["feature"] for m in report["missing"]},
                             {"pos.profile", "pos.session", "sales.invoice", "accounting.payment_entry"})
            self.assertEqual(saved["features"], {"pos.zatgo_pos": []}, "nothing was added for it")

    def test_invalid_features_are_refused(self) -> None:
        with _Issuer():
            for features in ({"foundation.setup": []}, {"sales.nothing": []}, {"sales.invoice": ["import"]}):
                with self.subTest(features=features), self.assertRaises(frappe.ValidationError):
                    editions.save(self._config(features=features))

    def test_version_bumps_only_when_the_grant_changes(self) -> None:
        with _Issuer():
            cfg = editions.save(self._config())
            self.assertEqual(cfg["version"], 1)
            cfg = editions.save({**cfg, "edition_name": "Renamed"})
            self.assertEqual(cfg["version"], 1)
            cfg = editions.save({**cfg, "features": {**cfg["features"], "sales.quotation": []}})
            self.assertEqual(cfg["version"], 2)
            cfg = editions.save({**cfg, "features": {**cfg["features"], "sales.invoice": ["read", "print"]}})
            self.assertEqual(cfg["version"], 3)
            self.assertEqual(cfg["features"]["sales.invoice"], ["read", "print"])

    def test_feature_changes_are_audited(self) -> None:
        with _Issuer():
            cfg = editions.save(self._config())
            editions.save({**cfg, "features": {"sales.invoice": []}})
            rows = frappe.get_all("ZG Audit Log", filters={"doctype_name": DOCTYPE, "document_name": cfg["edition_id"],
                                                           "fieldname": "features"}, pluck="new_value")
            self.assertEqual(len(rows), 2)
            self.assertIn(json.dumps({"sales.invoice": []}), rows)
            noisy = frappe.get_all("ZG Audit Log", filters={"doctype_name": DOCTYPE, "document_name": cfg["edition_id"],
                                                            "fieldname": "dependency_report"})
            self.assertEqual(noisy, [])

    def test_archive_freezes_and_only_drafts_are_deleted(self) -> None:
        with _Issuer():
            cfg = editions.save(self._config(status="Active"))
            eid = cfg["edition_id"]
            with self.assertRaises(frappe.ValidationError):
                frappe.delete_doc(DOCTYPE, eid)
            editions.set_status(eid, "Archived")
            with self.assertRaises(frappe.ValidationError):
                editions.save({**editions.get_config(eid), "features": {"sales.invoice": []}})
            editions.set_status(eid, "Draft")
            editions.save({**editions.get_config(eid), "features": {"sales.invoice": []}})
            frappe.delete_doc(DOCTYPE, eid)
            self.assertFalse(frappe.db.exists(DOCTYPE, eid))

    def test_duplicate_is_a_draft_copy(self) -> None:
        with _Issuer():
            src = editions.save(self._config(status="Active"))
            new_id = _id("dup")
            copy = editions.duplicate(src["edition_id"], new_id, "Copy")
            self.assertEqual(copy["status"], "Draft")
            self.assertEqual(copy["features"], src["features"])
            self.assertEqual(copy["preset"], src["edition_id"])
            diff = editions.compare(src["edition_id"], new_id)
            self.assertEqual((diff["only_a"], diff["only_b"], diff["actions_differ"]), ([], [], []))

    # -- export / import --------------------------------------------------------------------------------------

    def test_export_import_round_trip_with_conflict_detection(self) -> None:
        with _Issuer():
            src = editions.save(self._config(status="Active"))
            payload = editions.export(src["edition_id"])
            self.assertIn("resolved", payload)
            self.assertEqual(editions.preview_import(payload)["action"], "unchanged")

            new_id = _id("imp")
            fresh = {**payload, "edition_id": new_id}
            preview = editions.preview_import(json.dumps(fresh))
            self.assertEqual((preview["action"], preview["conflict"], preview["problems"]), ("create", False, []))
            self.assertFalse(frappe.db.exists(DOCTYPE, new_id), "a preview writes nothing")
            self.assertEqual(editions.import_config(json.dumps(fresh))["action"], "create")

            changed = {**fresh, "features": {"sales.invoice": []}}
            preview = editions.preview_import(changed)
            self.assertEqual((preview["action"], preview["conflict"]), ("update", True))
            self.assertEqual(preview["diff"]["only_a"], ["sales.order"])
            with self.assertRaises(frappe.ValidationError):
                editions.import_config(changed)
            editions.import_config(changed, overwrite=True)
            self.assertEqual(editions.get_config(new_id)["features"], {"sales.invoice": []})
            history = [h["document_name"] for h in editions.import_history()]
            self.assertGreaterEqual(history.count(new_id), 2)

    def test_a_licence_or_broken_file_is_refused(self) -> None:
        with _Issuer():
            payload = {**self._config(), "type": edition_config.LICENCE_FILE_TYPE}
            self.assertEqual(editions.preview_import(payload)["action"], "refuse")
            with self.assertRaises(frappe.ValidationError):
                editions.import_config(payload)
            with self.assertRaises(frappe.ValidationError):
                editions.preview_import("{not json")

    def test_an_active_file_missing_dependencies_imports_as_draft(self) -> None:
        with _Issuer():
            payload = self._config(features={"pos.zatgo_pos": []}, status="Active")
            preview = editions.preview_import(payload)
            self.assertEqual(preview["config"]["status"], "Draft")
            result = editions.import_config(payload)
            self.assertEqual(result["config"]["status"], "Draft")

    # -- API --------------------------------------------------------------------------------------------------

    def test_api_reads_for_read_only_role_and_refuses_its_writes(self) -> None:
        with _Issuer():
            eid = editions.save(self._config())["edition_id"]
            frappe.set_user(self._user("ZG Read Only"))
            builder = api.get_builder()["data"]
            self.assertFalse(builder["can_edit"])
            self.assertTrue(builder["is_issuer"])
            self.assertIn(eid, [e["name"] for e in builder["editions"]])
            self.assertTrue(api.get_edition(eid)["data"]["inspection"]["ok"])
            self.assertTrue(api.inspect(json.dumps({"sales.invoice": []}))["success"])
            with self.assertRaises(frappe.PermissionError):
                api.save_edition(json.dumps(self._config()))
            with self.assertRaises(frappe.PermissionError):
                api.preview_import(json.dumps(self._config()))

    def test_api_needs_a_reading_role(self) -> None:
        frappe.set_user(self._user("Sales User"))
        with self.assertRaises(frappe.PermissionError):
            api.get_builder()

    def test_builder_says_read_only_off_the_issuer(self) -> None:
        data = api.get_builder()["data"]
        self.assertFalse(data["is_issuer"])
        self.assertFalse(data["can_edit"])
        self.assertEqual(len(data["presets"]), 10)

    def test_default_roles_of_presets_exist(self) -> None:
        for p in edition_config.presets():
            for role in p["default_roles"]:
                self.assertTrue(frappe.db.exists("Role", role), f"{p['edition_id']}: {role}")

    def _user(self, role: str) -> str:
        email = f"zg-ed-{random_string(8).lower()}@example.com"
        frappe.get_doc({"doctype": "User", "email": email, "first_name": "Edition test", "send_welcome_email": 0,
                        "roles": [{"role": role}]}).insert(ignore_permissions=True)
        return email
