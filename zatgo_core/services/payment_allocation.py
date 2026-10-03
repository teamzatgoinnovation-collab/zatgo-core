"""Multi-method / multi-account payment allocation.

One transaction's money split across several Modes of Payment, and several
ledger accounts under each one (Cash -> "Cash - X" + "Petty Cash - X",
Card -> "HDFC POS - X" + "SBI POS - X", ...).

Where the rows live, and who posts them -- nothing here writes GL rows:

- Sales Invoice: ERPNext's own `payments` table (Sales Invoice Payment) on
  an `is_pos` invoice. ERPNext's make_pos_gl_entries() already posts one
  Dr <row account> / Cr <receivable> pair per row, and its
  calculate_outstanding_amount() already leaves `grand_total - paid_amount`
  outstanding. Using that table (not a parallel one) is what keeps this
  from double-posting. The only core behaviour we change is that
  before_save would otherwise overwrite every row's account with the
  mode's single default (see overrides/sales_invoice.py).
- Payment Entry: `custom_payment_details` (ZG Payment Allocation). The
  single bank-side GL line ERPNext builds (paid_to on Receive, paid_from on
  Pay) is split into one line per row by overrides/payment_entry.py; the
  party line, references, outstanding updates, deductions, taxes and
  exchange gain/loss all stay ERPNext's. The bank-side field is set to the
  first row's account so ERPNext's currency/account-type resolution still
  runs on a real account.

Which accounts a Mode of Payment may use, per company: Mode of Payment
`custom_zg_accounts` (ZG Mode of Payment Account) rows plus the native
Mode of Payment Account default. Nothing else -- an API caller can't route
money to an arbitrary ledger.
"""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt

SI_PAYMENT_TABLE = "payments"
PE_PAYMENT_TABLE = "custom_payment_details"

# A party account needs a party on its GL row; a payment row never has one.
_FORBIDDEN_ACCOUNT_TYPES = ("Receivable", "Payable")


# -- Mode of Payment configuration -------------------------------------------


def allowed_accounts(mode_of_payment: str, company: str) -> list[dict[str, Any]]:
    """Accounts `mode_of_payment` may post to for `company`, default first.

    `custom_zg_accounts` rows (enabled) plus the native Mode of Payment
    Account default. Disabled / group / other-company accounts are dropped
    here too, so a stale configuration row can't be selected.
    """
    if not mode_of_payment or not company:
        return []

    rows: list[dict[str, Any]] = []
    if frappe.db.has_table("ZG Mode of Payment Account"):
        rows = frappe.get_all(
            "ZG Mode of Payment Account",
            filters={
                "parent": mode_of_payment,
                "parenttype": "Mode of Payment",
                "company": company,
                "enabled": 1,
            },
            fields=["account", "is_default"],
            order_by="idx asc",
        )
    native_default = frappe.db.get_value(
        "Mode of Payment Account",
        {"parent": mode_of_payment, "company": company},
        "default_account",
    )

    result: dict[str, dict[str, Any]] = {}
    has_custom_default = any(cint(r.is_default) for r in rows)
    if native_default:
        result[native_default] = {"account": native_default, "is_default": not has_custom_default}
    for r in rows:
        if r.account in result:
            result[r.account]["is_default"] = result[r.account]["is_default"] or bool(cint(r.is_default))
        else:
            result[r.account] = {"account": r.account, "is_default": bool(cint(r.is_default))}

    if not result:
        return []
    valid = set(
        frappe.get_all(
            "Account",
            filters={"name": ["in", list(result)], "company": company, "is_group": 0, "disabled": 0},
            pluck="name",
        )
    )
    out = [v for k, v in result.items() if k in valid]
    out.sort(key=lambda r: not r["is_default"])
    return out


def default_account(mode_of_payment: str, company: str) -> str | None:
    accounts = allowed_accounts(mode_of_payment, company)
    return accounts[0]["account"] if accounts else None


def is_allowed_account(account: str, mode_of_payment: str, company: str) -> bool:
    return any(a["account"] == account for a in allowed_accounts(mode_of_payment, company))


def validate_mode_of_payment(doc, method=None) -> None:
    """Mode of Payment validate hook: the `custom_zg_accounts` rows."""
    seen: set[tuple[str, str]] = set()
    defaults: dict[str, int] = {}
    for row in doc.get("custom_zg_accounts") or []:
        if not row.company or not row.account:
            continue
        key = (row.company, row.account)
        if key in seen:
            frappe.throw(
                _("Allowed Accounts row {0}: {1} is listed more than once for {2}.").format(
                    row.idx, frappe.bold(row.account), row.company
                )
            )
        seen.add(key)
        acc = frappe.db.get_value(
            "Account", row.account, ["company", "is_group", "disabled", "account_type"], as_dict=True
        )
        if not acc:
            frappe.throw(_("Allowed Accounts row {0}: Account {1} does not exist.").format(row.idx, row.account))
        if acc.company != row.company:
            frappe.throw(
                _("Allowed Accounts row {0}: Account {1} belongs to {2}, not {3}.").format(
                    row.idx, frappe.bold(row.account), acc.company, row.company
                )
            )
        if cint(acc.is_group):
            frappe.throw(
                _("Allowed Accounts row {0}: {1} is a group account.").format(row.idx, frappe.bold(row.account))
            )
        if acc.account_type in _FORBIDDEN_ACCOUNT_TYPES:
            frappe.throw(
                _("Allowed Accounts row {0}: {1} is a {2} account and cannot hold payments.").format(
                    row.idx, frappe.bold(row.account), acc.account_type
                )
            )
        if cint(row.is_default) and cint(row.enabled):
            defaults[row.company] = defaults.get(row.company, 0) + 1
    for company, count in defaults.items():
        if count > 1:
            frappe.throw(_("Only one Default allowed account per company ({0}).").format(company))


# -- Row validation (shared by Sales Invoice and Payment Entry) ---------------


def _validate_row_account(row, company: str, label: str) -> frappe._dict:
    if not row.mode_of_payment:
        frappe.throw(_("{0}: Payment Method is required.").format(label))
    mop = frappe.db.get_value("Mode of Payment", row.mode_of_payment, ["name", "enabled"], as_dict=True)
    if not mop:
        frappe.throw(_("{0}: Payment Method {1} does not exist.").format(label, row.mode_of_payment))
    if not cint(mop.enabled):
        frappe.throw(_("{0}: Payment Method {1} is disabled.").format(label, frappe.bold(row.mode_of_payment)))

    if not row.account:
        frappe.throw(_("{0}: Account is required.").format(label))
    acc = frappe.db.get_value(
        "Account",
        row.account,
        ["company", "is_group", "disabled", "account_type", "account_currency"],
        as_dict=True,
    )
    if not acc:
        frappe.throw(_("{0}: Account {1} does not exist.").format(label, row.account))
    if acc.company != company:
        frappe.throw(
            _("{0}: Account {1} belongs to company {2}, not {3}.").format(
                label, frappe.bold(row.account), acc.company, company
            )
        )
    if cint(acc.is_group):
        frappe.throw(_("{0}: {1} is a group account. Pick a ledger account.").format(label, frappe.bold(row.account)))
    if cint(acc.disabled):
        frappe.throw(_("{0}: Account {1} is disabled.").format(label, frappe.bold(row.account)))
    if acc.account_type in _FORBIDDEN_ACCOUNT_TYPES:
        frappe.throw(
            _("{0}: {1} is a {2} account and cannot receive or pay money directly.").format(
                label, frappe.bold(row.account), acc.account_type
            )
        )
    if not is_allowed_account(row.account, row.mode_of_payment, company):
        frappe.throw(
            _(
                "{0}: Account {1} is not configured for Payment Method {2} in {3}. "
                "Add it to the Payment Method's Allowed Accounts first."
            ).format(label, frappe.bold(row.account), frappe.bold(row.mode_of_payment), company)
        )
    return acc


def _reject_duplicate_rows(rows, label_fn) -> None:
    """Two rows with the same method + account and no reference to tell them
    apart are almost always a double-entered line, not two payments."""
    seen: dict[tuple[str, str], int] = {}
    for row in rows:
        if row.get("reference_no"):
            continue
        key = (row.mode_of_payment, row.account)
        if key in seen:
            frappe.throw(
                _("{0} duplicates row {1} ({2} / {3}). Merge them, or give each a Reference.").format(
                    label_fn(row), seen[key], row.mode_of_payment, row.account
                )
            )
        seen[key] = row.idx


# -- Sales Invoice -----------------------------------------------------------


def _si_applies(doc) -> bool:
    # POS-created / consolidated invoices are governed by ERPNext's POS flow
    # (POS Profile, POS Closing) -- leave them exactly as ERPNext has them.
    return bool(
        cint(doc.get("is_pos"))
        and doc.get(SI_PAYMENT_TABLE)
        and not cint(doc.get("is_created_using_pos"))
        and not cint(doc.get("is_consolidated"))
    )


def validate_sales_invoice(doc, method=None) -> None:
    """Sales Invoice validate hook (runs after ERPNext's own validate, so
    paid_amount / change_amount / outstanding_amount are already computed
    by ERPNext's taxes_and_totals)."""
    if not _si_applies(doc):
        return

    def label(row) -> str:
        return _("Payment row {0}").format(row.idx)

    company_currency = frappe.get_cached_value("Company", doc.company, "default_currency")
    for row in doc.get(SI_PAYMENT_TABLE):
        acc = _validate_row_account(row, doc.company, label(row))
        # make_pos_gl_entries posts `base_amount` when the account is in
        # company currency and `amount` (invoice currency) otherwise -- any
        # third currency would be booked wrong.
        if acc.account_currency not in (company_currency, doc.currency):
            frappe.throw(
                _("{0}: Account {1} is in {2}; it must be in {3} or the invoice currency {4}.").format(
                    label(row), frappe.bold(row.account), acc.account_currency, company_currency, doc.currency
                )
            )
        if cint(doc.is_return):
            if flt(row.amount) > 0:
                frappe.throw(_("{0}: a return's payment amount must be negative (a refund).").format(label(row)))
        elif flt(row.amount) < 0:
            frappe.throw(_("{0}: Amount must be greater than zero.").format(label(row)))

    nonzero = [r for r in doc.get(SI_PAYMENT_TABLE) if flt(r.amount)]
    _reject_duplicate_rows(nonzero, label)

    if cint(doc.is_return):
        # ERPNext's own validate_pos_return / validate_pos cover refund totals.
        return

    precision = doc.precision("outstanding_amount")
    invoice_total = flt(doc.rounded_total) or flt(doc.grand_total)
    if flt(doc.change_amount) > 0 or flt(doc.outstanding_amount, precision) < 0:
        frappe.throw(
            _(
                "Payment allocation does not match invoice total: payments {0} exceed the invoice total {1}."
            ).format(
                frappe.format_value(doc.paid_amount, currency=doc.currency),
                frappe.format_value(invoice_total, currency=doc.currency),
            ),
            title=_("Overpayment"),
        )
    if flt(doc.outstanding_amount, precision) > 0 and (doc.get("custom_payment_type") or "") != "Credit":
        frappe.throw(
            _(
                "Payment allocation does not match invoice total: payments {0}, invoice total {1}, "
                "difference {2}. Allocate the full amount, or set Payment Type to Credit to leave "
                "the difference outstanding."
            ).format(
                frappe.format_value(doc.paid_amount, currency=doc.currency),
                frappe.format_value(invoice_total, currency=doc.currency),
                frappe.format_value(doc.outstanding_amount, currency=doc.party_account_currency),
            ),
            title=_("Payment Mismatch"),
        )


# -- Payment Entry -----------------------------------------------------------


def _pe_rows(doc) -> list:
    return [r for r in doc.get(PE_PAYMENT_TABLE) or [] if r.mode_of_payment or r.account or flt(r.amount)]


def _bank_side(doc) -> str:
    return "paid_to" if doc.payment_type == "Receive" else "paid_from"


def prepare_payment_entry(doc, method=None) -> None:
    """Payment Entry before_validate hook: validate rows, then point the
    bank-side account and amounts at them before ERPNext's own validate
    resolves currencies, exchange rates and allocations."""
    rows = _pe_rows(doc)
    doc.set(PE_PAYMENT_TABLE, rows)
    if not rows:
        return
    if doc.payment_type not in ("Receive", "Pay"):
        frappe.throw(_("Payment Details rows are only supported on Receive and Pay entries."))

    def label(row) -> str:
        return _("Payment Details row {0}").format(row.idx)

    currencies = set()
    for row in rows:
        acc = _validate_row_account(row, doc.company, label(row))
        if flt(row.amount) <= 0:
            frappe.throw(_("{0}: Amount must be greater than zero.").format(label(row)))
        row.account_currency = acc.account_currency
        currencies.add(acc.account_currency)
    _reject_duplicate_rows(rows, label)
    if len(currencies) > 1:
        frappe.throw(
            _("All Payment Details accounts must share one currency; got {0}.").format(", ".join(sorted(currencies)))
        )

    side = _bank_side(doc)
    first = rows[0].account
    if doc.get(side) != first:
        doc.set(side, first)
        # Let ERPNext's set_missing_values() re-resolve them for the new account.
        doc.set(f"{side}_account_currency", None)
        doc.set(f"{side}_account_type", None)

    total = flt(sum(flt(r.amount) for r in rows), doc.precision("paid_amount"))
    row_currency = currencies.pop()
    party_account = doc.get("paid_from" if side == "paid_to" else "paid_to")
    party_currency = frappe.get_cached_value("Account", party_account, "account_currency") if party_account else None
    if side == "paid_to":
        doc.received_amount = total
        if not party_currency or party_currency == row_currency:
            doc.paid_amount = total
    else:
        doc.paid_amount = total
        if not party_currency or party_currency == row_currency:
            doc.received_amount = total

    modes = {r.mode_of_payment for r in rows}
    doc.mode_of_payment = modes.pop() if len(modes) == 1 else None


def validate_payment_entry(doc, method=None) -> None:
    """Payment Entry validate hook (after ERPNext's validate): totals and the
    company-currency split, with ERPNext's final amounts in hand."""
    rows = doc.get(PE_PAYMENT_TABLE) or []
    if not rows:
        return
    side = _bank_side(doc)
    bank_currency = doc.get(f"{side}_account_currency")
    for row in rows:
        if row.account_currency != bank_currency:
            frappe.throw(
                _("Payment Details row {0}: account currency {1} differs from {2}.").format(
                    row.idx, row.account_currency, bank_currency
                )
            )
    expected = doc.received_amount if side == "paid_to" else doc.paid_amount
    total = sum(flt(r.amount) for r in rows)
    precision = doc.precision("paid_amount")
    if flt(total, precision) != flt(expected, precision):
        frappe.throw(
            _("Payment Details total {0} does not match the {1} {2}.").format(
                total, _("Received Amount") if side == "paid_to" else _("Paid Amount"), expected
            ),
            title=_("Payment Mismatch"),
        )
    split_base_amounts(doc)


def split_base_amounts(doc) -> list:
    """Company-currency amount per row, summing *exactly* to the base amount
    ERPNext posts for the bank side (base_received_amount on Receive,
    base_paid_amount on Pay) -- proportional, remainder on the last row.
    Currency conversion, not rounding concealment: the total is ERPNext's."""
    rows = doc.get(PE_PAYMENT_TABLE) or []
    if not rows:
        return rows
    side = _bank_side(doc)
    base_total = flt(doc.base_received_amount if side == "paid_to" else doc.base_paid_amount)
    total = sum(flt(r.amount) for r in rows)
    precision = rows[0].precision("base_amount")
    running = 0.0
    for i, row in enumerate(rows):
        if i == len(rows) - 1:
            row.base_amount = flt(base_total - running, precision)
        else:
            row.base_amount = flt(flt(row.amount) * base_total / total, precision) if total else 0
            running += row.base_amount
        if flt(row.base_amount) <= 0:
            frappe.throw(_("Payment Details row {0}: amount is too small to post.").format(row.idx))
    return rows


# -- API input ---------------------------------------------------------------


def parse_payment_details(raw: Any, company: str | None = None) -> list[dict[str, Any]]:
    """Normalise an API caller's `payment_details` into row dicts.

    Accepts a list (or JSON string) of {payment_method | mode_of_payment,
    account?, amount, reference_no?, remarks?}. With `company`, a missing
    account becomes the method's default there; without, it stays None and
    apply_to_*() fills it from the document's company. Full validation still
    happens in the document hooks -- this only shapes input and rejects the
    obviously malformed.
    """
    if raw in (None, "", []):
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            frappe.throw(_("payment_details must be a JSON list."))
    if not isinstance(raw, list):
        frappe.throw(_("payment_details must be a list."))

    rows = []
    for i, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            frappe.throw(_("payment_details[{0}] must be an object.").format(i))
        mop = (item.get("payment_method") or item.get("mode_of_payment") or "").strip()
        if not mop:
            frappe.throw(_("payment_details[{0}]: payment_method is required.").format(i))
        amount = flt(item.get("amount"))
        if amount <= 0:
            frappe.throw(_("payment_details[{0}]: amount must be greater than zero.").format(i))
        rows.append(
            {
                "mode_of_payment": mop,
                "account": (item.get("account") or "").strip() or None,
                "amount": amount,
                "reference_no": (item.get("reference_no") or item.get("reference") or "").strip() or None,
                "remarks": (item.get("remarks") or "").strip() or None,
            }
        )
    if company:
        _fill_default_accounts(rows, company)
    return rows


def _fill_default_accounts(rows: list[dict[str, Any]], company: str) -> None:
    for i, row in enumerate(rows, start=1):
        if row["account"]:
            continue
        row["account"] = default_account(row["mode_of_payment"], company)
        if not row["account"]:
            frappe.throw(
                _("payment_details[{0}]: no account given and Payment Method {1} has no default for {2}.").format(
                    i, row["mode_of_payment"], company
                )
            )


def apply_to_sales_invoice(doc, rows: list[dict[str, Any]]) -> None:
    """Put parsed rows on an unsaved Sales Invoice as ERPNext POS payments."""
    if not rows:
        return
    _fill_default_accounts(rows, doc.company)
    doc.is_pos = 1
    # A back-office / van invoice is not a POS-terminal sale: don't let a
    # company-wide POS Profile get attached and rewrite its fields/payments.
    doc.flags.ignore_pos_profile = True
    doc.set(
        SI_PAYMENT_TABLE,
        [
            {
                "mode_of_payment": r["mode_of_payment"],
                "account": r["account"],
                "amount": r["amount"],
                "reference_no": r["reference_no"],
                "custom_remarks": r["remarks"],
            }
            for r in rows
        ],
    )


def apply_to_payment_entry(doc, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    _fill_default_accounts(rows, doc.company)
    doc.set(PE_PAYMENT_TABLE, rows)


def payment_details_payload(doc) -> list[dict[str, Any]]:
    """Rows as returned to API callers (Sales Invoice or Payment Entry)."""
    table = SI_PAYMENT_TABLE if doc.doctype == "Sales Invoice" else PE_PAYMENT_TABLE
    out = []
    for r in doc.get(table) or []:
        out.append(
            {
                "payment_method": r.mode_of_payment,
                "account": r.account,
                "amount": flt(r.amount),
                "base_amount": flt(r.base_amount),
                "reference_no": r.reference_no,
                "remarks": r.get("custom_remarks") if table == SI_PAYMENT_TABLE else r.get("remarks"),
            }
        )
    return out
