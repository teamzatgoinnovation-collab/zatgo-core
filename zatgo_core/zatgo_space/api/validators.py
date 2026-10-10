"""Shared API helpers: pagination caps, filter allow-lists, permission guards."""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _


DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def parse_pagination(
    page: int | str | None = 1,
    page_size: int | str | None = DEFAULT_PAGE_SIZE,
) -> tuple[int, int, int]:
    """Return (page, page_size, start) with hard caps."""
    try:
        page_i = max(int(page or 1), 1)
        size_i = int(page_size or DEFAULT_PAGE_SIZE)
    except (TypeError, ValueError) as exc:
        raise frappe.ValidationError(_("Invalid pagination parameters")) from exc

    size_i = max(1, min(size_i, MAX_PAGE_SIZE))
    start = (page_i - 1) * size_i
    return page_i, size_i, start


def require_login() -> None:
    """Ensure the session is authenticated."""
    if frappe.session.user == "Guest":
        raise frappe.PermissionError(_("Authentication required"))


def require_doc_permission(doctype: str, ptype: str = "read", doc: str | None = None) -> None:
    """Raise if the current user lacks DocType permission."""
    if not frappe.has_permission(doctype, ptype=ptype, doc=doc):
        raise frappe.PermissionError(_("Not permitted"))


def whitelist_filters(
    raw: dict[str, Any] | None,
    allowed_fields: set[str],
) -> dict[str, Any]:
    """Keep only allow-listed filter keys."""
    if not raw:
        return {}
    unknown = set(raw) - allowed_fields
    if unknown:
        raise frappe.ValidationError(_("Unsupported filter fields: {0}").format(", ".join(sorted(unknown))))
    return {k: v for k, v in raw.items() if v is not None and v != ""}
