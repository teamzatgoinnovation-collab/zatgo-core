"""Seed DocPerm for VanSale roles on ERPNext + ZG DocTypes (once per pair)."""

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
    # Sales Order — the "Order" side of the Order -> Confirm -> Invoice flow.
    ("Sales Order", ROLE_USER, {"read": 1, "write": 1, "create": 1, "submit": 1, "print": 1, "report": 1, "export": 1}),
    ("Sales Order", ROLE_ADMIN, {"read": 1, "write": 1, "create": 1, "submit": 1, "print": 1, "report": 1, "export": 1, "cancel": 1}),
    # Payment Entry
    ("Payment Entry", ROLE_USER, {"read": 1, "write": 1, "create": 1, "submit": 1, "print": 1, "report": 1}),
    ("Payment Entry", ROLE_ADMIN, {"read": 1, "write": 1, "create": 1, "submit": 1, "print": 1, "report": 1, "cancel": 1}),
    # Stock Entry
    ("Stock Entry", ROLE_USER, {"read": 1, "write": 1, "create": 1, "submit": 1, "report": 1}),
    ("Stock Entry", ROLE_ADMIN, {"read": 1, "write": 1, "create": 1, "submit": 1, "report": 1, "cancel": 1}),
    # Masters
    ("Customer", ROLE_USER, {"read": 1, "write": 1, "create": 1, "export": 1, "report": 1}),
    ("Customer", ROLE_ADMIN, {"read": 1, "write": 1, "create": 1, "export": 1, "report": 1, "delete": 1}),
    # Address / Contact — every Customer created via sync gets a linked
    # billing Address + Contact, and ERPNext's Sales Invoice/Payment Entry
    # validate() renders the customer's address on every save via
    # render_address()->check_permission(); without read here (and create
    # for the sync flow that makes them), every non-admin VanSale User order
    # or collection fails with PermissionError.
    ("Address", ROLE_USER, {"read": 1, "write": 1, "create": 1, "report": 1}),
    ("Address", ROLE_ADMIN, {"read": 1, "write": 1, "create": 1, "report": 1, "delete": 1}),
    ("Contact", ROLE_USER, {"read": 1, "write": 1, "create": 1, "report": 1}),
    ("Contact", ROLE_ADMIN, {"read": 1, "write": 1, "create": 1, "report": 1, "delete": 1}),
    ("Item", ROLE_USER, {"read": 1, "write": 1, "create": 1, "export": 1, "report": 1}),
    ("Item", ROLE_ADMIN, {"read": 1, "write": 1, "create": 1, "export": 1, "report": 1, "delete": 1}),
    # Item Price — ERPNext's Item.after_insert() auto-creates an Item Price
    # for the default selling price list whenever a new Item has a selling
    # rate. Without create/write here, that insert throws PermissionError
    # from inside the Item insert itself, so the whole product (and every
    # order that references it) fails to sync.
    ("Item Price", ROLE_USER, {"read": 1, "write": 1, "create": 1}),
    ("Item Price", ROLE_ADMIN, {"read": 1, "write": 1, "create": 1, "delete": 1}),
    ("Warehouse", ROLE_USER, {"read": 1}),
    ("Warehouse", ROLE_ADMIN, {"read": 1}),
    ("Bin", ROLE_USER, {"read": 1}),
    ("Bin", ROLE_ADMIN, {"read": 1}),
    # Account — ERPNext's Sales Invoice/Payment Entry resolve the customer's
    # receivable account internally on every save; without read access here,
    # every order/collection a non-admin VanSale User makes fails.
    ("Account", ROLE_USER, {"read": 1}),
    ("Account", ROLE_ADMIN, {"read": 1}),
    ("ZG Vehicle", ROLE_USER, {"read": 1}),
    ("ZG Vehicle", ROLE_ADMIN, {"read": 1, "write": 1, "create": 1}),
    # ZG Trip — vansalex/trips.py, vansalex_service.update_visit() require read/write
    # via require_doc_permission/has_permission; without these, VanSale User and
    # VanSale Admin accounts (non System Manager) get PermissionError on the
    # core trip/visit flow.
    ("ZG Trip", ROLE_USER, {"read": 1, "write": 1, "create": 1}),
    ("ZG Trip", ROLE_ADMIN, {"read": 1, "write": 1, "create": 1, "delete": 1}),
    ("ZG Delivery Stop", ROLE_USER, {"read": 1, "write": 1}),
    ("ZG Delivery Stop", ROLE_ADMIN, {"read": 1, "write": 1, "create": 1, "delete": 1}),
]


# Roles every staff member (or everyone) holds.
_BROAD_ROLES = {"All", "Desk User", "Guest"}
_WRITE_FLAGS = ("write", "create", "delete", "submit", "cancel", "amend")


def _seeded_key(doctype: str, role: str) -> str:
    return f"zg_vansale_perm_{frappe.scrub(doctype)}_{frappe.scrub(role)}"


def _standard_kept_key(doctype: str) -> str:
    return f"zg_vansale_std_perms_{frappe.scrub(doctype)}"


def _opens_to_all_staff(row: dict) -> bool:
    """A standard row that lets every staff member change other people's records. Never in effect on a seeded site, and
    VanSale roles are least-privilege (VanSale User holds Desk User too, and is read-only on ZG Vehicle), so it stays out."""
    return row.role in _BROAD_ROLES and not row.if_owner and any(row.get(flag) for flag in _WRITE_FLAGS)


def _keep_standard_perms(doctype: str) -> None:
    """Copy the DocType's standard rows into Custom DocPerm -- once per DocType.

    Frappe ignores every standard DocPerm of a DocType that has any Custom DocPerm, so a seeded row alone takes the
    DocType away from Accounts User, Stock User, Delivery, even System Manager. Role Permissions Manager copies them
    first for the same reason (`setup_custom_perms`), but only while no custom row exists. Add-only: a row with the same
    role, permlevel and if_owner is left as it is. After the marker they belong to the admin, like the seeded grants."""
    marker = _standard_kept_key(doctype)
    if frappe.db.get_global(marker):
        return
    have = {
        (r.role, r.permlevel, r.if_owner)
        for r in frappe.get_all("Custom DocPerm", filters={"parent": doctype}, fields=["role", "permlevel", "if_owner"])
    }
    for row in frappe.get_all("DocPerm", filters={"parent": doctype}, fields="*"):
        if (row.role, row.permlevel, row.if_owner) in have or _opens_to_all_staff(row):
            continue
        doc = frappe.new_doc("Custom DocPerm")
        doc.update({k: v for k, v in row.items() if k not in frappe.model.default_fields})
        doc.insert(ignore_permissions=True)
        logger.info("Kept standard DocPerm %s / %s (level %s)", doctype, row.role, row.permlevel)
    frappe.db.set_global(marker, 1)


def _ensure_perm(doctype: str, role: str, flags: dict) -> None:
    """Seed one (DocType, role) grant -- once.

    First time (no marker): create the Custom DocPerm, or top an existing
    one up to [flags] (add-only: the flags here are all 1), then record that
    it was seeded. After that the pair belongs to the site's admin: a row
    they delete is not re-created and a flag they change is not reset."""
    if not frappe.db.exists("DocType", doctype):
        return
    _keep_standard_perms(doctype)
    marker = _seeded_key(doctype, role)
    if frappe.db.get_global(marker):
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
    # Also check standard DocPerm on the DocType itself
    elif not frappe.db.exists("DocPerm", {"parent": doctype, "role": role}):
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
    frappe.db.set_global(marker, 1)


def ensure_vansale_perms() -> None:
    """Grant least-privilege DocPerms for VanSale roles -- once per DocType/role
    (see `_ensure_perm`): an admin's later removal or edit of a grant sticks."""
    for doctype, role, flags in _PERMS:
        try:
            _ensure_perm(doctype, role, flags)
        except Exception:
            logger.exception("Failed to ensure perm %s / %s", doctype, role)
    frappe.clear_cache()
    logger.info("VanSale DocPerms ensured")
