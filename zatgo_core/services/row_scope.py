"""Row-level scope for API reads built on SQL or `get_all`.

`frappe.get_all` and raw SQL skip User Permissions and `permission_query_conditions`, so an endpoint that only
checks "may this user read the DocType" returned every company's rows to a user restricted to one. Reads that
can use `frappe.get_list` do (it applies both); the ones that must stay SQL (ledger sums, trial balance, P&L)
use `company_clause` to add the user's Company restriction; counts go through `count` (a bare
`frappe.db.count` also ignores permissions); a portal (Website User) session only ever sees its own
Customer's / Supplier's documents (`portal_parties`, ERPNext's own Portal User links).

Administrator and users without a Company User Permission are unrestricted -- the result for them is what it was.
"""

from __future__ import annotations

from typing import Any

import frappe


def permitted_companies(user: str | None = None) -> list[str] | None:
	"""Companies the user is restricted to by User Permissions; None when they are not restricted."""
	user = user or frappe.session.user
	if user == "Administrator":
		return None
	from frappe.permissions import get_user_permissions

	rows = (get_user_permissions(user) or {}).get("Company")
	if not rows:
		return None
	return sorted({r.get("doc") for r in rows if r.get("doc")})


def company_clause(column: str, params: dict[str, Any]) -> str:
	"""` AND <column> IN %(zg_companies)s` (filling `params`), or "" when the user is unrestricted. A user
	restricted to nothing matches nothing."""
	companies = permitted_companies()
	if companies is None:
		return ""
	params["zg_companies"] = tuple(companies) or ("",)
	return f" AND {column} IN %(zg_companies)s"


def require_company(company: str | None) -> None:
	"""A company the caller names must be one they may read."""
	if company and not frappe.has_permission("Company", "read", doc=company):
		raise frappe.PermissionError(frappe._("Not permitted for company {0}").format(company))


def count(doctype: str, filters: Any = None) -> int:
	"""Rows of `doctype` the user may see (frappe.db.count ignores permissions). Frappe v16 takes an aggregate as a
	dict -- a "count(name)" string is refused."""
	rows = frappe.get_list(doctype, filters=filters, fields=[{"COUNT": "name", "as": "c"}], limit_page_length=0)
	return int(rows[0].c) if rows else 0


def portal_parties(doctype: str, party_field: str) -> list[str] | None:
	"""For a portal (Website User) session: the Customers (`party_field` "customer") or Suppliers it belongs to
	through ERPNext's Portal User links -- [] for none. None for staff, whose scope is their permissions."""
	user = frappe.session.user
	if frappe.get_cached_value("User", user, "user_type") != "Website User":
		return None
	from erpnext.controllers.website_list_for_contact import get_customers_suppliers

	customers, suppliers = get_customers_suppliers(doctype, user)
	return list((customers if party_field == "customer" else suppliers) or [])
