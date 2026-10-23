"""Naming standard (no database): DocTypes shipped by zatgo_core are `ZG <Name>`.

The standard is in docs/naming.md. The 25 DocTypes below predate it (the modules merged in 2026-10-08 came
with their own names, and VanSaleX Settings is older than the prefix); they keep their names -- renaming a
DocType moves data, hooks, permissions and clients -- but nothing new may join them. If one is ever
renamed, remove it from LEGACY_NON_ZG: this test fails on an entry that no longer exists."""

from __future__ import annotations

import json
import os
import unittest

PACKAGE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

LEGACY_NON_ZG = frozenset(
    {
        # VanSaleX (core module)
        "VanSaleX Settings",
        "VanSaleX Access",
        # Chat AI module
        "Chat AI Settings",
        "AI Artifact",
        "AI Attachment",
        "AI Chat Memory",
        "AI Chat Message",
        "AI Chat Session",
        "AI Conversation Summary",
        "AI Integration Connector",
        "AI MCP Server",
        "AI Plugin Registry",
        "AI Provider Health Log",
        "AI REST Tool",
        "AI Scheduled Task",
        "AI Search Index",
        "AI Tool Log",
        "AI Usage Daily",
        # Tracker module
        "Tracker Settings",
        "Tracker Activity Session",
        # ZatGo Space module
        "Space Settings",
        "Space Plan",
        "Space Order",
        "Space Order App",
        "Space Job Log",
    }
)

# Standard ERPNext DocTypes that hooks.py attaches permission hooks to.
ERPNEXT_HOOKED = frozenset({"Project", "Task", "Issue", "Timesheet"})


def shipped_doctypes() -> dict[str, str]:
    """DocType name -> path of its JSON, for every DocType the package ships."""
    out: dict[str, str] = {}
    for root, dirs, files in os.walk(PACKAGE):
        dirs[:] = [d for d in dirs if d not in ("public", "node_modules", "__pycache__", ".claude")]
        if os.path.basename(os.path.dirname(root)) != "doctype":
            continue
        name = os.path.basename(root)
        if f"{name}.json" in files:
            path = os.path.join(root, f"{name}.json")
            with open(path, encoding="utf-8") as f:
                out[json.load(f)["name"]] = path
    return out


class TestNamingStandard(unittest.TestCase):
    def test_new_doctypes_are_zg_prefixed(self) -> None:
        offenders = sorted(n for n in shipped_doctypes() if not n.startswith("ZG ") and n not in LEGACY_NON_ZG)
        self.assertEqual(offenders, [], "New DocTypes are named 'ZG <Name>' (docs/naming.md)")

    def test_legacy_list_has_no_stale_entries(self) -> None:
        shipped = set(shipped_doctypes())
        self.assertEqual(sorted(LEGACY_NON_ZG - shipped), [], "Renamed or removed: delete it from LEGACY_NON_ZG")

    def test_no_doctype_carries_zatgo_as_a_suffix_or_infix(self) -> None:
        # The retired convention was '<Name> ZatGo'.
        self.assertEqual(sorted(n for n in shipped_doctypes() if "ZatGo" in n), [])

    def test_hooked_doctypes_exist(self) -> None:
        """A permission hook keyed on a DocType nobody ships (a typo, or a half-done rename) silently stops
        applying -- for Chat AI that means its per-user privacy scoping."""
        from zatgo_core import hooks

        shipped = set(shipped_doctypes())
        for table in ("permission_query_conditions", "has_permission"):
            for key in getattr(hooks, table):
                if key == "*":
                    continue
                self.assertTrue(key in shipped or key in ERPNEXT_HOOKED, f"hooks.{table}[{key!r}] names no known DocType")


if __name__ == "__main__":
    unittest.main()
