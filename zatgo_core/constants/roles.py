"""Enterprise roles for ZatGo Core."""

from __future__ import annotations

ROLES = {
    "SYSTEM_MANAGER": "System Manager",
    "ADMINISTRATOR": "Administrator",
    "COMPANY_ADMIN": "ZatGo Company Admin",
    "BRANCH_ADMIN": "ZatGo Branch Admin",
    "APPLICATION_ADMIN": "ZatGo Application Admin",
    "READ_ONLY": "ZatGo Read Only",
    "DELIVERY": "Delivery",
    "VANSALE_USER": "VanSale User",
    "VANSALE_ADMIN": "VanSale Admin",
    # Manages Sales Invoice Naming Settings (user-wise invoice series).
    "INVOICE_NAMING_MANAGER": "ZatGo Invoice Naming Manager",
    # Owns the "ZatGo ERP" workspace and the rights its links need (setup/ensure_erp_perms.py). Same string as
    # services/erp_workspace.ROLE (kept import-free so the workspace generator script can run without bench).
    "ACCOUNTS_INVENTORY": "ZatGo Accounts & Inventory",
}

# Which roles may write which settings categories.
ROLE_PERMISSION_MATRIX: dict[str, dict[str, bool]] = {
    ROLES["SYSTEM_MANAGER"]: {
        "system": True,
        "company": True,
        "branch": True,
        "security": True,
        "integrations": True,
        "features": True,
        "audit": True,
        "apps": True,
    },
    ROLES["COMPANY_ADMIN"]: {
        "system": False,
        "company": True,
        "branch": True,
        "security": False,
        "integrations": False,
        "features": False,
        "audit": True,
        "apps": False,
    },
    ROLES["BRANCH_ADMIN"]: {
        "system": False,
        "company": False,
        "branch": True,
        "security": False,
        "integrations": False,
        "features": False,
        "audit": True,
        "apps": False,
    },
    ROLES["APPLICATION_ADMIN"]: {
        "system": False,
        "company": False,
        "branch": False,
        "security": False,
        "integrations": True,
        "features": True,
        "audit": True,
        "apps": True,
    },
    ROLES["READ_ONLY"]: {
        "system": False,
        "company": False,
        "branch": False,
        "security": False,
        "integrations": False,
        "features": False,
        "audit": True,
        "apps": False,
    },
}
