"""Edition configs, presets and the dependency inspector (no database)."""

from __future__ import annotations

import unittest

from zatgo_core.licensing import edition_config as ec
from zatgo_core.licensing import inspector, registry


def _cfg(**kw):
    base = dict(edition_id="test_ed", edition_name="Test", features={"sales.invoice": []})
    base.update(kw)
    return ec.build_config(**base)


class TestPresets(unittest.TestCase):
    def test_ten_presets_ship(self) -> None:
        ids = [p["edition_id"] for p in ec.presets()]
        self.assertEqual(sorted(ids), sorted([
            "sales", "accounting", "inventory", "pos", "sales_inventory", "accounting_inventory", "retail",
            "distribution", "enterprise", "custom",
        ]))

    def test_every_preset_is_valid_and_complete(self) -> None:
        for p in ec.presets():
            with self.subTest(preset=p["edition_id"]):
                self.assertEqual(ec.validate_config(p), [])
                report = inspector.inspect(p["features"], platforms=p["platforms"])
                self.assertEqual(report["missing"], [], "a preset must include what its features need")
                self.assertEqual(report["platform_mismatch"], [])

    def test_enterprise_has_every_live_feature_and_custom_is_an_empty_draft(self) -> None:
        live = {f.id for f in registry.features() if not f.retired and not f.foundation}
        self.assertEqual(set(ec.get_preset("enterprise")["features"]), live)
        custom = ec.get_preset("custom")
        self.assertEqual(custom["features"], {})
        self.assertEqual(custom["status"], "Draft")

    def test_sales_includes_payment_and_tax_but_not_accounting_ledgers(self) -> None:
        sales = ec.get_preset("sales")["features"]
        self.assertIn("accounting.payment_entry", sales)
        self.assertIn("tax.templates", sales)
        self.assertNotIn("accounting.journal_entry", sales)


class TestValidation(unittest.TestCase):
    def test_a_sound_config_has_no_problem(self) -> None:
        self.assertEqual(ec.validate_config(_cfg()), [])

    def test_a_licence_file_is_refused(self) -> None:
        problems = ec.validate_config({**_cfg(), "type": ec.LICENCE_FILE_TYPE})
        self.assertEqual(len(problems), 1)
        self.assertIn("licence file", problems[0])

    def test_wrong_schema_product_and_id(self) -> None:
        joined = "\n".join(ec.validate_config({**_cfg(), "schema_version": 99, "product_id": "other",
                                               "edition_id": "Bad Id"}))
        self.assertIn("unsupported schema_version", joined)
        self.assertIn("product_id", joined)
        self.assertIn("edition_id", joined)

    def test_feature_rules(self) -> None:
        joined = "\n".join(ec.validate_config(_cfg(features={
            "foundation.setup": [], "sales.nothing": [], "sales.analytics": ["read"],
            "sales.invoice": ["read", "import"],
        })))
        self.assertIn("foundation.setup: foundation features", joined)
        self.assertIn("sales.nothing: unknown feature", joined)
        self.assertIn("sales.analytics: has no DocTypes", joined)
        self.assertIn("sales.invoice: does not grant ['import']", joined)

    def test_limits_and_platforms(self) -> None:
        cfg = _cfg(platforms={"desk": 0}, licence_defaults={"max_users": -1, "licence_type": "Forever"})
        joined = "\n".join(ec.validate_config(cfg))
        self.assertIn("at least one platform", joined)
        self.assertIn("max_users must be a whole number", joined)
        self.assertIn("licence_type must be one of", joined)

    def test_grant_hash_ignores_name_status_and_description(self) -> None:
        a = _cfg()
        b = _cfg(edition_name="Renamed", status="Active", description="x")
        self.assertEqual(ec.grant_hash(a), ec.grant_hash(b))
        self.assertNotEqual(ec.grant_hash(a), ec.grant_hash(_cfg(features={"sales.invoice": ["read"]})))
        self.assertNotEqual(ec.grant_hash(a), ec.grant_hash(_cfg(licence_defaults={"max_users": 9})))

    def test_actions_are_normalised(self) -> None:
        self.assertEqual(ec.normalise_features({"sales.invoice": ["print", "read", "read"]}),
                         {"sales.invoice": ["read", "print"]})
        self.assertEqual(ec.normalise_features(["sales.order"]), {"sales.order": []})


class TestCompareAndExport(unittest.TestCase):
    def test_compare(self) -> None:
        a = _cfg(features={"sales.invoice": [], "sales.order": []})
        b = _cfg(edition_id="other", features={"sales.invoice": ["read"], "sales.quotation": []},
                 platforms={"desk": 1, "mobile": 1})
        diff = ec.compare(a, b)
        self.assertEqual(diff["only_a"], ["sales.order"])
        self.assertEqual(diff["only_b"], ["sales.quotation"])
        self.assertEqual(diff["actions_differ"], [{"feature": "sales.invoice", "a": [], "b": ["read"]}])
        self.assertEqual(diff["platforms"], {"mobile": [0, 1]})

    def test_export_carries_resolved_mappings(self) -> None:
        payload = ec.export_payload(_cfg(features={"sales.return": [], "sales.invoice": ["read", "print"]}))
        self.assertEqual(payload["type"], ec.FILE_TYPE)
        resolved = payload["resolved"]
        self.assertEqual(resolved["doctype_mappings"]["Sales Invoice"], [
            a for a in registry.ACTIONS if a in set(registry.TRANSACTION)
        ])  # sales.return grants it all for returns; the union is reported
        self.assertEqual(resolved["dependencies"], [])
        self.assertIn("Sales Register", resolved["report_mappings"])


class TestInspector(unittest.TestCase):
    def test_missing_dependency_is_reported_not_added(self) -> None:
        r = inspector.inspect({"pos.zatgo_pos": []})
        self.assertFalse(r["ok"])
        self.assertEqual([f["id"] for f in r["features"]], ["pos.zatgo_pos"])
        self.assertTrue(any(w.startswith("Missing sales.invoice (sales)") for w in r["warnings"]))

    def test_posting_effects_show_the_ledgers_and_zatca(self) -> None:
        r = inspector.inspect({"sales.invoice": [], "tax.zatca": []})
        si = next(p for p in r["posting"] if p["doctype"] == "Sales Invoice")
        self.assertIn("GL Entry", si["ledgers"])
        self.assertIn(inspector.ZATCA_EFFECT, si["ledgers"])
        self.assertTrue(si["jobs"])

    def test_narrowed_actions_shrink_the_grant(self) -> None:
        r = inspector.inspect({"sales.invoice": ["read", "print"]})
        si = next(d for d in r["doctypes"] if d["doctype"] == "Sales Invoice")
        self.assertEqual(si["actions"], ["read", "print"])
        self.assertFalse(any(p["doctype"] == "Sales Invoice" for p in r["posting"]), "no submit, no posting")

    def test_foundation_is_always_in(self) -> None:
        r = inspector.inspect({})
        self.assertTrue(r["ok"])
        self.assertIn("Company", [d["doctype"] for d in r["doctypes"]])
        self.assertIn("foundation.setup", r["foundation"])

    def test_unavailable_and_platform_warnings(self) -> None:
        r = inspector.inspect({"hr_payroll.employee": [], "vansalex.app": []}, platforms={"desktop": 1},
                              installed={"frappe", "erpnext", "zatgo_core"})
        self.assertEqual(r["unavailable"], [{"feature": "hr_payroll.employee", "source_app": "hrms"}])
        self.assertEqual([p["feature"] for p in r["platform_mismatch"]], ["hr_payroll.employee", "vansalex.app"])

    def test_settings_come_from_the_single_test(self) -> None:
        r = inspector.inspect({"sales.settings": []}, is_single=lambda dt: dt.endswith("Settings"))
        self.assertIn("Selling Settings", r["settings"])


if __name__ == "__main__":
    unittest.main()
