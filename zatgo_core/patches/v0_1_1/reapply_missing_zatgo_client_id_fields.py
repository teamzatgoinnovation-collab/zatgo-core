"""Re-apply the zatgo_client_id / sync custom fields that four earlier
patches (add_zatgo_client_id_fields, add_customer_sync_fields,
add_item_sync_fields) recorded as run in Patch Log without the fields
actually materializing on the DB (Item, Customer, Address, Contact,
Sales Invoice, Payment Entry, Stock Entry, ZG Trip all missing them in
production). Patches are gated run-once by name, so simply fixing the
original files doesn't re-trigger on sites that already "ran" them —
this patch re-invokes them directly; create_custom_fields(update=True)
is idempotent, so it's a safe no-op anywhere the fields do exist.
"""

from __future__ import annotations

from zatgo_core.patches.v0_1_0 import (
    add_customer_sync_fields,
    add_item_sync_fields,
    add_zatgo_client_id_fields,
)


def execute() -> None:
    add_zatgo_client_id_fields.execute()
    add_customer_sync_fields.execute()
    add_item_sync_fields.execute()
