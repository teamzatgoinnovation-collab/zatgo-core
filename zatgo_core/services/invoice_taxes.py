"""The tax template an invoice created by zatgo_core posts with (Phase 9, T-01).

ERPNext computes the tax; this module only chooses the template and copies its rows onto the document, the way
Desk does when a new invoice opens. One rule for every path that creates an invoice: van sale, Retail and Resto
POS, and the accounting API.

- Sales: the company's ZatGo default template (Company Settings), else ERPNext's default for the company, else its
  only template. Several templates and no default is refused: the wrong template posts the wrong VAT.
- Purchase: ERPNext's default Purchase Taxes and Charges Template for the company, if one is marked default.
- A template that cannot be applied stops the write: nothing is recorded without the tax it asks for.
- A caller that already set a template (or tax rows) keeps them.
"""

from __future__ import annotations

from typing import Any

import frappe


def apply_sales_taxes(doc: Any, company: str) -> None:
    from zatgo_core.services.vansalex_settings import sales_tax_template

    template, inclusive = sales_tax_template(company)
    if not template:
        return
    doc.taxes_and_charges = template
    _copy_rows(doc, "Sales Taxes and Charges Template", template, inclusive=inclusive)


def apply_purchase_taxes(doc: Any, company: str) -> None:
    master = "Purchase Taxes and Charges Template"
    if not company or not frappe.db.exists("DocType", master):
        return
    template = frappe.db.get_value(master, {"company": company, "is_default": 1, "disabled": 0}, "name")
    if not template:
        return
    doc.taxes_and_charges = template
    _copy_rows(doc, master, template, inclusive=False)


def apply_if_unset(doc: Any, company: str) -> None:
    """For the accounting API: apply the company's template unless the document already has taxes."""
    if doc.get("taxes_and_charges") or doc.get("taxes"):
        return
    if doc.doctype == "Sales Invoice":
        apply_sales_taxes(doc, company)
    elif doc.doctype == "Purchase Invoice":
        apply_purchase_taxes(doc, company)


def _copy_rows(doc: Any, master: str, template: str, *, inclusive: bool) -> None:
    try:
        from zatgo_core.services.core.erpnext_api import get_taxes_and_charges

        doc.set("taxes", [])
        for tax in get_taxes_and_charges(master, template) or []:
            row = dict(tax)
            # Company prices are tax-inclusive: ERPNext must not add VAT on top of them.
            if inclusive:
                row["included_in_print_rate"] = 1
            doc.append("taxes", row)
    except Exception:
        try:
            doc.append_taxes_from_master()
            if inclusive:
                for tax in doc.taxes or []:
                    tax.included_in_print_rate = 1
        except Exception:
            frappe.log_error(title="Tax template apply failed", message=frappe.get_traceback())
            frappe.throw(f"Could not apply the tax template {template}. Nothing was recorded -- fix the template and retry.")
