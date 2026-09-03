"""Give ZG Trip.zatgo_client_id the DB-level UNIQUE constraint it was
missing.

`v0_1_0.add_zatgo_client_id_fields` declared this one field with
`unique: 0` while every other doctype in the same patch got `unique: 1`.
That was harmless while ZG Trip was read-only to the client, but the
mobile app now *creates* stops with a client-generated id, and
`services/idempotency.py::insert_idempotent` is explicitly built on the
constraint existing: without it, two concurrent creates can both pass the
pre-insert existence check and both insert, which is the duplicate-row
race `.claude/rules/accounting.md` forbids.

Two cleanups are needed before the index can be added on an existing site:

1. `services/vansalex_service.py::update_visit` used to stamp the *visit's*
   client_id onto this field on every status change, so the same value can
   legitimately appear on several rows (and a trip's own create id may have
   been overwritten). Those values carry no idempotency meaning any more —
   duplicates are nulled out, keeping the oldest row's value.
2. The Custom Field doc itself has to be re-saved with `unique: 1`, and the
   resulting index verified directly against information_schema rather than
   trusted — see this app's CLAUDE.md on patches that record as run without
   materializing.
"""

from __future__ import annotations

import frappe

from zatgo_core.utils.logging import get_logger

logger = get_logger("system")

INDEX_NAME = "zatgo_client_id"
TABLE = "tabZG Trip"


def execute() -> None:
    if not frappe.db.exists("DocType", "ZG Trip"):
        return
    if not frappe.db.has_column("ZG Trip", "zatgo_client_id"):
        # Field itself never materialized; add_zatgo_client_id_fields (now
        # declaring unique: 1) will create it correctly, including the index.
        from zatgo_core.patches.v0_1_0.add_zatgo_client_id_fields import execute as add_fields

        add_fields()
        return

    _null_out_duplicates()
    _reapply_field_definition()
    _ensure_unique_index()
    frappe.db.commit()


def _null_out_duplicates() -> None:
    """Keep the oldest row's client id per value, blank the rest."""
    dupes = frappe.db.sql(
        """
        SELECT zatgo_client_id
        FROM `tabZG Trip`
        WHERE zatgo_client_id IS NOT NULL AND zatgo_client_id != ''
        GROUP BY zatgo_client_id
        HAVING COUNT(*) > 1
        """,
        as_dict=True,
    )
    for row in dupes:
        cid = row["zatgo_client_id"]
        names = frappe.get_all(
            "ZG Trip",
            filters={"zatgo_client_id": cid},
            fields=["name"],
            order_by="creation asc",
            pluck="name",
        )
        for name in names[1:]:
            frappe.db.set_value("ZG Trip", name, "zatgo_client_id", None, update_modified=False)
        logger.info(
            "make_zg_trip_client_id_unique: cleared %s duplicate client_id(s) for %s",
            len(names) - 1,
            cid,
        )


def _reapply_field_definition() -> None:
    from zatgo_core.patches.v0_1_0.add_zatgo_client_id_fields import execute as add_fields

    add_fields()


def _unique_index_exists() -> bool:
    rows = frappe.db.sql(
        """
        SELECT INDEX_NAME
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND COLUMN_NAME = 'zatgo_client_id'
          AND NON_UNIQUE = 0
        """,
        (TABLE,),
        as_dict=True,
    )
    return bool(rows)


def _ensure_unique_index() -> None:
    """create_custom_fields alone does not reliably alter the live table."""
    if _unique_index_exists():
        return
    try:
        frappe.db.add_unique("ZG Trip", ["zatgo_client_id"], constraint_name=INDEX_NAME)
    except Exception:
        logger.exception("make_zg_trip_client_id_unique: add_unique failed")

    if not _unique_index_exists():
        raise frappe.ValidationError(
            "ZG Trip.zatgo_client_id UNIQUE index was not created — "
            "idempotent trip creation is unsafe until it exists."
        )
