"""Read-only SQL aggregates behind the MyBis dashboard. ERPNext's ledgers stay the source of truth.

Why SQL and not get_list: a dashboard sums thousands of rows; get_list would load them. The price is that raw SQL skips User
Permissions, so `guard()` (called by the API layer before anything here) refuses users who carry record-level restrictions other
than Company, and every query filters on the company the scope already validated. Sources:

- sales / purchases: submitted Sales / Purchase Invoices in company currency (`base_*`); returns are invoices with `is_return`.
- COGS and expenses, income, net profit: GL Entry by account root / type (cancelled entries excluded, Period Closing Voucher
  entries excluded so a year-end close does not zero the P&L).
- gross profit: net sales - COGS. COGS comes from the GL when the company runs perpetual inventory; otherwise the GL has no COGS
  and the figure is an ESTIMATE from the valuation rate at the time of sale (Sales Invoice Item.incoming_rate x qty). The basis is
  reported with the figure.
- receivables / payables: GL balance of Receivable / Payable accounts as of a date (what ERPNext's aging reports start from).
- stock value: sum of Stock Ledger Entry value differences as of a date (ERPNext's own valuation).
"""

from __future__ import annotations

from datetime import date
from typing import Any

import frappe
from frappe import _
from frappe.utils import flt

# DocTypes whose rows these queries read. The caller needs read permission on each one it uses.
SOURCE_DOCTYPES = {
    "sales": "Sales Invoice",
    "purchases": "Purchase Invoice",
    "gl": "GL Entry",
    "stock": "Stock Ledger Entry",
    "bin": "Bin",
    "items": "Item",
}


def guard(*kinds: str) -> None:
    """Refuse a caller who may not read a source, or whose User Permissions can't be applied to totals."""
    for kind in kinds:
        doctype = SOURCE_DOCTYPES[kind]
        if not frappe.has_permission(doctype, "read"):
            frappe.throw(_("You do not have permission to read {0}.").format(_(doctype)), frappe.PermissionError)
    if frappe.session.user == "Administrator":
        return
    from frappe.permissions import get_user_permissions

    restricted = sorted(k for k in (get_user_permissions(frappe.session.user) or {}) if k != "Company")
    if restricted:
        frappe.throw(
            _("Your account has record-level restrictions ({0}); MyBis cannot apply them to totals yet.").format(", ".join(restricted)),
            frappe.PermissionError,
        )


def _one(sql: str, params: dict[str, Any]) -> dict[str, Any]:
    rows = frappe.db.sql(sql, params, as_dict=True)
    return rows[0] if rows else {}


# -- sales / purchases ------------------------------------------------------------------------------------------------


def sales_totals(company: str, start: date, end: date) -> dict[str, float]:
    row = _one(
        """
        SELECT
          COALESCE(SUM(CASE WHEN is_return = 0 THEN base_net_total END), 0) AS sales,
          COALESCE(SUM(CASE WHEN is_return = 1 THEN base_net_total END), 0) AS returns,
          COALESCE(SUM(CASE WHEN is_return = 0 THEN base_discount_amount END), 0) AS discount,
          COALESCE(SUM(base_total_taxes_and_charges), 0) AS tax,
          SUM(is_return = 0) AS invoices,
          COALESCE(SUM(CASE WHEN is_return = 0 THEN base_grand_total END), 0) AS grand,
          COALESCE(SUM(CASE WHEN is_return = 0 THEN outstanding_amount * conversion_rate END), 0) AS outstanding
        FROM `tabSales Invoice`
        WHERE docstatus = 1 AND company = %(company)s AND posting_date BETWEEN %(start)s AND %(end)s
        """,
        {"company": company, "start": start, "end": end},
    )
    sales, returns = flt(row.get("sales")), flt(row.get("returns"))  # returns are negative
    invoices = int(row.get("invoices") or 0)
    return {
        "sales": sales,
        "returns": returns,
        "net_sales": sales + returns,
        "discount": flt(row.get("discount")),
        "tax": flt(row.get("tax")),
        "invoices": invoices,
        "average_order_value": (sales / invoices) if invoices else 0.0,
        # incl. tax: what customers were invoiced, what they still owe on those invoices, and the rest (paid)
        "invoiced_total": flt(row.get("grand")),
        "outstanding_sales": flt(row.get("outstanding")),
        "paid_sales": flt(row.get("grand")) - flt(row.get("outstanding")),
    }


def purchase_totals(company: str, start: date, end: date) -> dict[str, float]:
    row = _one(
        """
        SELECT
          COALESCE(SUM(CASE WHEN is_return = 0 THEN base_net_total END), 0) AS purchases,
          COALESCE(SUM(CASE WHEN is_return = 1 THEN base_net_total END), 0) AS returns,
          SUM(is_return = 0) AS invoices
        FROM `tabPurchase Invoice`
        WHERE docstatus = 1 AND company = %(company)s AND posting_date BETWEEN %(start)s AND %(end)s
        """,
        {"company": company, "start": start, "end": end},
    )
    purchases, returns = flt(row.get("purchases")), flt(row.get("returns"))
    return {"purchases": purchases, "returns": returns, "net_purchases": purchases + returns, "invoices": int(row.get("invoices") or 0)}


def supplier_count(company: str, start: date, end: date) -> int:
    row = _one(
        """
        SELECT COUNT(DISTINCT supplier) AS n FROM `tabPurchase Invoice`
        WHERE docstatus = 1 AND is_return = 0 AND company = %(company)s AND posting_date BETWEEN %(start)s AND %(end)s
        """,
        {"company": company, "start": start, "end": end},
    )
    return int(row.get("n") or 0)


def net_sales_by_bucket(company: str, start: date, end: date, bucket: str) -> dict[date, float]:
    expr = {
        "day": "posting_date",
        "week": "DATE_SUB(posting_date, INTERVAL WEEKDAY(posting_date) DAY)",
        "month": "DATE_FORMAT(posting_date, '%%Y-%%m-01')",
    }[bucket]
    rows = frappe.db.sql(
        f"""
        SELECT {expr} AS bucket, COALESCE(SUM(base_net_total), 0) AS value
        FROM `tabSales Invoice`
        WHERE docstatus = 1 AND company = %(company)s AND posting_date BETWEEN %(start)s AND %(end)s
        GROUP BY bucket
        """,
        {"company": company, "start": start, "end": end},
        as_dict=True,
    )
    return {frappe.utils.getdate(r.bucket): flt(r.value) for r in rows}


# -- general ledger ---------------------------------------------------------------------------------------------------

_GL_PERIOD = """
    FROM `tabGL Entry` gle JOIN `tabAccount` acc ON acc.name = gle.account
    WHERE gle.company = %(company)s AND gle.is_cancelled = 0 AND gle.posting_date BETWEEN %(start)s AND %(end)s
      AND gle.voucher_type != 'Period Closing Voucher'
"""


def gl_pnl(company: str, start: date, end: date) -> dict[str, float]:
    """Income / COGS / other expenses from the ledger (income positive, expenses positive)."""
    row = _one(
        f"""
        SELECT
          COALESCE(SUM(CASE WHEN acc.root_type = 'Income' THEN gle.credit - gle.debit END), 0) AS income,
          COALESCE(SUM(CASE WHEN acc.root_type = 'Expense' AND acc.account_type = 'Cost of Goods Sold' THEN gle.debit - gle.credit END), 0) AS cogs,
          COALESCE(SUM(CASE WHEN acc.root_type = 'Expense' AND IFNULL(acc.account_type, '') != 'Cost of Goods Sold' THEN gle.debit - gle.credit END), 0) AS expenses
        {_GL_PERIOD}
        """,
        {"company": company, "start": start, "end": end},
    )
    income, cogs, expenses = flt(row.get("income")), flt(row.get("cogs")), flt(row.get("expenses"))
    return {"income": income, "cogs": cogs, "expenses": expenses, "net_profit": income - cogs - expenses}


def estimated_cogs(company: str, start: date, end: date) -> float:
    """COGS from valuation at the time of sale -- used only when the ledger carries none (periodic inventory)."""
    row = _one(
        """
        SELECT COALESCE(SUM(sii.incoming_rate * sii.stock_qty), 0) AS cogs
        FROM `tabSales Invoice Item` sii JOIN `tabSales Invoice` si ON si.name = sii.parent
        JOIN `tabItem` it ON it.name = sii.item_code AND it.is_stock_item = 1
        WHERE si.docstatus = 1 AND si.company = %(company)s AND si.posting_date BETWEEN %(start)s AND %(end)s
        """,
        {"company": company, "start": start, "end": end},
    )
    return flt(row.get("cogs"))


def cogs(company: str, start: date, end: date, gl_cogs: float) -> tuple[float, str]:
    """(cogs, basis) -- the ledger's COGS when the company has perpetual inventory, else the valuation estimate."""
    if frappe.get_cached_value("Company", company, "enable_perpetual_inventory"):
        return gl_cogs, "gl"
    return estimated_cogs(company, start, end), "valuation_estimate"


def balance_as_of(company: str, account_type: str, as_of: date) -> float:
    """Net debit balance of the company's accounts of `account_type` (Receivable / Payable) up to `as_of`."""
    row = _one(
        """
        SELECT COALESCE(SUM(gle.debit - gle.credit), 0) AS bal
        FROM `tabGL Entry` gle JOIN `tabAccount` acc ON acc.name = gle.account
        WHERE gle.company = %(company)s AND gle.is_cancelled = 0 AND gle.posting_date <= %(as_of)s AND acc.account_type = %(t)s
        """,
        {"company": company, "as_of": as_of, "t": account_type},
    )
    return flt(row.get("bal"))


def stock_value_as_of(company: str, as_of: date) -> float:
    row = _one(
        """
        SELECT COALESCE(SUM(stock_value_difference), 0) AS v
        FROM `tabStock Ledger Entry`
        WHERE company = %(company)s AND is_cancelled = 0 AND posting_date <= %(as_of)s
        """,
        {"company": company, "as_of": as_of},
    )
    return flt(row.get("v"))


# -- rankings ---------------------------------------------------------------------------------------------------------

_RANK_KEY = {"category": "sii.item_group", "product": "sii.item_code"}
# name / category shown next to the key
_RANK_LABEL = {
    "category": "sii.item_group AS name, NULL AS category",
    "product": "MAX(sii.item_name) AS name, MAX(sii.item_group) AS category",
}


def top_sales(company: str, start: date, end: date, by: str, limit: int, order: str = "revenue") -> list[dict[str, Any]]:
    """Top item groups / items by net sales (returns net off). order: revenue | quantity."""
    key = _RANK_KEY[by]
    order_col = "revenue" if order == "revenue" else "quantity"
    rows = frappe.db.sql(
        f"""
        SELECT {key} AS code, {_RANK_LABEL[by]},
               COALESCE(SUM(sii.base_net_amount), 0) AS revenue,
               COALESCE(SUM(sii.stock_qty), 0) AS quantity,
               COUNT(DISTINCT CASE WHEN si.is_return = 0 THEN si.name END) AS invoices
        FROM `tabSales Invoice Item` sii JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE si.docstatus = 1 AND si.company = %(company)s AND si.posting_date BETWEEN %(start)s AND %(end)s
        GROUP BY {key}
        HAVING revenue > 0
        ORDER BY {order_col} DESC
        LIMIT %(limit)s
        """,
        {"company": company, "start": start, "end": end, "limit": int(limit)},
        as_dict=True,
    )
    return [
        {
            "code": r.code,
            "name": r.name or r.code,
            "category": r.category,
            "revenue": flt(r.revenue),
            "quantity": flt(r.quantity),
            "invoices": int(r.invoices or 0),
        }
        for r in rows
    ]


def revenue_for(company: str, start: date, end: date, by: str, codes: list[str]) -> dict[str, float]:
    """Net sales of the given item groups / items in a period (for growth against the previous one)."""
    if not codes:
        return {}
    key = _RANK_KEY[by]
    rows = frappe.db.sql(
        f"""
        SELECT {key} AS code, COALESCE(SUM(sii.base_net_amount), 0) AS revenue
        FROM `tabSales Invoice Item` sii JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE si.docstatus = 1 AND si.company = %(company)s AND si.posting_date BETWEEN %(start)s AND %(end)s
          AND {key} IN %(codes)s
        GROUP BY {key}
        """,
        {"company": company, "start": start, "end": end, "codes": tuple(codes)},
        as_dict=True,
    )
    return {r.code: flt(r.revenue) for r in rows}


def total_item_revenue(company: str, start: date, end: date) -> float:
    row = _one(
        """
        SELECT COALESCE(SUM(sii.base_net_amount), 0) AS total
        FROM `tabSales Invoice Item` sii JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE si.docstatus = 1 AND si.company = %(company)s AND si.posting_date BETWEEN %(start)s AND %(end)s
        """,
        {"company": company, "start": start, "end": end},
    )
    return flt(row.get("total"))

