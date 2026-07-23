"""Seed DocPerm for VanSale roles on ERPNext + ZG DocTypes."""

from __future__ import annotations

import frappe

from zatgo_core.constants.roles import ROLES
from zatgo_core.utils.logging import get_logger

logger = get_logger("system")

ROLE_USER = ROLES["VANSALE_USER"]
ROLE_ADMIN = ROLES["VANSALE_ADMIN"]

# (doctype, role, perms dict)
_PERMS: list[tuple[str, str, dict]] = [
    # Sales Invoice
    ("Sales Invoice", ROLE_USER, {"read": 1, "write": 1, "create": 1, "submit": 1, "print": 1, "report": 1, "export": 1}),
    ("Sales Invoice", ROLE_ADMIN, {"read": 1, "write": 1, "create": 1, "submit": 1, "print": 1, "report": 1, "export": 1, "cancel": 1}),
    # Payment Entry
    ("Payment Entry", ROLE_USER, {"read": 1, "write": 1, "create": 1, "submit": 1, "print": 1, "report": 1}),
    ("Payment Entry", ROLE_ADMIN, {"read": 1, "write": 1, "create": 1, "submit": 1, "print": 1, "report": 1, "cancel": 1}),
    # Stock Entry
    ("Stock Entry", ROLE_USER, {"read": 1, "write": 1, "create": 1, "submit": 1, "report": 1}),
    ("Stock Entry", ROLE_ADMIN, {"read": 1, "write": 1, "create": 1, "submit": 1, "report": 1, "cancel": 1}),
    # Masters
    ("Customer", ROLE_USER, {"read": 1, "write": 1, "create": 1, "export": 1, "report": 1}),
    ("Customer", ROLE_ADMIN, {"read": 1, "write": 1, "create": 1, "export": 1, "report": 1, "delete": 1}),
    ("Item", ROLE_USER, {"read": 1, "write": 1, "create": 1, "export": 1, "report": 1}),
    ("Item", ROLE_ADMIN, {"read": 1, "write": 1, "create": 1, "export": 1, "report": 1, "delete": 1}),
    ("Warehouse", ROLE_USER, {"read": 1}),
    ("Warehouse", ROLE_ADMIN, {"read": 1}),
    ("Bin", ROLE_USER, {"read": 1}),
    ("Bin", ROLE_ADMIN, {"read": 1}),
    ("ZG Vehicle", ROLE_USER, {"read": 1}),
    ("ZG Vehicle", ROLE_ADMIN, {"read": 1, "write": 1, "create": 1}),
]


def _ensure_perm(doctype: str, role: str, flags: dict) -> None:
    if not frappe.db.exists("DocType", doctype):
        return
    existing = frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": role})
    if existing:
        doc = frappe.get_doc("Custom DocPerm", existing)
        changed = False
        for k, v in flags.items():
            if doc.get(k) != v:
                doc.set(k, v)
                changed = True
        if changed:
            doc.save(ignore_permissions=True)
        return
    # Also check standard DocPerm on the DocType itself
    if frappe.db.exists("DocPerm", {"parent": doctype, "role": role}):
        return
    row = {
        "doctype": "Custom DocPerm",
        "parent": doctype,
        "parenttype": "DocType",
        "parentfield": "permissions",
        "role": role,
        "permlevel": 0,
        **{k: 0 for k in ("read", "write", "create", "delete", "submit", "cancel", "amend", "report", "export", "import", "share", "print", "email")},
        **flags,
    }
    frappe.get_doc(row).insert(ignore_permissions=True)


def ensure_vansale_perms() -> None:
    """Grant least-privilege DocPerms for VanSale roles."""
    for doctype, role, flags in _PERMS:
        try:
            _ensure_perm(doctype, role, flags)
        except Exception:
            logger.exception("Failed to ensure perm %s / %s", doctype, role)
    frappe.clear_cache()
    logger.info("VanSale DocPerms ensured")
