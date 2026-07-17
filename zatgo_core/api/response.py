"""Standard API response envelope for ZatGo Core."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import frappe


def ok(
    data: Any = None,
    *,
    meta: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Build a successful API response."""
    return {
        "success": True,
        "data": data,
        "meta": meta or {},
        "error": None,
        "request_id": request_id or str(uuid4()),
    }


def fail(
    code: str,
    message: str,
    *,
    details: Any = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Build a failed API response."""
    frappe.logger("zatgo_core.api").warning(
        "API failure code=%s message=%s details=%s", code, message, details
    )
    return {
        "success": False,
        "data": None,
        "meta": {},
        "error": {"code": code, "message": message, "details": details},
        "request_id": request_id or str(uuid4()),
    }


def paginated(
    rows: list[Any],
    *,
    page: int,
    page_size: int,
    total: int,
    sort: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Wrap list results with pagination meta."""
    return ok(
        rows,
        meta={
            "page": page,
            "page_size": page_size,
            "total": total,
            "sort": sort or "modified desc",
        },
        request_id=request_id,
    )
