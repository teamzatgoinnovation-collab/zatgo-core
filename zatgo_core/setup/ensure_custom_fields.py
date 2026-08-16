"""Guarantee zatgo_core's custom fields exist, independent of Patch Log.

Root cause (confirmed by direct reproduction on a fresh site, not just
inferred from production history): `bench install-app zatgo_core`'s
bundled patch-execution step can mark a `[post_model_sync]` patch as done
in Patch Log without its `create_custom_fields(...)` call actually
persisting — calling the exact same `execute()` function directly
afterward (e.g. from `bench console`, or from here) creates the fields
correctly. Because patches are gated run-once-by-name, a site that hit
this once can never re-trigger the patch by fixing the patch file alone
(see the two now-superseded "reapply_*" patches this replaces).

`after_install()` / `after_migrate()` app hooks are not patch-log-gated —
they run unconditionally on every install and every migrate — so calling
these idempotent field-creation functions from there guarantees the
fields exist regardless of whatever is going wrong in the patch runner.
"""

from __future__ import annotations

from zatgo_core.utils.logging import get_logger

logger = get_logger("system")


def ensure_custom_fields() -> None:
    """Idempotently (re-)create every custom field zatgo_core depends on.

    Each field group is independent and wrapped separately so one failure
    (e.g. a DocType not yet installed) doesn't block the others.
    """
    _run("zatgo_client_id fields", _ensure_zatgo_client_id_fields)
    _run("customer sync fields", _ensure_customer_sync_fields)
    _run("item sync fields", _ensure_item_sync_fields)
    _run("zatca_qr_base64 field", _ensure_zatca_qr_field)
    _run("accounting client_id fields", _ensure_accounting_client_id_fields)


def _run(label: str, fn) -> None:
    try:
        fn()
    except Exception:
        logger.exception("ensure_custom_fields: %s failed", label)


def _ensure_zatgo_client_id_fields() -> None:
    from zatgo_core.patches.v0_1_0.add_zatgo_client_id_fields import execute

    execute()


def _ensure_customer_sync_fields() -> None:
    from zatgo_core.patches.v0_1_0.add_customer_sync_fields import execute

    execute()


def _ensure_item_sync_fields() -> None:
    from zatgo_core.patches.v0_1_0.add_item_sync_fields import execute

    execute()


def _ensure_zatca_qr_field() -> None:
    from zatgo_core.patches.v0_1_0.add_zatca_qr_field import execute

    execute()


def _ensure_accounting_client_id_fields() -> None:
    from zatgo_core.patches.v0_1_3.add_accounting_client_id_fields import execute

    execute()
