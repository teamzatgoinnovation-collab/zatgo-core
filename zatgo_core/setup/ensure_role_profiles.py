"""ZatGo access personas as native Role Profiles (Phase 8), made from ERPNext's standard roles.

Created once when missing, then the site's: an administrator may change a profile in Desk (Role Profile) and it is
never reset. A user on a profile gets exactly its roles (Frappe re-applies them on every save of the user).

Record-level limits are User Permissions, not profiles. `restrict_user` sets them in one call, for example the
"restricted stock" persona: Stock User profile + Item Group + Warehouse permissions.

    bench --site X execute zatgo_core.setup.ensure_role_profiles.restrict_user \\
        --kwargs "{'user': 'cold@example.com', 'item_groups': ['Frozen'], 'warehouses': ['Cold Store - ZTC']}"
"""

from __future__ import annotations

from typing import Iterable

import frappe

PROFILES: dict[str, tuple[str, ...]] = {
    "ZatGo Sales User": ("Sales User",),
    "ZatGo Sales Manager": ("Sales Manager", "Sales User"),
    "ZatGo Purchase User": ("Purchase User",),
    "ZatGo Stock User": ("Stock User",),
    "ZatGo Restricted Stock User": ("Stock User",),  # + Item Group / Warehouse User Permissions (restrict_user)
    "ZatGo Accountant": ("Accounts User",),
    "ZatGo Administrator": ("System Manager", "ZatGo Application Admin"),
}


def ensure_role_profiles() -> list[str]:
    """Create the missing profiles (only with roles that exist on the site). Returns the names created."""
    if not frappe.db.exists("DocType", "Role Profile"):
        return []
    created = []
    for name, roles in PROFILES.items():
        if frappe.db.exists("Role Profile", name):
            continue
        existing = [r for r in roles if frappe.db.exists("Role", r)]
        if not existing:
            continue
        frappe.get_doc({"doctype": "Role Profile", "role_profile": name,
                        "roles": [{"role": r} for r in existing]}).insert(ignore_permissions=True)
        created.append(name)
    return created


def restrict_user(
    user: str,
    *,
    companies: Iterable[str] = (),
    warehouses: Iterable[str] = (),
    item_groups: Iterable[str] = (),
    items: Iterable[str] = (),
    customers: Iterable[str] = (),
) -> list[str]:
    """Add User Permissions (apply to all DocTypes) so `user` sees only these records. Idempotent; existing
    permissions are kept. Only a System Manager (or the bench) may do this. Returns the User Permissions created."""
    if frappe.session.user != "Administrator" and "System Manager" not in frappe.get_roles():
        frappe.throw("Only a System Manager can restrict users.", frappe.PermissionError)
    if not frappe.db.exists("User", user):
        frappe.throw(f"No such user: {user}")
    made = []
    for allow, values in (("Company", companies), ("Warehouse", warehouses), ("Item Group", item_groups),
                          ("Item", items), ("Customer", customers)):
        for value in values:
            if not frappe.db.exists(allow, value):
                frappe.throw(f"No such {allow}: {value}")
            if frappe.db.exists("User Permission", {"user": user, "allow": allow, "for_value": value}):
                continue
            doc = frappe.get_doc({"doctype": "User Permission", "user": user, "allow": allow, "for_value": value,
                                  "apply_to_all_doctypes": 1}).insert(ignore_permissions=True)
            made.append(doc.name)
    return made
