"""Industry registry integrity (no database)."""

from __future__ import annotations

import unittest

from zatgo_core.industries import registry


class TestIndustryRegistry(unittest.TestCase):
    def test_registry_is_consistent(self) -> None:
        self.assertEqual(registry.validate_registry(), [])

    def test_all_seventeen_industries_registered(self) -> None:
        self.assertEqual(len(registry.INDUSTRIES), 17)
        for key in ("jewellery", "textile", "supermarket", "salon", "gym", "electrical", "restaurant", "pharmacy"):
            self.assertIn(key, registry.INDUSTRIES)

    def test_only_pilots_are_implemented(self) -> None:
        self.assertEqual(
            {k for k, i in registry.INDUSTRIES.items() if i.implemented}, {"jewellery", "gym", "restaurant"}
        )

    def test_doctype_owner_is_unique_and_mapped(self) -> None:
        owner = registry.doctype_owner()
        self.assertEqual(owner["ZG Gym Plan"], "gym")
        self.assertEqual(owner["ZG Table"], "restaurant")
        self.assertEqual(owner["ZG Metal Rate"], "jewellery")
        self.assertNotIn("Sales Invoice", owner)  # core is never industry-gated

    def test_broken_registry_is_reported(self) -> None:
        bad = registry.Industry(key="x", label="X", description="", requires=("nope",), requires_industries=("y",))
        saved = dict(registry.INDUSTRIES)
        try:
            registry.INDUSTRIES["x"] = bad
            problems = registry.validate_registry()
        finally:
            registry.INDUSTRIES.clear()
            registry.INDUSTRIES.update(saved)
        self.assertTrue(any("unknown capability" in p for p in problems))
        self.assertTrue(any("unknown industry dependency" in p for p in problems))
