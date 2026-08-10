"""Re-apply add_zatca_qr_field — same run-once-by-name gap as the fields
fixed in v0_1_1.reapply_missing_zatgo_client_id_fields: Patch Log shows
add_zatca_qr_field as already run, but zatca_qr_base64 was never actually
materialized on Sales Invoice in production or the local dev bench, so
every invoice print silently rendered without its ZATCA QR code.
"""

from __future__ import annotations

from zatgo_core.patches.v0_1_0 import add_zatca_qr_field


def execute() -> None:
    add_zatca_qr_field.execute()
