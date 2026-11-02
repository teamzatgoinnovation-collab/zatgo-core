"""Indexes on the columns Duplicate Prevention looks up by (tax / registration numbers, phone, e-mail, barcode).
Additive and idempotent; each is checked against information_schema afterwards (patch-log alone proves nothing)."""

import frappe

# (DocType, column) -- only columns that exist; ERPNext's own indexed columns are skipped.
INDEXES = (
    ("Customer", "tax_id"), ("Customer", "zatgo_cr_number"), ("Customer", "mobile_no"), ("Customer", "email_id"),
    ("Supplier", "tax_id"), ("Supplier", "zatgo_cr_number"), ("Supplier", "mobile_no"), ("Supplier", "email_id"),
    ("Employee", "cell_number"), ("Employee", "personal_email"), ("Employee", "company_email"),
    ("Lead", "email_id"), ("Lead", "mobile_no"), ("Contact", "mobile_no"),
    ("Item Barcode", "barcode"), ("Item", "item_name"), ("Contact Email", "email_id"), ("Contact Phone", "phone"),
    ("Purchase Invoice", "bill_no"), ("Sales Invoice", "po_no"),
)


def _indexed(table: str, column: str) -> bool:
    return bool(frappe.db.sql(
        "select 1 from information_schema.statistics where table_schema = database() and table_name = %s "
        "and column_name = %s and seq_in_index = 1 limit 1", (table, column)))


def execute() -> None:
    for doctype, column in INDEXES:
        if not frappe.db.exists("DocType", doctype) or not frappe.db.has_column(doctype, column):
            continue
        table = f"tab{doctype}"
        if _indexed(table, column):
            continue
        frappe.db.add_index(doctype, [column], index_name=f"zg_dup_{column}"[:60])
