"""Shared idempotency helpers for zatgo_client_id-keyed document creation.

`zatgo_client_id` carries a DB-level UNIQUE constraint (see
patches.v0_1_0.add_zatgo_client_id_fields), so two concurrent requests with
the same client_id can each pass a pre-insert existence check but only one
of their `insert()` calls can actually succeed — the loser hits a MariaDB
duplicate-key error, which Frappe surfaces as `frappe.UniqueValidationError`.
Callers must not let that become a raw error response to the client: the
correct idempotent behavior is to roll back, look up the document the
winner just created, and return the same acknowledgement as if this request
had found it on the pre-check instead of racing into the insert.
"""

from __future__ import annotations

import frappe


def find_by_client_id(doctype: str, client_id: str) -> str | None:
    if not client_id or not frappe.db.exists("DocType", doctype):
        return None
    if not frappe.db.has_column(doctype, "zatgo_client_id"):
        return None
    return frappe.db.get_value(doctype, {"zatgo_client_id": client_id}, "name")


def insert_idempotent(doc, *, doctype: str, client_id: str):
    """Insert `doc`, recovering cleanly from a concurrent duplicate client_id.

    Returns `(doc, created)`. `created` is False when a concurrent request
    won the race — `doc` is then the document *that* request created,
    fetched fresh, so the caller can treat this exactly like its ordinary
    "already exists" pre-check branch instead of a failure.
    """
    try:
        doc.insert()
        return doc, True
    except frappe.UniqueValidationError:
        frappe.db.rollback()
        existing_name = find_by_client_id(doctype, client_id)
        if not existing_name:
            # Some other unique field collided, or the winner's insert
            # hasn't become visible yet — don't mask that as "idempotent
            # success", let the original error surface.
            raise
        return frappe.get_doc(doctype, existing_name), False
