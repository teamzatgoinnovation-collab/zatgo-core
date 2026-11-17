"""Licensing registry integrity (no database). What exists on a site: tests/integration/test_licensing_registry.py."""

from __future__ import annotations

import ast
import os
import unittest

from zatgo_core.industries import registry as industries
from zatgo_core.licensing import registry
from zatgo_core.services import app_catalog

PACKAGE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _vansalex_catalog_keys() -> set[str]:
    """services/vansalex_access.CATALOG keys, read from the source (that module imports frappe)."""
    tree = ast.parse(open(os.path.join(PACKAGE, "services", "vansalex_access.py"), encoding="utf-8").read())
    for node in tree.body:
        target = getattr(node, "target", None) or (node.targets[0] if isinstance(node, ast.Assign) else None)
        if getattr(target, "id", None) == "CATALOG":
            return {k.value for k in node.value.keys}
    raise AssertionError("CATALOG not found in services/vansalex_access.py")


class TestLicensingRegistry(unittest.TestCase):
    def test_registry_is_valid(self) -> None:
        self.assertEqual(registry.validate(), [])

    def test_ids_are_locked_and_never_vanish(self) -> None:
        ids = {f.id for f in registry.features()}
        locked = registry.locked_ids()
        self.assertEqual(len(locked), len(set(locked)), "ids.lock has a duplicate line")
        self.assertEqual(ids, set(locked), "every shipped id stays in the code (retire it) and in ids.lock")

    def test_lock_check_catches_a_removed_id(self) -> None:
        problems = registry.validate(feats=[f for f in registry.features() if f.id != "sales.return"])
        self.assertTrue(any("no longer in the catalog" in p and "sales.return" in p for p in problems), problems)

    def test_lock_check_catches_an_unlocked_id(self) -> None:
        problems = registry.validate(locked=[i for i in registry.locked_ids() if i != "sales.order"])
        self.assertTrue(any("not in catalog/ids.lock" in p and "sales.order" in p for p in problems), problems)

    def test_no_feature_maps_a_never_gate_doctype(self) -> None:
        mapped = set(registry.doctype_index())
        self.assertEqual(mapped & registry.NEVER_GATE, set())
        for ledger in ("GL Entry", "Stock Ledger Entry", "Payment Ledger Entry", "Bin", "Repost Item Valuation"):
            self.assertIn(ledger, registry.NEVER_GATE)

    def test_validate_rejects_bad_features(self) -> None:
        bad = registry.feature(
            "sales.bogus", "Bogus",
            doctypes=[registry.dt("GL Entry", ("read",)), registry.dt("Sales Invoice", ("launch",))],
            platforms=["watch"], api_prefixes=["zatgo_core.api.v1.x"], requires={"nope.nothing": []},
        )
        cyclic_a = registry.feature("sales.cycle_a", "A", reports=["x"], requires={"sales.cycle_b": []})
        cyclic_b = registry.feature("sales.cycle_b", "B", reports=["x"], requires={"sales.cycle_a": []})
        problems = registry.validate(feats=[*registry.features(), bad, cyclic_a, cyclic_b])
        joined = "\n".join(problems)
        for needle in ("GL Entry is in NEVER_GATE", "unknown actions ['launch']", "unknown platforms ['watch']",
                       "must end with '.'", "requires unknown feature 'nope.nothing'", "dependency cycle",
                       "sales.bogus"):
            self.assertIn(needle, joined)

    def test_bridges_point_at_real_registries(self) -> None:
        apps = {a["key"] for a in app_catalog.catalog()}
        vx = _vansalex_catalog_keys()
        for f in registry.features():
            if f.app_key:
                self.assertIn(f.app_key, apps, f.id)
            if f.industry:
                self.assertIn(f.industry, industries.INDUSTRIES, f.id)
                self.assertTrue(industries.INDUSTRIES[f.industry].implemented, f"{f.id}: not implemented")
            for key in f.vansalex_keys:
                self.assertIn(key, vx, f.id)

    def test_every_switchable_app_and_vansalex_key_is_covered_once(self) -> None:
        licensed_apps = [f.app_key for f in registry.features() if f.app_key]
        self.assertEqual(len(licensed_apps), len(set(licensed_apps)))
        switchable = {a["key"] for a in app_catalog.catalog() if a["switch_field"] and a["group"] != "industries"}
        self.assertEqual(switchable - set(licensed_apps), set())
        covered = [k for f in registry.features() for k in f.vansalex_keys]
        self.assertEqual(len(covered), len(set(covered)), "a VanSaleX key belongs to one feature")
        self.assertEqual(_vansalex_catalog_keys() - set(covered), set())
        implemented = {k for k, i in industries.INDUSTRIES.items() if i.implemented}
        self.assertEqual(implemented - {f.industry for f in registry.features() if f.industry}, set())

    def test_returns_are_their_own_feature(self) -> None:
        grants = dict(registry.doctype_index())["Sales Invoice"]
        by_feature = {fid: dict(g.match) for fid, g in grants}
        self.assertEqual(by_feature["sales.invoice"], {"is_return": 0})
        self.assertEqual(by_feature["sales.return"], {"is_return": 1})

    def test_resolution_reports_a_paid_module_instead_of_adding_it(self) -> None:
        out = registry.resolve_requirements(["pos.zatgo_pos"])
        self.assertEqual(out["selected"], ["pos.zatgo_pos"])  # nothing added
        missing = {m["feature"] for m in out["missing"]}
        self.assertEqual(missing, {"pos.profile", "pos.session", "sales.invoice", "accounting.payment_entry"})
        self.assertEqual(len(out["missing"]), 4, "each missing feature reported once per feature needing it")
        self.assertEqual({m["module"] for m in out["missing"] if m["feature"] == "sales.invoice"}, {"sales"})

    def test_resolution_is_transitive_and_counts_foundation(self) -> None:
        out = registry.resolve_requirements(["vansalex.stock_transfer"])
        missing = {m["feature"] for m in out["missing"]}
        self.assertIn("vansalex.inventory", missing)
        self.assertIn("vansalex.app", missing)  # needed by vansalex.inventory, itself missing: the chain shows
        self.assertIn("inventory.stock_reports", missing)
        self.assertIn("inventory.stock_transfer", missing)
        full = registry.resolve_requirements(
            ["vansalex.stock_transfer", "vansalex.inventory", "vansalex.app", "inventory.stock_transfer",
             "inventory.stock_reports"]
        )
        self.assertEqual(full["missing"], [])
        self.assertIn("foundation.masters_read", full["foundation"])

    def test_unknown_and_retired_ids_are_reported(self) -> None:
        out = registry.resolve_requirements(["sales.nothing"])
        self.assertEqual(out["unknown"], ["sales.nothing"])

    def test_foundation_never_grants_writes_on_business_masters(self) -> None:
        reads = registry.get_feature("foundation.masters_read")
        for grant in reads.doctypes:
            self.assertEqual(set(grant.actions) - set(registry.READ_ONLY), set(), grant.doctype)

    def test_hash_is_stable(self) -> None:
        self.assertEqual(registry.registry_hash(), registry.registry_hash())
        self.assertEqual(len(registry.registry_hash()), 16)


if __name__ == "__main__":
    unittest.main()
