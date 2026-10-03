"""Multi-method / multi-account payment allocation fields.

- Mode of Payment `custom_zg_accounts` (ZG Mode of Payment Account): every
  ledger account a payment method may post to, per company. The native
  Mode of Payment Account table allows exactly one account per company.
- Sales Invoice Payment `custom_remarks`: per-row note. The rest of a Sales
  Invoice's payment rows (mode, account, amount, reference) are ERPNext's
  own `payments` table, posted by ERPNext's own make_pos_gl_entries().
- Payment Entry `custom_payment_details` (ZG Payment Allocation): where a
  Payment Entry's money actually went, split across accounts. Posted by
  zatgo_core.overrides.payment_entry.

See zatgo_core.services.payment_allocation for the rules.
"""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter


def execute() -> None:
    for doctype in ("ZG Mode of Payment Account", "ZG Payment Allocation"):
        if not frappe.db.exists("DocType", doctype):
            frappe.reload_doc("zatgo_core", "doctype", frappe.scrub(doctype))

    create_custom_fields(
        {
            "Mode of Payment": [
                {
                    "fieldname": "custom_zg_accounts_section",
                    "label": "Allowed Accounts",
                    "fieldtype": "Section Break",
                    "insert_after": "accounts",
                    "description": (
                        "Every ledger account this payment method may receive into / pay "
                        "from, per company. The Default row is pre-filled on new payment "
                        "rows. When a company has no rows here, only the Default Account "
                        "above is allowed."
                    ),
                },
                {
                    "fieldname": "custom_zg_accounts",
                    "label": "Allowed Accounts",
                    "fieldtype": "Table",
                    "options": "ZG Mode of Payment Account",
                    "insert_after": "custom_zg_accounts_section",
                },
            ],
            "Sales Invoice Payment": [
                {
                    "fieldname": "custom_remarks",
                    "label": "Remarks",
                    "fieldtype": "Small Text",
                    "insert_after": "reference_no",
                },
            ],
            "Payment Entry": [
                {
                    "fieldname": "custom_payment_details_section",
                    "label": "Payment Details",
                    "fieldtype": "Section Break",
                    "insert_after": "paid_to_account_currency",
                    "depends_on": "eval:doc.payment_type != 'Internal Transfer'",
                    "description": (
                        "Optional: split the money across several payment methods / "
                        "accounts. When rows are present they replace the single "
                        "Account Paid To (Receive) / Account Paid From (Pay) posting."
                    ),
                },
                {
                    "fieldname": "custom_payment_details",
                    "label": "Payment Details",
                    "fieldtype": "Table",
                    "options": "ZG Payment Allocation",
                    "insert_after": "custom_payment_details_section",
                    "depends_on": "eval:doc.payment_type != 'Internal Transfer'",
                },
            ],
        },
        update=True,
    )
    # Show which ledger each Sales Invoice payment row goes to right in the
    # grid -- with several accounts per method, the method alone is ambiguous.
    for fieldname in ("account", "reference_no"):
        make_property_setter(
            "Sales Invoice Payment", fieldname, "in_list_view", 1, "Check", validate_fields_for_doctype=False
        )
    frappe.db.commit()
