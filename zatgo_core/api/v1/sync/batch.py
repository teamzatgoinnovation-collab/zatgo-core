"""Batch sync endpoint for VanSale outbox flushes."""

from __future__ import annotations

import json
from typing import Any

import frappe

from zatgo_core.api.response import ok
from zatgo_core.api.validators import require_login
from zatgo_core.services.customer_sync_ops import sync_customer_op
from zatgo_core.services.item_sync_ops import sync_item_op


@frappe.whitelist()
def batch(operations: str | list | None = None) -> dict[str, Any]:
    """
    Process a list of sync operations.

    Each op:
      {
        "id": "local-queue-id",
        "entity_type": "customer" | "product",
        "op": "create" | "update" | "delete",
        "client_id": "...",
        "base_modified": "...",
        "force": 0,
        "payload": { ... customer/item fields ... },
        "attachments": { ... }
      }
    """
    require_login()
    if operations is None:
        ops: list[Any] = []
    elif isinstance(operations, str):
        ops = json.loads(operations)
    else:
        ops = list(operations)

    if not isinstance(ops, list):
        frappe.throw("operations must be a list")

    results: list[dict[str, Any]] = []
    for raw in ops[:50]:
        if not isinstance(raw, dict):
            results.append({"success": False, "error": "invalid_op"})
            continue
        local_id = raw.get("id")
        entity = str(raw.get("entity_type") or "").strip().lower()
        try:
            if entity == "customer":
                resp = sync_customer_op(
                    client_id=str(raw.get("client_id") or ""),
                    op=str(raw.get("op") or "create"),
                    customer=raw.get("payload") or raw.get("customer"),
                    contact=raw.get("contact"),
                    address=raw.get("address"),
                    attachments=raw.get("attachments"),
                    base_modified=raw.get("base_modified"),
                    force=raw.get("force") or 0,
                )
            elif entity in ("product", "item"):
                resp = sync_item_op(
                    client_id=str(raw.get("client_id") or ""),
                    op=str(raw.get("op") or "create"),
                    item=raw.get("payload") or raw.get("item"),
                    attachments=raw.get("attachments"),
                    base_modified=raw.get("base_modified"),
                    force=raw.get("force") or 0,
                )
            else:
                results.append(
                    {
                        "id": local_id,
                        "success": False,
                        "error": f"unsupported entity_type: {entity}",
                    }
                )
                continue

            data = resp.get("data") if isinstance(resp, dict) else None
            meta = resp.get("meta") if isinstance(resp, dict) else {}
            results.append(
                {
                    "id": local_id,
                    "success": bool(resp.get("success", True)) if isinstance(resp, dict) else True,
                    "conflict": bool((meta or {}).get("conflict")),
                    "data": data,
                    "meta": meta,
                }
            )
        except Exception as exc:
            frappe.log_error(title="VanSale batch sync op failed")
            results.append(
                {
                    "id": local_id,
                    "success": False,
                    "error": str(exc),
                }
            )

    uploaded = sum(1 for r in results if r.get("success") and not r.get("conflict"))
    conflicts = sum(1 for r in results if r.get("conflict"))
    failed = sum(1 for r in results if not r.get("success"))
    return ok(
        {"results": results},
        meta={
            "stub": False,
            "uploaded": uploaded,
            "conflicts": conflicts,
            "failed": failed,
            "total": len(results),
        },
    )
