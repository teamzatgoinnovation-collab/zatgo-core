"""MyBis -- global search and record summaries. Permission-aware: ERPNext permissions apply to every hit."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.api.response import ok
from zatgo_core.api.validators import require_login
from zatgo_core.services import row_scope
from zatgo_core.services.mybis import search as search_service


@frappe.whitelist(methods=["GET", "POST"])
def query(q: str, types: Any = None, limit: int | str = 5, company: str | None = None) -> dict[str, Any]:
    """Customers, suppliers, items, invoices, payments, employees and warehouses matching `q` (at least 2 characters)."""
    require_login()
    kinds = None
    if isinstance(types, str) and types:
        kinds = [t for t in types.replace("[", "").replace("]", "").replace('"', "").split(",") if t.strip()]
        kinds = [t.strip() for t in kinds]
    elif isinstance(types, (list, tuple)):
        kinds = list(types)
    if company:
        row_scope.require_company(company)
    return ok(search_service.search(q, kinds, int(limit), company))


@frappe.whitelist(methods=["GET", "POST"])
def record(type: str, name: str) -> dict[str, Any]:
    """Key facts of a payment entry, employee or warehouse (the hits that have no screen of their own)."""
    require_login()
    return ok(search_service.record(type, name))
