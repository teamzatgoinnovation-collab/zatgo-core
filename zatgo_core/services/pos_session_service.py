"""POS cash session: opening and closing a cashier's shift on ERPNext's own POS Opening / POS Closing Entry.

ERPNext already has the session records (POS Opening Entry: cashier, profile, opening float per payment method; POS
Closing Entry: expected vs counted per method, variance). They are used as they are. The one thing ERPNext cannot do
for this POS is *see the sales*: its closing entry only reads Sales Invoices created with `is_pos=1`, while the ZatGo POS
posts a normal Sales Invoice plus a Payment Entry per sale (services/retail_pos_service.py). So this module only feeds the
native closing entry the per-method totals computed from those Payment Entries; nothing is posted to the GL or the stock ledger.

A session belongs to a cashier. ERPNext allows one open session per POS Profile, so each cashier gets a profile of their own
(`ZatGo POS - <user> - <company abbr>`, created on first use, restricted to that user).
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import cint, flt, get_datetime, now_datetime, nowdate, nowtime

from zatgo_core.api.response import ok
from zatgo_core.api.validators import require_login
from zatgo_core.services.resto_pos_admin_service import _company
from zatgo_core.services.resto_pos_service import _MODE_OF_PAYMENT_MAP, _resolve_pos_warehouse
from zatgo_core.services.retail_pos_service import _MARKER, _method_key

_CASH = _MODE_OF_PAYMENT_MAP["cash"]


# --- profile ---------------------------------------------------------------


def _ensure_profile(user: str, company: str) -> str:
    """The cashier's own POS Profile (ERPNext allows one open session per profile). Created once, as configuration."""
    co = frappe.get_cached_doc("Company", company)
    name = f"ZatGo POS - {user} - {co.abbr}"  # a profile belongs to one company, so one per cashier and company
    if frappe.db.exists("POS Profile", name):
        return name
    # A profile made earlier under another name (before the company abbreviation was part of it) is reused: ERPNext
    # allows only one default profile per user.
    earlier = frappe.db.sql(
        """select p.name from `tabPOS Profile` p join `tabPOS Profile User` u on u.parent = p.name
           where p.company = %s and u.user = %s and ifnull(p.disabled, 0) = 0 order by p.creation limit 1""",
        (company, user),
    )
    if earlier:
        return earlier[0][0]
    warehouse = _resolve_pos_warehouse(company)
    write_off = co.write_off_account or frappe.db.get_value(
        "Account", {"company": company, "account_type": "Expense Account", "is_group": 0}, "name"
    )
    cost_center = co.cost_center
    if not (write_off and cost_center):
        frappe.throw(f"Company {company} needs a Write Off Account and a Cost Center before POS sessions can be used.")
    profile = frappe.get_doc(
        {
            "doctype": "POS Profile",
            "__newname": name,
            "name": name,
            "company": company,
            "currency": co.default_currency,
            "warehouse": warehouse,
            "write_off_account": write_off,
            "write_off_cost_center": cost_center,
            "applicable_for_users": [{"user": user, "default": 1}],
            # ERPNext refuses a session on a method that has no default account for the company, so only those are listed.
            "payments": [
                {"mode_of_payment": mop, "default": 1 if mop == _CASH else 0}
                for mop in _MODE_OF_PAYMENT_MAP.values()
                if frappe.db.get_value(
                    "Mode of Payment Account", {"parent": mop, "company": company}, "default_account"
                )
            ],
        }
    )
    # Not the cashier's permission to give: the profile is configuration derived from company defaults, for that user only.
    profile.insert(ignore_permissions=True)
    return profile.name


# --- reading a session -----------------------------------------------------


def _open_entry(user: str, company: str | None = None) -> Any | None:
    filters: dict[str, Any] = {"user": user, "status": "Open", "docstatus": 1}
    if company:
        filters["company"] = company
    name = frappe.db.get_value("POS Opening Entry", filters, "name", order_by="creation desc")
    return frappe.get_doc("POS Opening Entry", name) if name else None


def _sales_since(user: str, company: str, start: Any) -> dict[str, Any]:
    """Net money by payment method, and the sales count / totals, of this cashier's retail POS sales since `start`.

    Cash in the drawer = the cash Payment Entries received, less those paid back on credit notes. Only Payment Entries made
    by this cashier (`owner`) against retail POS invoices (or their credit notes) count."""
    pes = frappe.get_all(
        "Payment Entry",
        filters={
            "docstatus": 1,
            "company": company,
            "owner": user,
            "party_type": "Customer",
            "creation": [">=", start],
        },
        fields=["name", "payment_type", "mode_of_payment", "paid_amount"],
    )
    by_method: dict[str, float] = {}
    if pes:
        refs = frappe.get_all(
            "Payment Entry Reference",
            filters={"parent": ["in", [p.name for p in pes]], "reference_doctype": "Sales Invoice"},
            fields=["parent", "reference_name"],
        )
        ref_of = {r.parent: r.reference_name for r in refs}
        invoices = {
            i.name: i
            for i in frappe.get_all(
                "Sales Invoice",
                filters={"name": ["in", list(set(ref_of.values())) or [""]]},
                fields=["name", "remarks", "is_return", "return_against"],
            )
        }
        retail_parents = set(
            frappe.get_all(
                "Sales Invoice",
                filters={"name": ["in", [i.return_against for i in invoices.values() if i.return_against] or [""]], "remarks": _MARKER},
                pluck="name",
            )
        )
        for pe in pes:
            si = invoices.get(ref_of.get(pe.name))
            if not si:
                continue
            retail = si.remarks == _MARKER or (cint(si.is_return) and si.return_against in retail_parents)
            if not retail:
                continue
            sign = 1 if pe.payment_type == "Receive" else -1
            mop = pe.mode_of_payment or _CASH
            by_method[mop] = by_method.get(mop, 0.0) + sign * flt(pe.paid_amount)

    sales = frappe.get_all(
        "Sales Invoice",
        filters={
            "docstatus": 1,
            "company": company,
            "owner": user,
            "remarks": _MARKER,
            "creation": [">=", start],
        },
        fields=["is_return", "grand_total", "net_total", "total_qty", "total_taxes_and_charges"],
    )
    returns = frappe.get_all(
        "Sales Invoice",
        filters={"docstatus": 1, "company": company, "owner": user, "is_return": 1, "creation": [">=", start]},
        fields=["grand_total", "net_total", "total_qty", "total_taxes_and_charges", "return_against"],
    )
    if returns:
        retail_set = set(
            frappe.get_all(
                "Sales Invoice",
                filters={"name": ["in", [r.return_against for r in returns if r.return_against] or [""]], "remarks": _MARKER},
                pluck="name",
            )
        )
        returns = [r for r in returns if r.return_against in retail_set]
    # Credit notes carry their own remarks, so the sale list above is invoices only; add the credit notes back in.
    docs = [s for s in sales if not cint(s.is_return)] + returns
    return {
        "by_method": by_method,
        "sales_count": len([s for s in sales if not cint(s.is_return)]),
        "returns_count": len(returns),
        "grand_total": sum(flt(d.grand_total) for d in docs),
        "net_total": sum(flt(d.net_total) for d in docs),
        "total_qty": sum(flt(d.total_qty) for d in docs),
        "taxes": sum(flt(d.total_taxes_and_charges) for d in docs),
    }


def _summary(entry: Any) -> dict[str, Any]:
    totals = _sales_since(entry.user, entry.company, entry.period_start_date)
    opening = {r.mode_of_payment: flt(r.opening_amount) for r in entry.balance_details}
    methods = []
    for mop in {*opening, *totals["by_method"]}:
        received = flt(totals["by_method"].get(mop))
        methods.append(
            {
                "method": _method_key(mop),
                "modeOfPayment": mop,
                "opening": flt(opening.get(mop)),
                "net": received,
                "expected": flt(opening.get(mop)) + received,
            }
        )
    methods.sort(key=lambda m: (m["modeOfPayment"] != _CASH, m["modeOfPayment"]))
    return {
        "id": entry.name,
        "user": entry.user,
        "company": entry.company,
        "posProfile": entry.pos_profile,
        "status": entry.status,
        "openedAt": str(entry.period_start_date),
        "salesCount": totals["sales_count"],
        "returnsCount": totals["returns_count"],
        "grandTotal": totals["grand_total"],
        "methods": methods,
    }


def current(company: str | None = None) -> dict[str, Any]:
    """The signed-in cashier's open session with the running totals, or `data: null` when none is open."""
    require_login()
    entry = _open_entry(frappe.session.user, _company(company))
    return ok(_summary(entry) if entry else None, meta={"source": "POS Opening Entry"})


# --- open ------------------------------------------------------------------


def open_session(opening_cash: Any = 0, company: str | None = None) -> dict[str, Any]:
    """Open this cashier's session (POS Opening Entry) with the cash float counted into the drawer. Idempotent: a session
    that is already open is returned as it is, whatever float the repeated call carries."""
    require_login()
    user = frappe.session.user
    comp = _company(company)
    cash = flt(opening_cash)
    if cash < 0:
        frappe.throw("The opening cash cannot be negative.")

    lock = f"zg_pos_session:{user}"
    if not frappe.db.sql("select get_lock(%s, 10)", lock)[0][0]:
        frappe.throw("Another request is opening this session. Try again.")
    try:
        entry = _open_entry(user, comp)
        if entry:
            return ok(_summary(entry), meta={"created": False, "idempotent": True, "source": "POS Opening Entry"})
        profile = _ensure_profile(user, comp)
        modes = [r.mode_of_payment for r in frappe.get_doc("POS Profile", profile).payments]
        doc = frappe.get_doc(
            {
                "doctype": "POS Opening Entry",
                "period_start_date": now_datetime(),
                "posting_date": nowdate(),
                "company": comp,
                "pos_profile": profile,
                "user": user,
                "balance_details": [
                    {"mode_of_payment": mop, "opening_amount": cash if mop == _CASH else 0} for mop in modes
                ],
            }
        )
        # The cashier opens their own session only (user is forced to the signed-in user above).
        doc.insert(ignore_permissions=True)
        doc.submit()
        frappe.db.commit()
        return ok(_summary(doc), meta={"created": True, "idempotent": False, "source": "POS Opening Entry"})
    finally:
        frappe.db.sql("select release_lock(%s)", lock)


# --- close -----------------------------------------------------------------


def close_session(
    counted_cash: Any,
    opening_entry: str | None = None,
    counted: Any = None,
    company: str | None = None,
) -> dict[str, Any]:
    """Close the signed-in cashier's open session with a POS Closing Entry whose expected amounts come from the Payment
    Entries. `counted_cash` is what was counted in the drawer; other methods (card, wallet) are settled by the processor, so
    they close at their expected amount unless `counted` ({mode_of_payment: amount}) says otherwise.

    Idempotent: repeating the call for a session that is already closed returns its closing entry (pass `opening_entry`)."""
    require_login()
    user = frappe.session.user
    comp = _company(company)
    cash = flt(counted_cash)
    if cash < 0:
        frappe.throw("The counted cash cannot be negative.")
    overrides = counted if isinstance(counted, dict) else {}

    if opening_entry:
        prior = frappe.db.get_value(
            "POS Opening Entry", opening_entry, ["user", "status", "pos_closing_entry"], as_dict=True
        )
        if prior and prior.user == user and prior.status == "Closed" and prior.pos_closing_entry:
            return ok(
                _closed_view(prior.pos_closing_entry),
                meta={"created": False, "idempotent": True, "source": "POS Closing Entry"},
            )

    entry = _open_entry(user, comp)
    if not entry:
        frappe.throw("There is no open session to close.")
    if opening_entry and entry.name != opening_entry:
        frappe.throw(f"Session {opening_entry} is not the open one ({entry.name}).")

    from erpnext.accounts.doctype.pos_closing_entry.pos_closing_entry import make_closing_entry_from_opening

    closing = make_closing_entry_from_opening(entry)  # native: also picks up any is_pos invoices on this profile
    totals = _sales_since(user, comp, entry.period_start_date)
    native = {r.mode_of_payment: flt(r.get("expected_amount")) for r in closing.get("payment_reconciliation")}
    opening = {r.mode_of_payment: flt(r.opening_amount) for r in entry.balance_details}

    rows = []
    for mop in {*opening, *native, *totals["by_method"]}:
        expected = flt(opening.get(mop)) + flt(native.get(mop)) + flt(totals["by_method"].get(mop))
        got = cash if mop == _CASH else flt(overrides.get(mop, expected))
        rows.append(
            {
                "mode_of_payment": mop,
                "opening_amount": flt(opening.get(mop)),
                "expected_amount": expected,
                "closing_amount": got,
                "difference": got - expected,
            }
        )
    closing.set("payment_reconciliation", rows)
    closing.grand_total = flt(closing.grand_total) + totals["grand_total"]
    closing.net_total = flt(closing.net_total) + totals["net_total"]
    closing.total_quantity = flt(closing.total_quantity) + totals["total_qty"]
    closing.total_taxes_and_charges = flt(closing.total_taxes_and_charges) + totals["taxes"]
    closing.posting_date = nowdate()
    closing.posting_time = nowtime()
    closing.period_end_date = get_datetime(now_datetime())
    # Closes the cashier's own session; the entry's user is the session's user, never a request value.
    closing.insert(ignore_permissions=True)
    closing.submit()
    frappe.db.commit()
    return ok(_closed_view(closing.name), meta={"created": True, "idempotent": False, "source": "POS Closing Entry"})


def _closed_view(closing_name: str) -> dict[str, Any]:
    c = frappe.get_doc("POS Closing Entry", closing_name)
    return {
        "id": c.pos_opening_entry,
        "closingId": c.name,
        "user": c.user,
        "company": c.company,
        "posProfile": c.pos_profile,
        "status": "Closed",
        "openedAt": str(c.period_start_date),
        "closedAt": str(c.period_end_date),
        "grandTotal": flt(c.grand_total),
        "methods": [
            {
                "method": _method_key(r.mode_of_payment),
                "modeOfPayment": r.mode_of_payment,
                "opening": flt(r.opening_amount),
                "expected": flt(r.expected_amount),
                "counted": flt(r.closing_amount),
                "difference": flt(r.difference),
            }
            for r in c.payment_reconciliation
        ],
    }
