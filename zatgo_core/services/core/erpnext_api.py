"""Every call zatgo_core makes into ERPNext internals, in one place.

These functions are not a public ERPNext API: a minor release can rename one or change its arguments. Calling
them only from here means an upgrade is checked and fixed in one file, and
tests/unit/test_erpnext_api.py fails when a target disappears or stops accepting the keyword arguments our
callers pass.

Each wrapper imports its target when it is called, never at import time. So importing this module costs nothing,
and a test that patches the ERPNext function itself (`erpnext.controllers.accounts_controller.get_taxes_and_charges`)
still takes effect. ERPNext classes that we extend (`extend_doctype_class`) are not wrapped here.
"""

from __future__ import annotations

import importlib
from typing import Any

# wrapper name -> "module path:function name"
TARGETS: dict[str, str] = {
    "get_payment_entry": "erpnext.accounts.doctype.payment_entry.payment_entry:get_payment_entry",
    "get_party_details": "erpnext.accounts.doctype.payment_entry.payment_entry:get_party_details",
    "get_reference_details": "erpnext.accounts.doctype.payment_entry.payment_entry:get_reference_details",
    "get_payment_entry_bank_cash_account": "erpnext.accounts.doctype.payment_entry.payment_entry:get_bank_cash_account",
    "get_sales_invoice_bank_cash_account": "erpnext.accounts.doctype.sales_invoice.sales_invoice:get_bank_cash_account",
    "make_return_doc": "erpnext.controllers.sales_and_purchase_return:make_return_doc",
    "get_taxes_and_charges": "erpnext.controllers.accounts_controller:get_taxes_and_charges",
    "get_balance_on": "erpnext.accounts.utils:get_balance_on",
    "get_fiscal_year": "erpnext.accounts.utils:get_fiscal_year",
    "make_sales_invoice_from_quotation": "erpnext.selling.doctype.quotation.quotation:make_sales_invoice",
    "make_sales_invoice_from_sales_order": "erpnext.selling.doctype.sales_order.sales_order:make_sales_invoice",
    "get_mapped_purchase_invoice": "erpnext.buying.doctype.purchase_order.purchase_order:get_mapped_purchase_invoice",
    "get_credit_limit": "erpnext.selling.doctype.customer.customer:get_credit_limit",
    "get_customer_outstanding": "erpnext.selling.doctype.customer.customer:get_customer_outstanding",
    "get_customers_suppliers": "erpnext.controllers.website_list_for_contact:get_customers_suppliers",
    "make_closing_entry_from_opening": "erpnext.accounts.doctype.pos_closing_entry.pos_closing_entry:make_closing_entry_from_opening",
}


def target(name: str) -> Any:
    """The ERPNext function behind wrapper `name` (imported now)."""
    module, attr = TARGETS[name].split(":")
    return getattr(importlib.import_module(module), attr)


def _call(name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    return target(name)(*args, **kwargs)


def get_payment_entry(*args: Any, **kwargs: Any) -> Any:
    return _call("get_payment_entry", args, kwargs)


def get_party_details(*args: Any, **kwargs: Any) -> Any:
    return _call("get_party_details", args, kwargs)


def get_reference_details(*args: Any, **kwargs: Any) -> Any:
    return _call("get_reference_details", args, kwargs)


def get_payment_entry_bank_cash_account(*args: Any, **kwargs: Any) -> Any:
    return _call("get_payment_entry_bank_cash_account", args, kwargs)


def get_sales_invoice_bank_cash_account(*args: Any, **kwargs: Any) -> Any:
    return _call("get_sales_invoice_bank_cash_account", args, kwargs)


def make_return_doc(*args: Any, **kwargs: Any) -> Any:
    return _call("make_return_doc", args, kwargs)


def get_taxes_and_charges(*args: Any, **kwargs: Any) -> Any:
    return _call("get_taxes_and_charges", args, kwargs)


def get_balance_on(*args: Any, **kwargs: Any) -> Any:
    return _call("get_balance_on", args, kwargs)


def get_fiscal_year(*args: Any, **kwargs: Any) -> Any:
    return _call("get_fiscal_year", args, kwargs)


def make_sales_invoice_from_quotation(*args: Any, **kwargs: Any) -> Any:
    return _call("make_sales_invoice_from_quotation", args, kwargs)


def make_sales_invoice_from_sales_order(*args: Any, **kwargs: Any) -> Any:
    return _call("make_sales_invoice_from_sales_order", args, kwargs)


def get_mapped_purchase_invoice(*args: Any, **kwargs: Any) -> Any:
    return _call("get_mapped_purchase_invoice", args, kwargs)


def get_credit_limit(*args: Any, **kwargs: Any) -> Any:
    return _call("get_credit_limit", args, kwargs)


def get_customer_outstanding(*args: Any, **kwargs: Any) -> Any:
    return _call("get_customer_outstanding", args, kwargs)


def get_customers_suppliers(*args: Any, **kwargs: Any) -> Any:
    return _call("get_customers_suppliers", args, kwargs)


def make_closing_entry_from_opening(*args: Any, **kwargs: Any) -> Any:
    return _call("make_closing_entry_from_opening", args, kwargs)
