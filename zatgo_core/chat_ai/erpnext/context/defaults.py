"""Resolve ERPNext intelligent defaults (company, warehouse, etc.)."""

from __future__ import annotations

import re

import frappe

# Never surface these (or any "Using …:" line) in chat replies.
_USING_LINE = re.compile(r"^Using\s+[^:]+:\s*.+$", re.IGNORECASE)


def resolve_intelligent_defaults(context: dict | None = None) -> dict:
	"""Return { values: {...}, assumptions: [] }.

	Defaults are applied silently for tools — never as chat preamble lines.
	"""
	context = context or {}
	values: dict = {}

	company = _resolve_company(context)
	if company:
		values["company"] = company

	branch = _resolve_branch(company)
	if branch:
		values["branch"] = branch

	warehouse = _resolve_warehouse(company)
	if warehouse:
		values["warehouse"] = warehouse

	if company:
		currency = frappe.db.get_value("Company", company, "default_currency")
		if currency:
			values["currency"] = currency

		fy = _resolve_fiscal_year(company)
		if fy:
			values["fiscal_year"] = fy

	return {"values": values, "assumptions": []}


def filter_user_visible_assumptions(assumptions: list[str] | None) -> list[str]:
	"""Drop all 'Using …:' routine default lines from chat-facing assumption lists."""
	out = []
	for a in assumptions or []:
		s = str(a or "").strip()
		if not s:
			continue
		if _USING_LINE.match(s):
			continue
		if s.lower().startswith("using "):
			continue
		out.append(s)
	return out


def strip_using_preamble(text: str | None) -> str:
	"""Remove leading 'Using Company/Currency/Fiscal Year…' lines the model may emit."""
	if not text:
		return text or ""
	lines = text.splitlines()
	i = 0
	while i < len(lines):
		raw = lines[i]
		s = raw.strip()
		if not s:
			i += 1
			continue
		if _USING_LINE.match(s) or s.lower().startswith("using "):
			i += 1
			continue
		# Also drop a lone "**Assumptions:**" / "Assumptions:" header if followed by Using lines only
		if s.lower().rstrip(":") in ("assumptions", "**assumptions**"):
			i += 1
			continue
		break
	# Trim leading blank lines after strip
	while i < len(lines) and not lines[i].strip():
		i += 1
	return "\n".join(lines[i:]).lstrip("\n")


def _assumption(label: str, value: str, reason: str = "") -> str:
	if reason:
		return f"Using {label}: {value} ({reason})."
	return f"Using {label}: {value}."


def _resolve_company(context: dict) -> str | None:
	ctx_company = (context.get("current_company") or {}).get("company")
	if ctx_company:
		return ctx_company
	user_default = frappe.defaults.get_user_default("Company")
	if user_default:
		return user_default
	companies = frappe.get_all("Company", filters={"disabled": 0}, pluck="name", limit=2)
	if len(companies) == 1:
		return companies[0]
	return None


def _resolve_branch(company: str | None) -> str | None:
	if not company or not frappe.db.exists("DocType", "Branch"):
		return None
	user_default = frappe.defaults.get_user_default("Branch")
	if user_default:
		return user_default
	branches = frappe.get_all("Branch", pluck="name", limit=2)
	if len(branches) == 1:
		return branches[0]
	return None


def _resolve_warehouse(company: str | None) -> str | None:
	if not company or not frappe.db.exists("DocType", "Warehouse"):
		return None
	user_default = frappe.defaults.get_user_default("Warehouse")
	if user_default:
		return user_default
	# Company default warehouse
	if frappe.db.has_column("Company", "default_warehouse"):
		wh = frappe.db.get_value("Company", company, "default_warehouse")
		if wh:
			return wh
	warehouses = frappe.get_all(
		"Warehouse",
		filters={"company": company, "is_group": 0, "disabled": 0},
		pluck="name",
		limit=2,
	)
	if len(warehouses) == 1:
		return warehouses[0]
	return None


def _resolve_fiscal_year(company: str | None) -> str | None:
	if not company or not frappe.db.exists("DocType", "Fiscal Year"):
		return None
	try:
		from erpnext.accounts.utils import get_fiscal_year

		fy = get_fiscal_year(frappe.utils.today(), company=company)
		if fy and fy[0]:
			return fy[0]
	except Exception:
		pass
	rows = frappe.get_all("Fiscal Year", filters={"disabled": 0}, pluck="name", limit=1)
	return rows[0] if rows else None
