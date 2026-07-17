"""Enterprise roles for ZatGo Core."""

from __future__ import annotations

ROLES = {
    "SYSTEM_MANAGER": "System Manager",
    "ADMINISTRATOR": "Administrator",
    "COMPANY_ADMIN": "ZG Company Admin",
    "BRANCH_ADMIN": "ZG Branch Admin",
    "APPLICATION_ADMIN": "ZG Application Admin",
    "READ_ONLY": "ZG Read Only",
    "DELIVERY": "Delivery",
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
