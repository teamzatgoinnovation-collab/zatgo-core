"""Shared API helpers: pagination, auth guards, JSON parsing."""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _


DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def require_str(value: Any, field: str) -> str:
    if not value or not str(value).strip():
        frappe.throw(_("{0} is required").format(field))
    return str(value).strip()


def parse_json_dict(value: Any, field: str = "values") -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        import json

        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            frappe.throw(_("Invalid JSON for {0}: {1}").format(field, exc))
        if not isinstance(parsed, dict):
            frappe.throw(_("{0} must be a JSON object").format(field))
        return parsed
    frappe.throw(_("{0} must be a dict or JSON string").format(field))


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


def require_doc_permission(
    doctype: str, ptype: str = "read", doc: str | None = None
) -> None:
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
        raise frappe.ValidationError(
            _("Unsupported filter fields: {0}").format(", ".join(sorted(unknown)))
        )
    return {k: v for k, v in raw.items() if v is not None and v != ""}
