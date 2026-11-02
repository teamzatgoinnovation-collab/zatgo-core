"""Seeded duplicate rules for the supported DocTypes (patches/v0_5_0/seed_duplicate_rules.py).

`seed_defaults` only creates rules that do not exist yet, and only with fields the DocType really has --
a rule an administrator edited or deleted-and-recreated is never touched again."""

from __future__ import annotations

import frappe

from zatgo_core.services.duplicate.config import RULE

# (fieldname, kind, match_role, source, child_table, group)
U, N, S = "Unique Identifier", "Name", "Shared"
D, C, L = "Document", "Child Table", "Linked Contact"


def _f(fieldname, kind, role, source=D, child_table="", group=""):
    return {"fieldname": fieldname, "kind": kind, "match_role": role, "source": source, "child_table": child_table, "match_group": group}


DEFAULT_RULES: dict[str, dict] = {
    # Same item name = refused too (two "test item"s with different groups were being saved): possible matches block.
    "Item": {"display": "item_code,item_group,stock_uom", "possible": "Block", "fields": [
        _f("item_code", "Code", U), _f("item_name", "Name", N), _f("barcode", "Code", U, C, "barcodes"),
        _f("supplier_part_no", "Code", S, C, "supplier_items"), _f("default_manufacturer_part_no", "Code", S)]},
    "Customer": {"display": "customer_group,territory,tax_id,mobile_no,email_id", "fields": [
        _f("customer_name", "Name", N), _f("tax_id", "Tax ID", U), _f("zatgo_cr_number", "Tax ID", U),
        _f("mobile_no", "Phone", S, L), _f("email_id", "Email", S, L)]},
    "Supplier": {"display": "supplier_group,tax_id,mobile_no,email_id", "fields": [
        _f("supplier_name", "Name", N), _f("tax_id", "Tax ID", U), _f("zatgo_cr_number", "Tax ID", U),
        _f("mobile_no", "Phone", S, L), _f("email_id", "Email", S, L)]},
    "Employee": {"display": "department,designation", "fields": [
        _f("employee_number", "Code", U), _f("user_id", "Email", U), _f("company_email", "Email", U),
        _f("employee_name", "Name", N), _f("cell_number", "Phone", S), _f("personal_email", "Email", S)]},
    # Contacts are shared by design (one person, several parties; ERPNext and the sync API both create them): warn only.
    "Contact": {"display": "email_id,mobile_no,company_name", "strong": "Warn", "fields": [
        _f("email_id", "Email", S, C, "email_ids"), _f("phone", "Phone", S, C, "phone_nos"), _f("mobile_no", "Phone", S),
        _f("first_name", "Name", N, group="full_name"), _f("last_name", "Name", N, group="full_name")]},
    "Address": {"display": "city,country", "fields": [
        _f("address_line1", "Text", N, group="address"), _f("city", "Text", N, group="address"), _f("pincode", "Code", N, group="address")]},
    "Warehouse": {"display": "company,warehouse_type", "fields": [_f("warehouse_name", "Name", N)]},
    "Account": {"display": "company,root_type,account_number", "fields": [
        _f("account_number", "Code", U, group="number"), _f("company", "Code", U, group="number"),
        _f("account_name", "Name", N, group="account_name"), _f("company", "Code", N, group="account_name")]},
    "UOM": {"display": "symbol", "fields": [_f("uom_name", "Name", N)]},
    "Brand": {"display": "", "fields": [_f("brand", "Name", N)]},
    "Manufacturer": {"display": "full_name", "fields": [_f("short_name", "Name", N), _f("full_name", "Name", N)]},
    "Sales Partner": {"display": "territory,partner_type", "fields": [_f("partner_name", "Name", N), _f("referral_code", "Code", U)]},
    "Territory": {"display": "parent_territory", "fields": [_f("territory_name", "Name", N)]},
    "Lead": {"display": "company_name,email_id,mobile_no", "fields": [
        _f("lead_name", "Name", N), _f("email_id", "Email", S), _f("mobile_no", "Phone", S)]},
    "Opportunity": {"display": "opportunity_from,party_name,status", "possible": "Warn", "fields": [
        _f("title", "Text", N, group="opportunity"), _f("party_name", "Text", N, group="opportunity")]},
    "Purchase Invoice": {"type": "Transaction", "display": "supplier,bill_no,bill_date,grand_total", "live": 1, "fields": [
        _f("bill_no", "Code", U, group="supplier_bill"), _f("supplier", "Code", U, group="supplier_bill")]},
    "Sales Invoice": {"type": "Transaction", "display": "customer,po_no,grand_total", "strong": "Warn", "live": 1, "fields": [
        _f("po_no", "Code", N, group="customer_po"), _f("customer", "Code", N, group="customer_po")]},
}


def _usable(meta, row: dict) -> bool:
    if row["source"] == "Child Table":
        table = meta.get_field(row["child_table"])
        return bool(table and frappe.get_meta(table.options).has_field(row["fieldname"]))
    return meta.has_field(row["fieldname"])


def seed_defaults() -> list[str]:
    """Create the missing default rules. Returns the DocTypes seeded."""
    created: list[str] = []
    for doctype, spec in DEFAULT_RULES.items():
        if frappe.db.exists(RULE, doctype) or not frappe.db.exists("DocType", doctype):
            continue
        meta = frappe.get_meta(doctype)
        rows = [r for r in spec["fields"] if _usable(meta, r)]
        if not rows:
            continue
        display = ",".join(f for f in spec["display"].split(",") if f and meta.has_field(f))
        frappe.get_doc({
            "doctype": RULE,
            "ref_doctype": doctype,
            "enabled": 1,
            "rule_type": spec.get("type", "Master"),
            "live_lookup": spec.get("live", 1),
            "strong_action": spec.get("strong", "Block"),
            "possible_action": spec.get("possible", "Warn"),
            "display_fields": display,
            "fields": rows,
        }).insert(ignore_permissions=True)
        created.append(doctype)
    return created
