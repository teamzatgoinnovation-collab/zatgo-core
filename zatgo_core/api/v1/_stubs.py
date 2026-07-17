"""Shared stub helpers for product API packages."""

from __future__ import annotations

from typing import Any

from zatgo_core.api.response import ok, paginated
from zatgo_core.api.validators import parse_pagination, require_login


def stub_status(product: str, title: str, *, domain: str | None = None) -> dict[str, Any]:
    """Authenticated health/status payload for a product namespace."""
    require_login()
    return ok(
        {
            "product": product,
            "title": title,
            "ready": False,
            "stub": True,
            "message": (
                f"{title} API namespace is registered. Domain DocTypes and CRUD "
                "are not implemented yet; clients may wire method paths now."
            ),
            "domain": domain,
        },
        meta={"stub": True},
    )


def stub_list(
    product: str,
    resource: str,
    *,
    page: int | str = 1,
    page_size: int | str = 20,
) -> dict[str, Any]:
    """Empty paginated list for clients to wire against."""
    require_login()
    page_i, size_i, _start = parse_pagination(page, page_size)
    payload = paginated([], page=page_i, page_size=size_i, total=0, sort="modified desc")
    payload["meta"] = {
        **payload.get("meta", {}),
        "stub": True,
        "product": product,
        "resource": resource,
    }
    return payload


def stub_get(product: str, resource: str, name: str) -> dict[str, Any]:
    """Stub get — resource not implemented yet."""
    require_login()
    return ok(
        None,
        meta={
            "stub": True,
            "product": product,
            "resource": resource,
            "name": name,
            "message": f"{resource} CRUD is not implemented yet",
        },
    )
