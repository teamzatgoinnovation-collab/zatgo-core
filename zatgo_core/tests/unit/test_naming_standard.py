"""Naming standard (no database): DocTypes shipped by zatgo_core are plain `<Name>` (no prefix).

The standard is in docs/naming.md. The 25 DocTypes below predate it (the modules merged in 2026-10-08 came
with their own names, and VanSaleX Settings is older than the prefix); they keep their names -- renaming a
DocType moves data, hooks, permissions and clients -- but nothing new may join them. If one is ever
renamed, remove it from LEGACY_NON_ZG: this test fails on an entry that no longer exists."""

from __future__ import annotations

import json
import os
import unittest

PACKAGE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ZATGO_PREFIXED = {
    "ZatGo System Settings", "ZatGo Notification Settings", "ZatGo Security Settings", "ZatGo POS Settings",
    "ZatGo Vehicle", "ZatGo Delivery Stop", "ZatGo Mode of Payment Account",
}

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
    def test_doctypes_have_no_zg_prefix(self) -> None:
        # ZG <Name> was renamed (patch v0_6_0/rename_zg_to_zatgo): the prefix is gone.
        self.assertEqual(sorted(n for n in shipped_doctypes() if n.startswith("ZG ")), [])

    def test_only_colliding_names_keep_a_zatgo_prefix(self) -> None:
        # The plain name already exists in ERPNext / Frappe, so these (and only these) are `ZatGo <Name>`.
        prefixed = sorted(n for n in shipped_doctypes() if n.startswith("ZatGo "))
        self.assertEqual(prefixed, sorted(ZATGO_PREFIXED))

    def test_legacy_list_has_no_stale_entries(self) -> None:
        shipped = set(shipped_doctypes())
        self.assertEqual(sorted(LEGACY_NON_ZG - shipped), [], "Renamed or removed: delete it from LEGACY_NON_ZG")
