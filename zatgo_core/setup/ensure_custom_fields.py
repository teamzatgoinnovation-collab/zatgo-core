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
    # Must precede the generic client_id pass: it dedupes ZG Trip rows that
    # would otherwise make the (now UNIQUE) zatgo_client_id index unbuildable.
    _run("ZG Trip client_id uniqueness", _ensure_zg_trip_client_id_unique)
    _run("zatgo_client_id fields", _ensure_zatgo_client_id_fields)
    _run("customer sync fields", _ensure_customer_sync_fields)
    _run("item sync fields", _ensure_item_sync_fields)
    _run("zatca_qr_base64 field", _ensure_zatca_qr_field)
    _run("accounting client_id fields", _ensure_accounting_client_id_fields)
    _run("quotation item type field", _ensure_quotation_item_type_field)
    _run("company bank fields", _ensure_company_bank_fields)
    _run("print computed fields", _ensure_print_computed_fields)
    _run("payment type field", _ensure_payment_type_field)
    _run("cash account field", _ensure_cash_account_field)
    _run("bank payment fields", _ensure_bank_payment_fields)
    _run("payment entry balance field", _ensure_payment_entry_balance_field)
    _run("print count field", _ensure_print_count_field)
    _run("purchase invoice payment type field", _ensure_purchase_invoice_payment_type_field)
    _run("purchase invoice cash account field", _ensure_purchase_invoice_cash_account_field)
    _run("purchase invoice bank payment fields", _ensure_purchase_invoice_bank_payment_fields)
    _run("purchase order client_id field", _ensure_purchase_order_client_id_field)
    _run("multi payment fields", _ensure_multi_payment_fields)
    _run("narration fields", _ensure_narration_fields)
    _run("supplier cr number field", _ensure_supplier_cr_number_field)
    _run("supplier arabic name field", _ensure_supplier_name_arabic_field)
    _run("hide duplicate customer arabic name", _ensure_duplicate_customer_arabic_name_hidden)
    _run("warehouse selectable field", _ensure_warehouse_selectable_field)
    _run("warehouse transfer point field", _ensure_warehouse_transfer_point_field)


def _run(label: str, fn) -> None:
    try:
        fn()
    except Exception:
        logger.exception("ensure_custom_fields: %s failed", label)


def _ensure_zg_trip_client_id_unique() -> None:
    from zatgo_core.patches.v0_2_0.make_zg_trip_client_id_unique import execute

    execute()


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


def _ensure_quotation_item_type_field() -> None:
    from zatgo_core.patches.v0_2_0.add_quotation_item_type_field import execute

    execute()


def _ensure_company_bank_fields() -> None:
    from zatgo_core.patches.v0_2_1.add_company_bank_fields import execute

    execute()


def _ensure_print_computed_fields() -> None:
    from zatgo_core.patches.v0_2_1.add_print_computed_fields import execute

    execute()


def _ensure_payment_type_field() -> None:
    from zatgo_core.patches.v0_2_2.add_payment_type_field import execute

    execute()


def _ensure_warehouse_selectable_field() -> None:
    from zatgo_core.patches.v0_4_1.add_warehouse_selectable_field import execute

    execute()


def _ensure_warehouse_transfer_point_field() -> None:
    from zatgo_core.patches.v0_4_8.add_warehouse_transfer_point_field import execute

    execute()


def _ensure_cash_account_field() -> None:
    from zatgo_core.patches.v0_2_2.add_cash_account_field import execute

    execute()


def _ensure_bank_payment_fields() -> None:
    from zatgo_core.patches.v0_2_7.add_bank_payment_fields import execute

    execute()


def _ensure_payment_entry_balance_field() -> None:
    from zatgo_core.patches.v0_2_2.add_payment_entry_balance_field import execute

    execute()


def _ensure_print_count_field() -> None:
    from zatgo_core.patches.v0_2_2.add_print_count_field import execute

    execute()


def _ensure_purchase_invoice_payment_type_field() -> None:
    from zatgo_core.patches.v0_2_3.add_purchase_invoice_payment_type_field import execute

    execute()


def _ensure_purchase_invoice_cash_account_field() -> None:
    from zatgo_core.patches.v0_2_3.add_purchase_invoice_cash_account_field import execute

    execute()


def _ensure_purchase_invoice_bank_payment_fields() -> None:
    from zatgo_core.patches.v0_2_8.add_purchase_invoice_bank_payment_fields import execute

    execute()


def _ensure_purchase_order_client_id_field() -> None:
    from zatgo_core.patches.v0_3_0.add_purchase_order_client_id import execute

    execute()


def _ensure_supplier_cr_number_field() -> None:
    from zatgo_core.patches.v0_3_1.add_supplier_cr_number import execute

    execute()


def _ensure_supplier_name_arabic_field() -> None:
    from zatgo_core.patches.v0_4_2.add_supplier_name_arabic import execute

    execute()


def _ensure_duplicate_customer_arabic_name_hidden() -> None:
    """zatca_erpgulf's fixture adds a second "Customer Name Arabic" field
    (zatca_customer_name_in_arabic) beside ours (zatgo_customer_name_ar).
    Ours feeds the customer sync API; the ZATCA one is never read for
    customers. Hide it with a Property Setter, which (unlike editing the
    Custom Field) survives that app's fixture re-sync on every migrate."""
    import frappe
    from frappe.custom.doctype.property_setter.property_setter import make_property_setter

    if not frappe.db.has_column("Customer", "zatca_customer_name_in_arabic"):
        return
    make_property_setter(
        "Customer", "zatca_customer_name_in_arabic", "hidden", 1, "Check", validate_fields_for_doctype=False
    )
    frappe.db.commit()


def _ensure_multi_payment_fields() -> None:
    from zatgo_core.patches.v0_2_4.add_multi_payment_fields import execute

    execute()


def _ensure_narration_fields() -> None:
    from zatgo_core.patches.v0_2_5.add_narration_fields import execute

    execute()
