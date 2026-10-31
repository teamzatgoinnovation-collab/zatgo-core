"""Settings Map without a database: manifest keys, colour contrast, control map and the audit notes (every field and path
named in services/settings_notes.py must exist, so a note cannot rot)."""

from __future__ import annotations

import json
import os
import re
import unittest

import frappe

from zatgo_core.services import app_catalog, settings_map, settings_notes, settings_palette

PACKAGE = app_catalog.PACKAGE_DIR


def _doctype_json(name: str) -> dict | None:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    for root, _dirs, files in os.walk(PACKAGE):
        if os.path.basename(root) == slug and f"{slug}.json" in files and "doctype" in root:
            with open(os.path.join(root, f"{slug}.json"), encoding="utf-8") as f:
                return json.load(f)
    return None


class TestManifestKeys(unittest.TestCase):
    def setUp(self) -> None:
        self.addCleanup(app_catalog.catalog.cache_clear)

    def test_every_app_has_a_valid_accent(self) -> None:
        for app in app_catalog.catalog():
            self.assertTrue(settings_palette.is_hex(app["color"]), app["key"])

    def test_scopes_and_clients_are_valid(self) -> None:
        for app in app_catalog.catalog():
            self.assertTrue(set(app["scoped"]) <= set(app_catalog.SCOPES) - {"site"}, app["key"])
            self.assertTrue(set(app["device"]) <= set(app["clients"]), app["key"])

    def test_bad_values_are_rejected(self) -> None:
        base = {"key": "x", "label": "X", "group": "app"}
        for extra in (
            {"color": "blue"},
            {"color": "#FFE066"},  # too light for white text
            {"scoped": ("site",)},
            {"scoped": ("galaxy",)},
            {"clients": "one"},
            {"device": {"Nope": (("a", "b"),)}, "clients": ("Yes",)},
            {"device": {"Yes": (("a",),)}, "clients": ("Yes",)},
        ):
            with self.assertRaises(ValueError, msg=str(extra)):
                app_catalog._normalise({**base, **extra}, "test")
        ok = app_catalog._normalise({**base, "device": {"C": (("a", "b"),)}, "clients": ("C",), "color": "#123456"}, "test")
        self.assertEqual(ok["device"], {"C": (("a", "b"),)})
        self.assertEqual(app_catalog._normalise(base, "test")["color"], settings_palette.DEFAULT_COLOR)


class TestPaletteContrast(unittest.TestCase):
    """WCAG: text needs 4.5:1. White text on every manifest accent, accent ink on white and on its tint, and the same in the
    dark card, for every app that ships."""

    def test_every_manifest_color(self) -> None:
        for app in app_catalog.catalog():
            c = app["color"]
            p = settings_palette.palette(c)
            d = p["dark"]
            with self.subTest(app=app["key"], color=c):
                self.assertGreaterEqual(settings_palette.contrast(c, settings_palette.WHITE), 4.5, "white on the accent fill")
                self.assertGreaterEqual(settings_palette.contrast(p["on_accent"], p["accent"]), 4.5)
                self.assertGreaterEqual(settings_palette.contrast(p["ink"], settings_palette.WHITE), 4.5)
                self.assertGreaterEqual(settings_palette.contrast(p["ink"], p["tint"]), 4.5)
                self.assertGreaterEqual(settings_palette.contrast(d["accent"], d["card"]), 4.5)
                self.assertGreaterEqual(settings_palette.contrast(d["accent"], d["tint"]), 4.5)
                self.assertGreaterEqual(settings_palette.contrast(d["on_accent"], d["accent"]), 4.5)

    def test_status_and_scope_colors_in_the_stylesheet(self) -> None:
        css = open(os.path.join(PACKAGE, "public", "css", "zg_settings_map.css"), encoding="utf-8").read()
        light, dark = css.split('[data-theme="dark"] .zgs {')[0], css.split('[data-theme="dark"] .zgs {')[1].split("}")[0]
        tokens = lambda block: dict(re.findall(r"--zgs-(scope-\w+|s-\w+):\s*(#[0-9a-fA-F]{6})", block))
        for name, value in tokens(light).items():
            self.assertGreaterEqual(settings_palette.contrast(value, "#FFFFFF"), 4.5, f"light {name}")
        for name, value in tokens(dark).items():
            self.assertGreaterEqual(settings_palette.contrast(value, settings_palette.DARK_CARD), 4.5, f"dark {name}")

    def test_contrast_math(self) -> None:
        self.assertAlmostEqual(settings_palette.contrast("#000000", "#FFFFFF"), 21.0, places=1)


class TestControls(unittest.TestCase):
    def df(self, fieldtype: str, options: str = "", **kw):
        return frappe._dict({"fieldtype": fieldtype, "options": options, "fieldname": "f", "label": "F", "hidden": 0, "read_only": 0, **kw})

    def test_control_map(self) -> None:
        cases = [
            (("Check",), "switch"),
            (("Select", "A\nB\nC"), "choice"),
            (("Select", "\nA\nB\nC\nD"), "choice"),
            (("Select", "A\nB\nC\nD\nE"), "select"),
            (("Link", "Company"), "link"),
            (("Int",), "number"),
            (("Percent",), "number"),
            (("Float",), "number"),
            (("Data",), "text"),
            (("Small Text",), "textarea"),
            (("Password",), "password"),
            (("Table", "X"), "table"),
            (("Attach Image",), "attach"),
            (("Time",), "time"),
        ]
        for args, expected in cases:
            self.assertEqual(settings_map.control_for(self.df(*args)), expected, args)

    def test_locked_fields(self) -> None:
        self.assertIsNone(settings_map.locked_reason(self.df("Data")))
        self.assertEqual(settings_map.locked_reason(self.df("Password")), "secret")
        self.assertEqual(settings_map.locked_reason(self.df("Table", "X")), "table")
        self.assertEqual(settings_map.locked_reason(self.df("Attach")), "attachment")
        self.assertEqual(settings_map.locked_reason(self.df("Data", hidden=1)), "hidden")
        self.assertEqual(settings_map.locked_reason(self.df("Data", read_only=1)), "read_only")
        for field in app_catalog.switch_fields().values():
            df = self.df("Check")
            df.fieldname = field
            self.assertEqual(settings_map.locked_reason(df), "app_switch", field)
        # ordinary enable_* settings are not app switches
        df = self.df("Check")
        df.fieldname = "enable_ifrs_reports"
        self.assertIsNone(settings_map.locked_reason(df))


class TestNotes(unittest.TestCase):
    def test_every_note_points_at_something_real(self) -> None:
        for name, note in settings_notes.DOCTYPES.items():
            meta = _doctype_json(name)
            self.assertIsNotNone(meta, f"{name}: no DocType JSON in this app")
            fields = {f["fieldname"]: f for f in meta["fields"]}
            self.assertIn(note.get("status", "info"), settings_notes.STATUSES, name)
            self.assertIn(note.get("scope", "site"), app_catalog.SCOPES, name)
            for path in filter(None, [note.get("enforced_by")]):
                self._path_exists(name, path)
            for tab in note.get("tabs") or {}:
                self.assertEqual(fields.get(tab, {}).get("fieldtype"), "Tab Break", f"{name}: {tab}")
            for fieldname, f in (note.get("fields") or {}).items():
                self.assertIn(fieldname, fields, f"{name}: note for unknown field {fieldname}")
                self.assertNotIn(fields[fieldname]["fieldtype"], ("Section Break", "Column Break", "Tab Break", "HTML"), fieldname)
                self.assertIn(f.get("status", "info"), settings_notes.STATUSES, fieldname)
                self.assertIn(f.get("scope", "site"), app_catalog.SCOPES, fieldname)
                if f.get("enforced_by"):
                    self._path_exists(name, f["enforced_by"])

    def _path_exists(self, name: str, path: str) -> None:
        file = path.split("::")[0]
        self.assertTrue(os.path.isfile(os.path.join(PACKAGE, file)), f"{name}: {file} does not exist")

    def test_every_catalog_doctype_has_a_note(self) -> None:
        missing = sorted(dt for dt in app_catalog.settings_doctypes() if dt not in settings_notes.DOCTYPES)
        self.assertEqual(missing, [], "add them to services/settings_notes.py (even as plain 'info')")

    def test_field_merges_doctype_defaults(self) -> None:
        pos = settings_notes.field("ZG POS Settings", "pos_type")
        self.assertEqual(pos["status"], "enforced")
        self.assertEqual(settings_notes.field("ZG POS Settings", "default_warehouse")["status"], "unwired")
        self.assertEqual(settings_notes.field("Nope", "x")["status"], "info")

    def test_no_secret_values_in_notes_or_manifests(self) -> None:
        text = json.dumps(settings_notes.DOCTYPES) + json.dumps([a["device"] for a in app_catalog.catalog()])
        self.assertIsNone(re.search(r"(password|api[_-]?key|secret)\s*[:=]\s*\S{6,}", text, re.I))


if __name__ == "__main__":
    unittest.main()
