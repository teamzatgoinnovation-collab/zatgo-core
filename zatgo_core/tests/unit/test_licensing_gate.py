"""Licence gate decisions (no database: documents are plain dicts)."""

from __future__ import annotations

import unittest

import frappe

from zatgo_core.licensing import edition_config
from zatgo_core.licensing.entitlement import Entitlement
from zatgo_core.licensing.gate import ENFORCED, decide


def _sales() -> Entitlement:
    return Entitlement.from_features(edition_config.get_preset("sales")["features"], source="test")


def _doc(doctype: str, **fields) -> frappe._dict:
    return frappe._dict(doctype=doctype, **fields)


class TestEntitlement(unittest.TestCase):
    def test_foundation_is_always_in_and_unknown_ids_drop(self) -> None:
        ent = Entitlement.from_features({"sales.invoice": [], "sales.gone": []})
        self.assertIn("foundation.setup", ent.features)
        self.assertIn("sales.invoice", ent.features)
        self.assertNotIn("sales.gone", ent.features)

    def test_bridges_are_collected(self) -> None:
        ent = Entitlement.from_features(edition_config.get_preset("distribution")["features"])
        self.assertIn("vansalex", ent.app_keys)
        self.assertIn("inventory.transfer", ent.vansalex_keys)
        self.assertNotIn("gym", ent.industries)

    def test_digest_is_stable(self) -> None:
        self.assertEqual(_sales().digest, _sales().digest)
        self.assertNotEqual(_sales().digest, Entitlement.from_features({}).digest)


class TestDecide(unittest.TestCase):
    def test_no_entitlement_allows_everything(self) -> None:
        self.assertTrue(decide("Stock Entry", "create", _doc("Stock Entry", purpose="Material Receipt"), None)["allowed"])

    def test_licensed_and_unlicensed_writes(self) -> None:
        ent = _sales()
        self.assertTrue(decide("Sales Invoice", "submit", _doc("Sales Invoice", is_return=0), ent)["allowed"])
        verdict = decide("Stock Entry", "create", _doc("Stock Entry", purpose="Material Receipt"), ent)
        self.assertFalse(verdict["allowed"])
        self.assertEqual(verdict["features"], ["inventory.stock_receipt"])
        self.assertFalse(decide("Purchase Invoice", "create", _doc("Purchase Invoice", is_return=0), ent)["allowed"])

    def test_read_print_and_cancel_are_never_refused(self) -> None:
        ent = _sales()
        doc = _doc("Stock Entry", purpose="Material Receipt")
        for ptype in ("read", "print", "email", "export", "report", "share", "cancel"):
            self.assertNotIn(ptype, ENFORCED)
            self.assertTrue(decide("Stock Entry", ptype, doc, ent)["allowed"], ptype)

    def test_returns_follow_their_own_feature(self) -> None:
        only_invoice = Entitlement.from_features({"sales.invoice": []})
        self.assertTrue(decide("Sales Invoice", "create", _doc("Sales Invoice", is_return=0), only_invoice)["allowed"])
        self.assertFalse(decide("Sales Invoice", "create", _doc("Sales Invoice", is_return=1), only_invoice)["allowed"])
        self.assertTrue(decide("Sales Invoice", "create", _doc("Sales Invoice", is_return=1), _sales())["allowed"])

    def test_narrowed_actions(self) -> None:
        ent = Entitlement.from_features({"sales.invoice": ["read", "create", "write"]})
        doc = _doc("Sales Invoice", is_return=0)
        self.assertTrue(decide("Sales Invoice", "create", doc, ent)["allowed"])
        self.assertFalse(decide("Sales Invoice", "submit", doc, ent)["allowed"])

    def test_undescribed_documents_and_doctypes_are_untouched(self) -> None:
        ent = _sales()
        self.assertTrue(decide("Stock Entry", "create", _doc("Stock Entry", purpose="Repack"), ent)["allowed"])
        self.assertTrue(decide("ToDo", "create", _doc("ToDo"), ent)["allowed"])
        self.assertTrue(decide("GL Entry", "create", _doc("GL Entry"), ent)["allowed"])

    def test_manufacture_purposes_match_a_tuple(self) -> None:
        ent = Entitlement.from_features({"production.work_order": [], "production.bom": []})
        for purpose in ("Manufacture", "Material Transfer for Manufacture"):
            self.assertTrue(decide("Stock Entry", "submit", _doc("Stock Entry", purpose=purpose), ent)["allowed"])
        self.assertFalse(decide("Stock Entry", "submit", _doc("Stock Entry", purpose="Material Issue"), ent)["allowed"])

    def test_foundation_reads_masters_but_does_not_write_them(self) -> None:
        ent = Entitlement.from_features({})
        self.assertTrue(decide("Warehouse", "read", _doc("Warehouse"), ent)["allowed"])
        self.assertFalse(decide("Warehouse", "create", _doc("Warehouse"), ent)["allowed"])
        self.assertTrue(decide("Company", "write", _doc("Company"), ent)["allowed"])


if __name__ == "__main__":
    unittest.main()
