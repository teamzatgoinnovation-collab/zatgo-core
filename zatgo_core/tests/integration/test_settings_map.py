"""Settings Map end to end on a real site: every app is described, a Check on a Single says whether it is stored, a change goes
through the DocType's own save (validation, audit), and secrets, tables, hidden / read-only fields, app switches, foreign
DocTypes and users without write permission are refused."""

from __future__ import annotations

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import random_string

from zatgo_core.api.v1 import settings_map as api
from zatgo_core.services import app_catalog, settings_map

VANSALEX = "VanSaleX Settings"
POS = "ZG POS Settings"


def _make_user(*roles: str) -> str:
    email = f"map.{random_string(8).lower()}@zatgo.test"
    frappe.get_doc(
        {"doctype": "User", "email": email, "first_name": "Map", "send_welcome_email": 0, "roles": [{"role": r} for r in roles]}
    ).insert(ignore_permissions=True)
    return email


def _stored(doctype: str, field: str):
    rows = frappe.db.sql("select value from `tabSingles` where doctype = %s and field = %s", (doctype, field))
    return rows[0][0] if rows else None


def _rows(app_data: dict) -> dict:
    return {
        (dt["doctype"], r["fieldname"]): r
        for dt in app_data["settings"]
        for tab in dt["tabs"]
        for sec in tab["sections"]
        for r in sec["rows"]
    }


class TestSettingsMap(IntegrationTestCase):
    FIELDS = [(VANSALEX, "allow_bank_payment"), (VANSALEX, "max_discount_percent"), (VANSALEX, "default_payment_type"), (POS, "print_copies"), (POS, "allow_discounts")]

    def setUp(self) -> None:
        frappe.set_user("Administrator")
        self._saved = {k: _stored(*k) for k in self.FIELDS}

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        for (dt, field), value in self._saved.items():
            if value is None:
                frappe.db.delete("Singles", {"doctype": dt, "field": field})
            else:
                frappe.db.set_single_value(dt, field, value)
            frappe.clear_document_cache(dt, dt)
        frappe.db.commit()

    # -- reading -----------------------------------------------------------------------------------------------

    def test_every_app_with_settings_is_described(self) -> None:
        data = settings_map.describe()
        by_key = {a["key"]: a for a in data["apps"]}
        for app in app_catalog.catalog():
            self.assertIn(app["key"], by_key)
            card = by_key[app["key"]]
            self.assertEqual(card["palette"]["accent"], app["color"].upper())
            self.assertEqual(card["scopes"][0], "site")
            self.assertEqual(card["has_switch"], bool(app["switch_field"]))
        self.assertGreater(by_key["vansalex"]["counts"]["fields"], 10)
        self.assertGreater(by_key["chat_ai"]["counts"]["fields"], 50)
        self.assertEqual(settings_map.describe("zatgo_pos")["apps"][0]["key"], "zatgo_pos")

    def test_rows_have_a_control_scope_and_status_and_no_secrets(self) -> None:
        for card in settings_map.describe()["apps"]:
            for (dt, name), row in _rows(card).items():
                self.assertIn(row["status"], ("enforced", "read", "info", "unwired"), f"{dt}.{name}")
                self.assertIn(row["scope"], app_catalog.SCOPES, f"{dt}.{name}")
                self.assertTrue(row["control"], f"{dt}.{name}")
                if row["control"] == "password":
                    self.assertIsNone(row["value"], f"{dt}.{name} must never carry its secret")
                    self.assertFalse(row["writable"])
                if row["control"] in ("table", "attach"):
                    self.assertFalse(row["writable"])
                self.assertNotIn(name, app_catalog.switch_fields().values(), "app switches are the card switches")

    def test_a_doctype_listed_by_two_apps_is_shown_once(self) -> None:
        seen = [dt["doctype"] for card in settings_map.describe()["apps"] for dt in card["settings"]]
        core = next(c for c in settings_map.describe()["apps"] if c["key"] == "core_settings")
        industries = next(c for c in settings_map.describe()["apps"] if c["key"] == "industries")
        self.assertEqual(seen.count("ZG System Settings"), 2)
        self.assertIn(("ZG System Settings", "enabled_industries"), _rows(industries))
        self.assertNotIn(("ZG System Settings", "enabled_industries"), _rows(core))
        self.assertNotIn(("ZG System Settings", "autofill_source_warehouse"), _rows(industries))

    def test_stored_flag_reads_the_singles_table(self) -> None:
        frappe.db.delete("Singles", {"doctype": POS, "field": "allow_discounts"})
        frappe.clear_document_cache(POS, POS)
        row = _rows(settings_map.describe("zatgo_pos")["apps"][0])[(POS, "allow_discounts")]
        self.assertFalse(row["stored"])
        self.assertEqual(row["control"], "switch")
        settings_map.save_field(POS, "allow_discounts", 1)
        row = _rows(settings_map.describe("zatgo_pos")["apps"][0])[(POS, "allow_discounts")]
        self.assertTrue(row["stored"])
        self.assertEqual(row["value"], 1)

    def test_controls_for_known_fields(self) -> None:
        rows = _rows(settings_map.describe("vansalex")["apps"][0])
        self.assertEqual(rows[(VANSALEX, "default_payment_type")]["control"], "choice")
        self.assertEqual(rows[(VANSALEX, "default_payment_type")]["options"], ["Cash", "Bank", "Credit"])
        self.assertEqual(rows[(VANSALEX, "allow_credit_sales")]["control"], "switch")
        self.assertEqual(rows[(VANSALEX, "max_discount_percent")]["control"], "number")
        self.assertEqual(rows[(VANSALEX, "default_cash_account")]["control"], "link")
        self.assertEqual(rows[(VANSALEX, "access")]["control"], "table")
        self.assertFalse(rows[(VANSALEX, "config_version")]["writable"])

    # -- writing -----------------------------------------------------------------------------------------------

    def test_save_persists_and_reports_a_change(self) -> None:
        before = int(frappe.db.get_single_value(VANSALEX, "allow_bank_payment") or 0)
        result = settings_map.save_field(VANSALEX, "allow_bank_payment", 0 if before else 1)
        self.assertTrue(result["changed"])
        self.assertTrue(result["stored"])
        self.assertEqual(int(frappe.db.get_single_value(VANSALEX, "allow_bank_payment") or 0), 0 if before else 1)
        again = settings_map.save_field(VANSALEX, "allow_bank_payment", 0 if before else 1)
        self.assertFalse(again["changed"])

    def test_choice_and_number_are_saved_through_the_controller(self) -> None:
        settings_map.save_field(VANSALEX, "max_discount_percent", "12.5")
        self.assertEqual(float(frappe.db.get_single_value(VANSALEX, "max_discount_percent")), 12.5)
        settings_map.save_field(VANSALEX, "default_payment_type", "Cash")
        self.assertEqual(frappe.db.get_single_value(VANSALEX, "default_payment_type"), "Cash")

    def test_controller_validation_refuses_bad_values_and_changes_nothing(self) -> None:
        before = frappe.db.get_single_value(VANSALEX, "max_discount_percent")
        with self.assertRaises(settings_map.SettingsMapError) as ctx:
            settings_map.save_field(VANSALEX, "max_discount_percent", 150)
        self.assertEqual(ctx.exception.code, "invalid_value")
        self.assertIn("between 0 and 100", ctx.exception.message)
        self.assertEqual(frappe.db.get_single_value(VANSALEX, "max_discount_percent"), before)
        with self.assertRaises(settings_map.SettingsMapError) as ctx:
            settings_map.save_field(VANSALEX, "default_payment_type", "Barter")
        self.assertEqual(ctx.exception.code, "invalid_value")
        with self.assertRaises(settings_map.SettingsMapError):
            settings_map.save_field(POS, "print_copies", 0)
        before = frappe.db.get_single_value(VANSALEX, "max_discount_percent")
        for bad in ("abc", "inf", "nan", "1e999"):
            for dt, field in ((VANSALEX, "max_discount_percent"), (POS, "print_copies")):
                with self.assertRaises(settings_map.SettingsMapError, msg=f"{field}={bad}") as ctx:
                    settings_map.save_field(dt, field, bad)
                self.assertEqual(ctx.exception.code, "invalid_value")
        with self.assertRaises(settings_map.SettingsMapError):
            settings_map.save_field(POS, "print_copies", "2.7")
        self.assertEqual(frappe.db.get_single_value(VANSALEX, "max_discount_percent"), before)

    def test_forbidden_fields_are_refused(self) -> None:
        password = next(f.fieldname for f in frappe.get_meta("ZG Integration Settings").fields if f.fieldtype == "Password")
        cases = {
            ("ZG Integration Settings", password): "locked_field",
            (VANSALEX, "access"): "locked_field",
            (VANSALEX, "config_version"): "locked_field",
            ("ZG System Settings", "brand_name"): "locked_field",
            ("ZG System Settings", "enable_vansalex"): "locked_field",
            ("ZG System Settings", "enable_chat_ai"): "locked_field",
            (VANSALEX, "no_such_field"): "unknown_field",
            ("User", "first_name"): "not_settings",
            ("ToDo", "description"): "not_settings",
        }
        for (dt, field), code in cases.items():
            with self.assertRaises(settings_map.SettingsMapError, msg=f"{dt}.{field}") as ctx:
                settings_map.save_field(dt, field, "x")
            self.assertEqual(ctx.exception.code, code, f"{dt}.{field}")

    def test_an_ordinary_enable_setting_can_be_changed(self) -> None:
        field = "enable_ifrs_reports"
        was = frappe.db.get_single_value("ZG System Settings", field)
        self.addCleanup(lambda: frappe.db.set_single_value("ZG System Settings", field, was or 0))
        self.assertTrue(settings_map.save_field("ZG System Settings", field, 0 if was else 1)["changed"])

    def test_settings_the_roles_cannot_open_are_reported(self) -> None:
        card = settings_map.describe("vansalex")["apps"][0]
        self.assertEqual(card["restricted"], [])
        user = _make_user("System Manager")
        frappe.set_user(user)
        for app in settings_map.describe()["apps"]:
            for label in app["restricted"]:
                self.assertFalse(any(d["label"] == label for d in app["settings"]), label)

    def test_a_user_without_write_permission_is_refused(self) -> None:
        user = _make_user("Desk User")
        frappe.set_user(user)
        with self.assertRaises(settings_map.SettingsMapError) as ctx:
            settings_map.save_field(VANSALEX, "allow_bank_payment", 1)
        self.assertEqual(ctx.exception.code, "forbidden")
        self.assertEqual(settings_map.describe()["apps"], [])  # roles gate the cards, DocType read gates the rows

    def test_a_save_writes_an_audit_row_with_old_and_new_value(self) -> None:
        frappe.db.set_single_value(VANSALEX, "max_discount_percent", 40)
        frappe.clear_document_cache(VANSALEX, VANSALEX)
        settings_map.save_field(VANSALEX, "max_discount_percent", 55)
        rows = frappe.get_all(
            "ZG Audit Log",
            filters={"doctype_name": VANSALEX, "fieldname": "max_discount_percent", "changed_by": "Administrator"},
            fields=["old_value", "new_value"],
            order_by="creation desc",
            limit=1,
        )
        self.assertTrue(rows, "AuditableMixin must record the change")
        self.assertEqual(float(rows[0].new_value), 55.0)
        self.assertEqual(float(rows[0].old_value), 40.0)

    def test_theme_language_mybis_and_pos_settings_are_audited(self) -> None:
        from zatgo_core.mixins.auditable import AuditableMixin
        from zatgo_core.zatgo_core.doctype.vansalex_settings.vansalex_settings import VanSaleXSettings
        from zatgo_core.zatgo_core.doctype.zg_language_settings.zg_language_settings import ZGLanguageSettings
        from zatgo_core.zatgo_core.doctype.zg_pos_settings.zg_pos_settings import ZGPOSSettings
        from zatgo_core.zatgo_core.doctype.zg_theme_settings.zg_theme_settings import ZGThemeSettings

        for cls in (VanSaleXSettings, ZGLanguageSettings, ZGPOSSettings, ZGThemeSettings):
            self.assertTrue(issubclass(cls, AuditableMixin), cls.__name__)

    # -- the API -----------------------------------------------------------------------------------------------

    def test_api_envelopes(self) -> None:
        data = api.get_map("vansalex")
        self.assertTrue(data["success"])
        self.assertTrue(data["data"]["css"].startswith("/assets/zatgo_core/css/zg_settings_map.css?v="))
        bad = api.save_field(VANSALEX, "access", "[]")
        self.assertFalse(bad["success"])
        self.assertEqual(bad["error"]["code"], "locked_field")
        good = api.save_field(POS, "allow_discounts", 1)
        self.assertTrue(good["success"])
