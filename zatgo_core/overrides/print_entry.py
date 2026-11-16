"""Desk print entry points, wrapped for user-wise Sales Invoice print formats.

Frappe's print view loads HTML through `get_html_and_style` and the PDF button
through `download_pdf`. Both are replaced (hooks.py override_whitelisted_methods)
by thin wrappers that, for Sales Invoices only, ask
services/sales_invoice_print.resolve_print_format which format to use and
refuse a restricted user's other choices. Everything else is delegated
unchanged to Frappe.
"""

from __future__ import annotations

import frappe
from frappe.utils.print_format import download_pdf as _download_pdf
from frappe.www.printview import get_html_and_style as _get_html_and_style

from zatgo_core.services.sales_invoice_print import resolve_print_format



def _format_for(doctype: str, name: str | None, requested: str | None) -> str | None:
    if doctype != "Sales Invoice" or not isinstance(name, str) or not name:
        return requested
    company = frappe.db.get_value("Sales Invoice", name, "company")
    return resolve_print_format(frappe.session.user, company, requested) or requested


# Signatures mirror Frappe's: whitelisted calls pass only the arguments the
# function declares, so these must declare the same ones.
@frappe.whitelist()
def get_html_and_style(
    doc,
    name=None,
    print_format=None,
    no_letterhead=None,
    letterhead=None,
    trigger_print=False,
    style=None,
    settings=None,
):
    return _get_html_and_style(
        doc,
        name=name,
        print_format=_format_for(doc, name, print_format),
        no_letterhead=no_letterhead,
        letterhead=letterhead,
        trigger_print=trigger_print,
        style=style,
        settings=settings,
    )


@frappe.whitelist(allow_guest=True)
def download_pdf(
    doctype,
    name,
    format=None,
    doc=None,
    no_letterhead=0,
    language=None,
    letterhead=None,
    pdf_generator=None,
):
    return _download_pdf(
        doctype,
        name,
        format=_format_for(doctype, name, format),
        doc=doc,
        no_letterhead=no_letterhead,
        language=language,
        letterhead=letterhead,
        pdf_generator=pdf_generator,
    )
