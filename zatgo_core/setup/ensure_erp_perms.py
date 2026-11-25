"""Seed the rights of the "ZatGo Accounts & Inventory" role (once per DocType / report).

The role owns the "ZatGo ERP" workspace (services/erp_workspace.py). Rights are least-privilege: the documents the
workspace links to, plus read access to what those documents look up while they are saved or printed (accounts, price
lists, taxes...). No cancel / delete anywhere. The seed-once rules of ensure_vansale_perms apply: the standard rows of a
DocType are copied to Custom DocPerm first (otherwise Frappe would drop them), and what an admin later removes or edits
stays that way.
"""

from __future__ import annotations

import frappe

from zatgo_core.services.erp_workspace import ROLE, SECTIONS
from zatgo_core.setup.ensure_vansale_perms import _ensure_perm
from zatgo_core.utils.logging import get_logger

logger = get_logger("system")

_DOC = {"read": 1, "write": 1, "create": 1, "submit": 1, "print": 1, "email": 1, "report": 1, "export": 1}
_MASTER = {"read": 1, "write": 1, "create": 1, "print": 1, "report": 1, "export": 1}
_SINGLE = {"read": 1, "write": 1}
_READ = {"read": 1}
_REPORTING = {"read": 1, "report": 1, "export": 1, "print": 1}

_PERMS: list[tuple[str, dict]] = [
    # Transactions
    ("Sales Invoice", _DOC),
    ("Purchase Invoice", _DOC),
    ("Sales Order", _DOC),
    ("Purchase Order", _DOC),
    ("Payment Entry", _DOC),
    ("Payment Reconciliation", _SINGLE),
    # Setup
    ("Item", _MASTER),
    ("Customer", _MASTER),
    ("Supplier", _MASTER),
    ("Warehouse", _MASTER),
    # What the documents above create or look up on every save
    ("Address", {"read": 1, "write": 1, "create": 1}),
    ("Contact", {"read": 1, "write": 1, "create": 1}),
    ("Item Price", {"read": 1, "write": 1, "create": 1}),
    # Behind the reports
    ("GL Entry", _REPORTING),
    ("Stock Ledger Entry", _REPORTING),
    ("Bin", _REPORTING),
    # The summary block on the workspace page is a Custom HTML Block the user must be able to read
    ("Custom HTML Block", _READ),
    # The Dashboard entry of the sidebar: ERPNext charts and number cards
    ("Dashboard", _READ),
    ("Dashboard Chart", _READ),
    ("Number Card", _READ),
    # Settings: read only
    ("Accounts Settings", _READ),
    ("Stock Settings", _READ),
    ("Buying Settings", _READ),
    ("Selling Settings", _READ),
    ("Print Settings", _READ),
    ("System Settings", _READ),
] + [
    (dt, _READ)
    for dt in (
        "Company", "Account", "Cost Center", "Item Group", "UOM", "Brand", "Customer Group", "Territory", "Supplier Group",
        "Price List", "Mode of Payment", "Fiscal Year", "Currency", "Project", "Sales Taxes and Charges Template",
        "Purchase Taxes and Charges Template", "Item Tax Template", "Payment Terms Template", "Tax Category",
        "Stock Entry Type", "Warehouse Type",
    )
]


def _report_names() -> list[str]:
    return [i["link_to"] for _label, _icon, items in SECTIONS for i in items if i["link_type"] == "Report"]


def _ensure_report_role(report: str) -> None:
    """Add ROLE to the report's roles through a Custom Role row (standard reports keep their own roles) -- once."""
    marker = f"zg_erp_report_role_{frappe.scrub(report)}"
    if frappe.db.get_global(marker) or not frappe.db.exists("Report", report):
        return
    name = frappe.db.exists("Custom Role", {"report": report})
    doc = frappe.get_doc("Custom Role", name) if name else frappe.new_doc("Custom Role")
    if not name:
        doc.report = report
        # Keep the roles the report already has: a Custom Role replaces them.
        for r in frappe.get_all("Has Role", filters={"parent": report, "parenttype": "Report"}, pluck="role"):
            doc.append("roles", {"role": r})
    if ROLE not in [r.role for r in doc.get("roles", [])]:
        doc.append("roles", {"role": ROLE})
        doc.save(ignore_permissions=True) if name else doc.insert(ignore_permissions=True)
    frappe.db.set_global(marker, 1)


def ensure_erp_perms() -> None:
    """Rights of the ZatGo Accounts & Inventory role: DocPerms and report roles, once per DocType / report."""
    if not frappe.db.exists("Role", ROLE):
        return
    for doctype, flags in _PERMS:
        try:
            _ensure_perm(doctype, ROLE, flags)
        except Exception:
            logger.exception("Failed to ensure perm %s / %s", doctype, ROLE)
    for report in _report_names():
        try:
            _ensure_report_role(report)
        except Exception:
            logger.exception("Failed to ensure report role %s / %s", report, ROLE)
    frappe.clear_cache()
    logger.info("ZatGo Accounts & Inventory rights ensured")
