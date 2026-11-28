"""services/core/erpnext_api.py: every ERPNext internal zatgo_core calls still exists and still takes the keyword
arguments our callers pass (upgrade risk C-02); and no code calls ERPNext internals around it."""

from __future__ import annotations

import ast
import inspect
import os
import unittest

from zatgo_core.services.core import erpnext_api

PACKAGE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODULE = "zatgo_core.services.core.erpnext_api"
# The only places that may import from erpnext directly: the adapter itself, and the version check before install.
ALLOWED_DIRECT = {os.path.join("services", "core", "erpnext_api.py"), "install.py"}


def _sources():
    for root, dirs, files in os.walk(PACKAGE):
        dirs[:] = [d for d in dirs if d not in ("tests", "__pycache__", "node_modules", "public", ".claude")]
        for name in files:
            if name.endswith(".py"):
                path = os.path.join(root, name)
                yield os.path.relpath(path, PACKAGE), path


def _keyword_calls() -> dict[str, set[str]]:
    """wrapper name -> keyword names passed to it anywhere in the package (aliases resolved per file)."""
    found: dict[str, set[str]] = {name: set() for name in erpnext_api.TARGETS}
    for _rel, path in _sources():
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        local = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == MODULE:
                for alias in node.names:
                    local[alias.asname or alias.name] = alias.name
        if not local:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in local:
                found[local[node.func.id]].update(k.arg for k in node.keywords if k.arg)
    return found


class TestErpnextApi(unittest.TestCase):
    def test_every_wrapper_has_a_target_that_exists(self) -> None:
        for name in erpnext_api.TARGETS:
            self.assertTrue(callable(getattr(erpnext_api, name, None)), f"no wrapper function {name}")
            self.assertTrue(callable(erpnext_api.target(name)), f"{erpnext_api.TARGETS[name]} is gone")

    def test_targets_accept_the_keywords_we_pass(self) -> None:
        for name, keywords in _keyword_calls().items():
            params = inspect.signature(erpnext_api.target(name)).parameters
            if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
                continue
            unknown = sorted(keywords - set(params))
            self.assertEqual(unknown, [], f"{erpnext_api.TARGETS[name]} no longer takes {unknown}")

    def test_no_direct_erpnext_imports_elsewhere(self) -> None:
        offenders = []
        for rel, path in _sources():
            if rel in ALLOWED_DIRECT:
                continue
            with open(path, encoding="utf-8") as f:
                tree = ast.parse(f.read())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "erpnext":
                    offenders.append(f"{rel}:{node.lineno} from {node.module}")
                elif isinstance(node, ast.Import) and any(a.name.split(".")[0] == "erpnext" for a in node.names):
                    offenders.append(f"{rel}:{node.lineno} import erpnext")
        self.assertEqual(offenders, [], "call ERPNext internals through services/core/erpnext_api.py")
