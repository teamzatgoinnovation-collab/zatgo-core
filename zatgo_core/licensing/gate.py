"""Capability gate: refuse what the site's licence does not include (docs/licensing.md, Phase 4).

Inert unless `entitlement.active()` returns one (enforcement switch on AND a verified entitlement) -- until
Phase 5 no site has an entitlement, so these hooks return at once everywhere.

What is enforced (decision D6 -- unlicensed means read-only, never lost):
- **refused** for a DocType the registry maps, when no licensed feature grants the action on that document:
  create, write, delete, submit, amend, import;
- **always allowed**: read, print, email, export, report, share -- history stays viewable and printable (ZATCA
  invoices must stay reproducible) -- and **cancel**, so a mistake can still be reversed through ERPNext's
  own cancellation;
- DocTypes the registry does not map (ledgers, NEVER_GATE, anything not product-controlled), and documents no
  feature describes at all (a Stock Entry purpose no feature lists, e.g. Repack), are never touched.

Layers (no single Frappe hook sees everything -- same shape as services/subscription_gate.py):
1. `doc_has_permission` (has_permission "*"): permission checks on a document -- Desk buttons, REST, list
   actions. Frappe skips it for Administrator.
2. `enforce_doc_write` (doc_events "*" validate / on_trash / before_update_after_submit): every write,
   `ignore_permissions` or not, Administrator included -- custom endpoints, imports, background jobs a user
   started. Runs after the controller's own validate, so fields like Stock Entry `purpose` are set.
Exempt: install / migrate / patch, and Administrator outside a web request (scheduler, bench console) --
system work, not a customer's.

Apps, industries and VanSaleX keys are licensed through their own registries (services/app_state.py,
industries/gate.py, services/vansalex_access.py ask `licensing.gate`), so an unlicensed app cannot be
switched on and its API answers 404 like a switched-off one.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint

from zatgo_core.licensing import entitlement as ent
from zatgo_core.licensing import registry

ENFORCED = frozenset({"create", "write", "delete", "submit", "amend", "import"})


# -- the rule -----------------------------------------------------------------------------------------------------

def _value_matches(actual: Any, expected: Any) -> bool:
    if isinstance(expected, tuple):
        return any(_value_matches(actual, e) for e in expected)
    if isinstance(expected, int) and not isinstance(expected, bool):
        return cint(actual) == expected
    return (actual or "") == expected


def grant_matches(grant: registry.DocTypeGrant, doc: Any) -> bool:
    if doc is None or not grant.match:
        return True
    getter = doc.get if hasattr(doc, "get") else (lambda k: getattr(doc, k, None))
    return all(_value_matches(getter(field), expected) for field, expected in grant.match)


def decide(doctype: str, ptype: str, doc: Any = None, entitlement: ent.Entitlement | None = None) -> dict[str, Any]:
    """Pure decision for one check: {"allowed": bool, "features": [ids that would grant it]}."""
    if entitlement is None or ptype not in ENFORCED:
        return {"allowed": True, "features": []}
    every = [(fid, g) for fid, g in registry.doctype_index().get(doctype, ()) if grant_matches(g, doc)]
    if not every:
        return {"allowed": True, "features": []}  # not product-controlled
    for fid, grant in every:
        if fid in entitlement.features and ptype in grant.actions and ptype in entitlement.features[fid]:
            return {"allowed": True, "features": [fid]}
    return {"allowed": False, "features": sorted({fid for fid, g in every if ptype in g.actions})}


def allowed(doctype: str, ptype: str, doc: Any = None) -> bool:
    return decide(doctype, ptype, doc, ent.active())["allowed"]


# -- exemptions ---------------------------------------------------------------------------------------------------

def _system_context(user: str | None = None) -> bool:
    """Install / migrate / patch, or Administrator outside a request (scheduler jobs, bench console). `user` is
    the user a permission check is about -- not necessarily the session's."""
    flags = frappe.flags
    if flags.in_install or flags.in_migrate or flags.in_patch or flags.in_uninstall or flags.in_licensing_sync:
        return True
    return (user or frappe.session.user) == "Administrator" and getattr(frappe.local, "request", None) is None


def _refuse(doctype: str, ptype: str, features: list[str]) -> None:
    labels = [registry.get_feature(f).label for f in features if registry.get_feature(f)]
    action = _(ptype)
    if labels:
        msg = _("Your ZatGo licence does not include {0} for {1}. It needs: {2}.").format(
            action, _(doctype), ", ".join(labels))
    else:
        msg = _("Your ZatGo licence does not include {0} for {1}.").format(action, _(doctype))
    frappe.throw(msg, frappe.PermissionError, title=_("Not licensed"))


# -- layer 1: permission checks -----------------------------------------------------------------------------------

def doc_has_permission(doc: Any = None, ptype: str | None = None, user: str | None = None, **kwargs: Any) -> bool:
    """has_permission "*": True (never None, which Frappe reads as a denial) unless this write is not licensed."""
    if ptype not in ENFORCED:
        return True
    entitlement = ent.active()
    if entitlement is None or _system_context(user):
        return True
    if ptype == "write" and doc is not None:
        ptype = _write_means(doc)
        if ptype is None:
            return True
    return decide(getattr(doc, "doctype", None) or "", ptype, doc, entitlement)["allowed"]


def _write_means(doc: Any) -> str | None:
    """Frappe checks "write" inside cancel and submit too (Document._save, before `_action` is set): a document
    heading for docstatus 2 is being cancelled (always allowed -> None); one heading for 1 from a draft is being
    submitted, and is checked as such."""
    status = cint(getattr(doc, "docstatus", 0))
    if status == 2:
        return None
    if status == 1:
        if doc.is_new() if hasattr(doc, "is_new") else False:
            return "submit"
        stored = frappe.db.get_value(doc.doctype, doc.name, "docstatus")
        if stored is not None and cint(stored) == 0:
            return "submit"
    return "write"


# -- layer 2: document events -------------------------------------------------------------------------------------

def _check(doc: Any, ptype: str, entitlement: ent.Entitlement) -> None:
    verdict = decide(doc.doctype, ptype, doc, entitlement)
    if not verdict["allowed"]:
        _refuse(doc.doctype, ptype, verdict["features"])


def enforce_doc_write(doc: Any, method: str | None = None, *args: Any, **kwargs: Any) -> None:
    """doc_events "*" (validate, on_trash, before_update_after_submit)."""
    entitlement = ent.active()
    if entitlement is None or _system_context():
        return
    if doc.doctype in ("User", "Company") and method == "validate":
        check_limits(doc)
    if doc.doctype not in registry.doctype_index():
        return
    if method == "on_trash":
        _check(doc, "delete", entitlement)
        return
    if method == "before_update_after_submit":
        _check(doc, "write", entitlement)
        return
    action = getattr(doc, "_action", None)
    if action == "cancel":
        return
    if doc.is_new():
        _check(doc, "amend" if doc.get("amended_from") else "create", entitlement)
    elif action != "submit":
        _check(doc, "write", entitlement)
    if action == "submit" or cint(doc.get("docstatus")) == 1 and doc.is_new():
        _check(doc, "submit", entitlement)


# -- registries that license by key ------------------------------------------------------------------------------

def app_licensed(key: str) -> bool:
    """An app of services/app_catalog.py is licensed when no feature names it, or a licensed one does."""
    entitlement = ent.active()
    if entitlement is None:
        return True
    named = any(f.app_key == key for f in registry.features() if not f.retired)
    return not named or key in entitlement.app_keys


def industry_licensed(key: str) -> bool:
    entitlement = ent.active()
    if entitlement is None:
        return True
    named = any(f.industry == key for f in registry.features() if not f.retired)
    return not named or key in entitlement.industries


def vansalex_key_licensed(key: str) -> bool:
    entitlement = ent.active()
    if entitlement is None:
        return True
    named = any(key in f.vansalex_keys for f in registry.features() if not f.retired)
    return not named or key in entitlement.vansalex_keys


# -- licence limits (Phase 7, decision D10) -------------------------------------------------------------------------

def _counts_as_user(doc: Any) -> bool:
    return (cint(doc.get("enabled")) == 1 and doc.get("user_type") == "System User"
            and doc.name not in ("Administrator", "Guest"))


def check_limits(doc: Any) -> None:
    """Refuse a new licensed user (an enabled System User other than Administrator -- D9) or a new Company beyond
    the licence's limits. Existing users and companies are never disabled or removed (D10): only the change that
    would go over the limit is refused."""
    from zatgo_core.licensing.licences import current_terms

    terms = current_terms()
    limits = (terms or {}).get("limits") or {}
    if doc.doctype == "User":
        cap = cint(limits.get("max_users"))
        if not cap or not _counts_as_user(doc):
            return
        before = None if doc.is_new() else doc.get_doc_before_save()
        if before is not None and _counts_as_user(before):
            return  # already counted: editing an existing user is never refused
        others = frappe.db.count("User", {"enabled": 1, "user_type": "System User",
                                          "name": ["not in", ["Administrator", "Guest", doc.name]]})
        if others + 1 > cap:
            frappe.throw(_("Your ZatGo licence allows {0} users and {1} are active. Disable a user or import a "
                           "licence with more users.").format(cap, others), frappe.PermissionError,
                         title=_("User limit reached"))
    elif doc.doctype == "Company" and doc.is_new():
        cap = cint(limits.get("max_companies"))
        if cap and frappe.db.count("Company") + 1 > cap:
            frappe.throw(_("Your ZatGo licence allows {0} companies. Import a licence with more companies to add "
                           "one.").format(cap), frappe.PermissionError, title=_("Company limit reached"))
