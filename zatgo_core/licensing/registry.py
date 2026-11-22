"""Module & feature registry: the vocabulary editions and licences are written in.

A **module** is a commercial grouping (Sales, Inventory, ...). A **feature** is the unit an edition includes
and a licence signs: a set of (DocType, actions) grants, optionally narrowed to documents whose fields match
(a Sales Return is a Sales Invoice with `is_return = 1`), plus the reports, pages, workspaces and whitelisted-
method prefixes that belong to it. The registry only *describes* existing functionality -- ERPNext's, hrms's,
zatca_integration's and zatgo_core's own; it never creates any.

Code, not data: it describes code that ships with this app, so it is versioned with it and the same on every
site. Pure Python -- no database, safe at import and in the middle of a migrate (like services/app_catalog.py).
`ZG Module` / `ZG Feature` are a read-only projection of it (licensing/sync.py).

Rules (tests/unit/test_licensing_registry.py enforces them):
- Ids are stable: `<module>.<feature>`, lower snake case. A licence signed today names them, so an id is never
  renamed or removed -- mark it `retired=True` instead. `catalog/ids.lock` lists every id ever shipped.
- `NEVER_GATE` DocTypes (ledgers, controller-created and system records) are never mapped: gating them would
  break posting (a Sales-only edition still writes GL Entry when it submits an invoice).
- Child tables are never mapped: they follow their parent.
- `requires` names what a feature needs beyond the foundation, with the actions it needs. Resolving it never
  adds anything (`resolve_requirements` reports what is missing) -- a paid module is never switched on because
  something else depends on it.
- `foundation=True` features are part of every edition: shared masters read-only, setup, users, backups.

A DocType can appear in several features (Account: read in foundation, full in accounting). What a site may do
with it is the union over the features its licence includes -- decided in Phase 4, not here.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Iterable

# -- vocabulary -------------------------------------------------------------------------------------------------

ACTIONS = (
    "read", "create", "write", "delete", "submit", "cancel", "amend",
    "print", "email", "export", "import", "report", "share",
)
PLATFORMS = ("desk", "desktop", "mobile")

# Action bundles the catalog files use.
VIEW = ("read", "report", "print", "email", "export", "share")
READ_ONLY = ("read", "report", "print")
MASTER = VIEW + ("create", "write", "delete", "import")
TRANSACTION = VIEW + ("create", "write", "delete", "submit", "cancel", "amend")
SETTINGS = ("read", "write")

ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
MODULE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

# Never mapped by any feature: ledgers and records ERPNext / Frappe create themselves while another document is
# saved or submitted, plus system and log records. Read access to them stays with role permissions alone.
NEVER_GATE = frozenset(
    {
        # ledgers and posting machinery
        "GL Entry", "Payment Ledger Entry", "Advance Payment Ledger Entry", "Stock Ledger Entry", "Bin",
        "Repost Item Valuation", "Repost Payment Ledger", "Repost Accounting Ledger", "Serial and Batch Bundle",
        "Stock Reservation Entry", "Process Deferred Accounting", "Unreconcile Payment", "Stock Closing Entry",
        "Stock Closing Balance", "Account Closing Balance", "Bisect Accounting Statements", "POS Invoice Merge Log",
        # e-invoicing records made on submit (zatca_integration)
        "ZATCA Invoice", "ZATCA Submission Log",
        # system / platform records zatgo_core itself needs
        "ZG System Settings", "ZG Registered Application", "ZG Setting Section", "ZG Module", "ZG Feature",
        "User", "Role", "Has Role", "DocType", "Custom Field", "Property Setter", "Custom DocPerm", "DocPerm",
        "Module Def", "Workspace", "Workspace Sidebar", "Desktop Icon", "Page", "File", "Session Default Settings",
    }
    # Everything the subscription gate already lets through (logs, queues, Version, Comment, ...).
    | frozenset(
        # copied, not imported: subscription_gate imports frappe and this module must stay importable without it
        {
            "Error Log", "Activity Log", "Access Log", "Scheduled Job Log", "Version", "Comment", "Communication",
            "Email Queue", "Email Queue Recipient", "Notification Log", "Route History", "Console Log",
            "Error Snapshot", "Prepared Report", "RQ Job", "RQ Worker", "Deleted Document", "Document Share Log",
            "Log Setting", "Integration Request", "Webhook Request Log", "Submission Queue", "Scheduler Event",
            "Energy Point Log", "ZG Audit Log", "Sessions", "Document Follow", "Notification Settings", "View Log",
            "Email Unsubscribe", "Webhook", "OAuth Bearer Token", "OAuth Authorization Code", "Token Cache",
            "Data Import Log", "DocShare",
        }
    )
)


# -- model ------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class DocTypeGrant:
    doctype: str
    actions: tuple[str, ...]
    # Field -> value (or tuple of values): the grant covers only documents that match every field.
    match: tuple[tuple[str, Any], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"doctype": self.doctype, "actions": list(self.actions)}
        if self.match:
            out["match"] = {k: (list(v) if isinstance(v, tuple) else v) for k, v in self.match}
        return out


@dataclass(frozen=True)
class Module:
    id: str
    label: str
    category: str
    description: str = ""
    icon: str = "folder-normal"
    order: int = 0
    source_app: str = "erpnext"


@dataclass(frozen=True)
class Feature:
    id: str
    module: str
    label: str
    description: str = ""
    doctypes: tuple[DocTypeGrant, ...] = ()
    reports: tuple[str, ...] = ()
    pages: tuple[str, ...] = ()
    workspaces: tuple[str, ...] = ()
    api_prefixes: tuple[str, ...] = ()
    # feature id -> actions it needs on that feature's DocTypes (() = the feature as a whole)
    requires: tuple[tuple[str, tuple[str, ...]], ...] = ()
    platforms: tuple[str, ...] = ("desk",)
    source_app: str = "erpnext"
    app_key: str | None = None  # services/app_catalog.py key this feature licenses
    industry: str | None = None  # industries/registry.py key
    vansalex_keys: tuple[str, ...] = ()  # services/vansalex_access.py CATALOG keys
    foundation: bool = False
    retired: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "module": self.module, "label": self.label, "description": self.description,
            "doctypes": [g.as_dict() for g in self.doctypes], "reports": list(self.reports),
            "pages": list(self.pages), "workspaces": list(self.workspaces), "api_prefixes": list(self.api_prefixes),
            "requires": {fid: list(acts) for fid, acts in self.requires}, "platforms": list(self.platforms),
            "source_app": self.source_app, "app_key": self.app_key, "industry": self.industry,
            "vansalex_keys": list(self.vansalex_keys), "foundation": self.foundation, "retired": self.retired,
        }

    def fingerprint(self) -> str:
        return hashlib.sha256(json.dumps(self.as_dict(), sort_keys=True).encode()).hexdigest()[:16]


# -- catalog-file helpers ---------------------------------------------------------------------------------------

def dt(doctype: str, actions: Iterable[str] = TRANSACTION, **match: Any) -> DocTypeGrant:
    """One DocType grant; keyword arguments narrow it to matching documents (`is_return=1`)."""
    return DocTypeGrant(
        doctype=doctype,
        actions=tuple(dict.fromkeys(actions)),
        match=tuple(sorted((k, tuple(v) if isinstance(v, (list, tuple)) else v) for k, v in match.items())),
    )


def feature(id: str, label: str, **kw: Any) -> Feature:
    """Catalog helper: `module` is the part of the id before the dot; lists become tuples."""
    kw.setdefault("module", id.split(".", 1)[0])
    for key in ("reports", "pages", "workspaces", "api_prefixes", "platforms", "vansalex_keys"):
        if key in kw:
            kw[key] = tuple(kw[key])
    kw["doctypes"] = tuple(kw.get("doctypes") or ())
    requires = kw.get("requires") or {}
    kw["requires"] = tuple(sorted((fid, tuple(acts or ())) for fid, acts in requires.items()))
    return Feature(id=id, label=label, **kw)


# -- loading ----------------------------------------------------------------------------------------------------

CATALOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "catalog")
IDS_LOCK = os.path.join(CATALOG_DIR, "ids.lock")


def catalog_files() -> list[str]:
    return sorted(f for f in os.listdir(CATALOG_DIR) if f.endswith(".py") and not f.startswith("_"))


def _load(path: str) -> Any:
    spec = importlib.util.spec_from_file_location(f"zatgo_core_licensing_{os.path.basename(path)[:-3]}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@lru_cache(maxsize=None)
def _registry() -> tuple[tuple[Module, ...], tuple[Feature, ...]]:
    modules: list[Module] = []
    features: list[Feature] = []
    for name in catalog_files():
        mod = _load(os.path.join(CATALOG_DIR, name))
        # A file describes one MODULE, or several in MODULES.
        modules.extend(getattr(mod, "MODULES", None) or [mod.MODULE])
        features.extend(mod.FEATURES)
    modules.sort(key=lambda m: (m.order, m.id))
    return tuple(modules), tuple(features)


def modules() -> tuple[Module, ...]:
    return _registry()[0]


def features() -> tuple[Feature, ...]:
    return _registry()[1]


def get_module(module_id: str) -> Module | None:
    return next((m for m in modules() if m.id == module_id), None)


def get_feature(feature_id: str) -> Feature | None:
    return _feature_map().get(feature_id)


@lru_cache(maxsize=None)
def _feature_map() -> dict[str, Feature]:
    return {f.id: f for f in features()}


def features_of_module(module_id: str) -> tuple[Feature, ...]:
    return tuple(f for f in features() if f.module == module_id)


def foundation_features() -> tuple[Feature, ...]:
    return tuple(f for f in features() if f.foundation and not f.retired)


@lru_cache(maxsize=None)
def doctype_index() -> dict[str, tuple[tuple[str, DocTypeGrant], ...]]:
    """DocType -> ((feature id, grant), ...) over every live feature."""
    out: dict[str, list[tuple[str, DocTypeGrant]]] = {}
    for f in features():
        if f.retired:
            continue
        for grant in f.doctypes:
            out.setdefault(grant.doctype, []).append((f.id, grant))
    return {k: tuple(v) for k, v in out.items()}


def registry_hash() -> str:
    payload = [f.fingerprint() for f in features()] + [repr(m) for m in modules()]
    return hashlib.sha256("\n".join(payload).encode()).hexdigest()[:16]


def locked_ids() -> list[str]:
    with open(IDS_LOCK, encoding="utf-8") as fh:
        return [line.strip() for line in fh if line.strip() and not line.startswith("#")]


# -- dependencies -----------------------------------------------------------------------------------------------

def resolve_requirements(feature_ids: Iterable[str]) -> dict[str, Any]:
    """What a selection of features needs that it does not include, transitively. Never adds anything.

    Returns {"selected": [...], "foundation": [...], "missing": [{"feature", "needed_by", "actions",
    "module"}], "unknown": [...], "retired": [...]}. Foundation features count as included."""
    selected = list(dict.fromkeys(feature_ids))
    have = set(selected) | {f.id for f in foundation_features()}
    unknown = [fid for fid in selected if fid not in _feature_map()]
    retired = [fid for fid in selected if fid in _feature_map() and _feature_map()[fid].retired]
    missing: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    stack = [fid for fid in selected if fid in _feature_map()]
    visited: set[str] = set()
    while stack:
        fid = stack.pop()
        if fid in visited:
            continue
        visited.add(fid)
        for need, actions in _feature_map()[fid].requires:
            if need in have:
                continue
            if (need, fid) not in seen:
                seen.add((need, fid))
                target = _feature_map().get(need)
                missing.append({"feature": need, "needed_by": fid, "actions": list(actions),
                                "module": target.module if target else None})
            if need in _feature_map():
                stack.append(need)  # what a missing feature needs is missing too: show the whole chain
    return {
        "selected": selected,
        "foundation": sorted(f.id for f in foundation_features()),
        "missing": sorted(missing, key=lambda m: (m["feature"], m["needed_by"])),
        "unknown": unknown,
        "retired": retired,
    }


def dependency_cycles(feats: Iterable[Feature] | None = None) -> list[list[str]]:
    cycles: list[list[str]] = []
    graph = {f.id: [need for need, _ in f.requires] for f in (features() if feats is None else feats)}
    state: dict[str, int] = {}

    def visit(node: str, path: list[str]) -> None:
        state[node] = 1
        for nxt in graph.get(node, ()):
            if state.get(nxt) == 1:
                cycles.append(path[path.index(nxt):] + [nxt] if nxt in path else [node, nxt])
            elif nxt in graph and state.get(nxt) is None:
                visit(nxt, path + [nxt])
        state[node] = 2

    for node in graph:
        if state.get(node) is None:
            visit(node, [node])
    return cycles


# -- validation (structure only; existence on a site is tests/integration/test_licensing_registry.py) ----------

def validate(mods: Iterable[Module] | None = None, feats: Iterable[Feature] | None = None,
             locked: Iterable[str] | None = None) -> list[str]:
    """Problems with the registry (or with the given modules / features / lock, for tests); [] when sound."""
    mods = tuple(modules() if mods is None else mods)
    feats = tuple(features() if feats is None else feats)
    by_id = {f.id: f for f in feats}
    problems: list[str] = []
    module_ids = [m.id for m in mods]
    for mid in module_ids:
        if not MODULE_ID_PATTERN.match(mid):
            problems.append(f"module {mid!r}: bad id")
    if len(set(module_ids)) != len(module_ids):
        problems.append("duplicate module ids")
    ids = [f.id for f in feats]
    for fid in {i for i in ids if ids.count(i) > 1}:
        problems.append(f"{fid}: duplicate feature id")
    for f in feats:
        where = f.id
        if not ID_PATTERN.match(f.id):
            problems.append(f"{where}: id must be <module>.<feature> in lower snake case")
        if f.module not in module_ids:
            problems.append(f"{where}: unknown module {f.module!r}")
        elif not f.id.startswith(f.module + "."):
            problems.append(f"{where}: id must start with its module {f.module!r}")
        if not (f.doctypes or f.reports or f.pages or f.workspaces or f.api_prefixes or f.app_key
                or f.industry or f.vansalex_keys):
            problems.append(f"{where}: maps nothing")
        seen_dt: set[tuple[str, tuple]] = set()
        for g in f.doctypes:
            if g.doctype in NEVER_GATE:
                problems.append(f"{where}: {g.doctype} is in NEVER_GATE")
            if bad := [a for a in g.actions if a not in ACTIONS]:
                problems.append(f"{where}: {g.doctype}: unknown actions {bad}")
            if not g.actions:
                problems.append(f"{where}: {g.doctype}: no actions")
            if (g.doctype, g.match) in seen_dt:
                problems.append(f"{where}: {g.doctype} listed twice")
            seen_dt.add((g.doctype, g.match))
        if bad := [p for p in f.platforms if p not in PLATFORMS]:
            problems.append(f"{where}: unknown platforms {bad}")
        if not f.platforms:
            problems.append(f"{where}: no platform")
        for p in f.api_prefixes:
            if not p.endswith("."):
                problems.append(f"{where}: api prefix {p!r} must end with '.'")
        for need, actions in f.requires:
            if need == f.id:
                problems.append(f"{where}: requires itself")
            elif need not in by_id:
                problems.append(f"{where}: requires unknown feature {need!r}")
            if bad := [a for a in actions if a not in ACTIONS]:
                problems.append(f"{where}: requires {need} with unknown actions {bad}")
        if f.foundation and f.requires:
            problems.append(f"{where}: a foundation feature cannot require anything")
    for cycle in dependency_cycles(feats):
        problems.append("dependency cycle: " + " -> ".join(cycle))
    locked = set(locked_ids() if locked is None else locked)
    if missing := sorted(set(ids) - locked):
        problems.append(f"ids not in catalog/ids.lock (add them): {missing}")
    if vanished := sorted(locked - set(ids)):
        problems.append(f"ids in ids.lock no longer in the catalog (retire them, never delete): {vanished}")
    return problems


def summary() -> dict[str, Any]:
    """Counts for docs / the UI."""
    return {
        "modules": len(modules()),
        "features": len([f for f in features() if not f.retired]),
        "foundation": len(foundation_features()),
        "doctypes": len(doctype_index()),
        "hash": registry_hash(),
    }


__all__ = [
    "ACTIONS", "PLATFORMS", "VIEW", "READ_ONLY", "MASTER", "TRANSACTION", "SETTINGS", "NEVER_GATE",
    "DocTypeGrant", "Module", "Feature", "dt", "feature", "modules", "features", "get_module", "get_feature",
    "features_of_module", "foundation_features", "doctype_index", "registry_hash", "locked_ids",
    "resolve_requirements", "dependency_cycles", "validate", "summary",
]

