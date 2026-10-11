"""Company status brief + thin dashboard_summary."""

from __future__ import annotations


import frappe
from frappe.utils import flt, getdate, today

from zatgo_core.chat_ai.core.tool_router.spec import CATEGORY_READ, ToolSpec


def get_tools():
	return [
		ToolSpec(
			name="dashboard_summary",
			description="Count open docs for common types",
			category=CATEGORY_READ,
			skill="analytics",
			parameters={"type": "object", "properties": {}},
			handler=_summary,
		),
		ToolSpec(
			name="company_status_brief",
			description=(
				"Multi-domain company health snapshot: receivables, payables, cash, "
				"low stock, CRM, projects/tasks. Use for 'company status' / business overview."
			),
			category=CATEGORY_READ,
			skill="analytics",
			parameters={
				"type": "object",
				"properties": {
					"company": {"type": "string", "description": "Company name; defaults from context"},
				},
			},
			handler=_company_status_brief,
		),
	]


def _summary():
	out = {}
	for dt in ("Task", "Issue", "Sales Invoice", "Project", "Lead"):
		if frappe.db.exists("DocType", dt) and frappe.has_permission(dt, "read"):
			out[dt] = _count(dt)
	return out


def _company_status_brief(company: str | None = None, **kwargs):
	company = (company or kwargs.get("company") or _default_company() or "").strip()
	# The company comes from the caller: it must be one they may read (User
	# Permissions on Company), or another company's books would be summarised.
	if company and not frappe.has_permission("Company", "read", doc=company):
		frappe.throw(frappe._("Not permitted to view company {0}").format(company), frappe.PermissionError)
	sections = []
	actions = []
	omitted = []

	ar = _receivables(company)
	if ar is None:
		omitted.append("receivables")
	else:
		sections.append(ar)
		if ar.get("meta", {}).get("overdue_count"):
			actions.append(f"Follow up {ar['meta']['overdue_count']} overdue customer invoice(s)")

	ap = _payables(company)
	if ap is None:
		omitted.append("payables")
	else:
		sections.append(ap)
		if ap.get("meta", {}).get("overdue_count"):
			actions.append(f"Review {ap['meta']['overdue_count']} overdue supplier invoice(s)")

	cash = _cash_bank(company)
	if cash is None:
		omitted.append("cash")
	else:
		sections.append(cash)

	stock = _low_stock(company)
	if stock is None:
		omitted.append("stock")
	else:
		sections.append(stock)
		n = stock.get("meta", {}).get("low_count") or 0
		if n:
			actions.append(f"Reorder or investigate {n} low/zero stock item(s)")

	crm = _crm_open()
	if crm is None:
		omitted.append("crm")
	else:
		sections.append(crm)

	ops = _projects_tasks()
	if ops is None:
		omitted.append("projects")
	else:
		sections.append(ops)
		od = ops.get("meta", {}).get("overdue_tasks") or 0
		if od:
			actions.append(f"Clear {od} overdue task(s)")

	hr = _hr_optional()
	if hr is not None:
		sections.append(hr)

	# Plugin status sections
	try:
		from zatgo_core.chat_ai.plugin.registry import get_status_section_providers

		for fn in get_status_section_providers():
			try:
				extra = fn(company, {})
				if isinstance(extra, dict) and extra.get("title"):
					sections.append(extra)
			except Exception:
				pass
	except Exception:
		pass

	summary_md = _build_summary_md(company, sections, omitted)
	aging_chart = None
	for s in sections:
		if s.get("key") == "receivables" and s.get("chart"):
			aging_chart = s["chart"]
			break

	return {
		"_artifact_sections": True,
		"company": company,
		"as_of": today(),
		"summary_md": summary_md,
		"executive_summary": summary_md,
		"sections": sections,
		"actions": actions,
		"checklist": actions,
		"omitted": omitted,
		"chart": aging_chart,
	}


def _default_company() -> str:
	try:
		c = frappe.defaults.get_user_default("Company")
		if c:
			return c
	except Exception:
		pass
	try:
		rows = frappe.get_list("Company", pluck="name", limit_page_length=2)
		if len(rows) == 1:
			return rows[0]
		return rows[0] if rows else ""
	except Exception:
		return ""


def _count(dt: str, filters: dict | None = None) -> int:
	"""Like frappe.db.count, but only rows this user may read (get_list
	applies User Permissions and permission query conditions)."""
	return len(frappe.get_list(dt, filters=filters or {}, pluck="name", limit_page_length=10000))


def _can(dt: str) -> bool:
	return bool(frappe.db.exists("DocType", dt) and frappe.has_permission(dt, "read"))


def _receivables(company: str):
	if not _can("Sales Invoice"):
		return None
	filters = {"docstatus": 1, "outstanding_amount": (">", 0)}
	if company:
		filters["company"] = company
	rows = frappe.get_list(
		"Sales Invoice",
		filters=filters,
		fields=["name", "customer", "due_date", "outstanding_amount", "grand_total", "currency"],
		order_by="due_date asc",
		limit_page_length=50,
	)
	today_d = getdate(today())
	overdue = []
	open_amt = 0.0
	overdue_amt = 0.0
	buckets = {"current": 0.0, "1-30": 0.0, "31-60": 0.0, "61+": 0.0}
	for r in rows:
		amt = flt(r.outstanding_amount)
		open_amt += amt
		due = getdate(r.due_date) if r.due_date else today_d
		days = (today_d - due).days
		if days > 0:
			overdue_amt += amt
			overdue.append(r)
			if days <= 30:
				buckets["1-30"] += amt
			elif days <= 60:
				buckets["31-60"] += amt
			else:
				buckets["61+"] += amt
		else:
			buckets["current"] += amt
	table_rows = [
		[r.name, r.customer, str(r.due_date or ""), flt(r.outstanding_amount)]
		for r in overdue[:20]
	]
	return {
		"key": "receivables",
		"title": "Receivables / Debtors",
		"meta": {
			"open_count": len(rows),
			"open_amount": open_amt,
			"overdue_count": len(overdue),
			"overdue_amount": overdue_amt,
		},
		"table": {
			"headers": ["Invoice", "Customer", "Due Date", "Outstanding"],
			"rows": table_rows,
		},
		"chart": {
			"type": "bar",
			"labels": list(buckets.keys()),
			"values": [buckets[k] for k in buckets],
			"title": "AR aging (approx)",
		},
	}


def _payables(company: str):
	if not _can("Purchase Invoice"):
		return None
	filters = {"docstatus": 1, "outstanding_amount": (">", 0)}
	if company:
		filters["company"] = company
	rows = frappe.get_list(
		"Purchase Invoice",
		filters=filters,
		fields=["name", "supplier", "due_date", "outstanding_amount"],
		order_by="due_date asc",
		limit_page_length=50,
	)
	today_d = getdate(today())
	overdue = []
	open_amt = overdue_amt = 0.0
	for r in rows:
		amt = flt(r.outstanding_amount)
		open_amt += amt
		due = getdate(r.due_date) if r.due_date else today_d
		if (today_d - due).days > 0:
			overdue_amt += amt
			overdue.append(r)
	return {
		"key": "payables",
		"title": "Payables / Creditors",
		"meta": {
			"open_count": len(rows),
			"open_amount": open_amt,
			"overdue_count": len(overdue),
			"overdue_amount": overdue_amt,
		},
		"table": {
			"headers": ["Invoice", "Supplier", "Due Date", "Outstanding"],
			"rows": [[r.name, r.supplier, str(r.due_date or ""), flt(r.outstanding_amount)] for r in overdue[:20]],
		},
	}


def _cash_bank(company: str):
	if not _can("Account"):
		return None
	filters = {"account_type": ("in", ["Cash", "Bank"]), "is_group": 0}
	if company:
		filters["company"] = company
	# get_list: only accounts this user may read (User Permissions on Company /
	# Account apply); the GL sums below are per listed account only.
	accounts = frappe.get_list("Account", filters=filters, fields=["name", "account_type"], limit_page_length=30)
	rows_out = []
	total = 0.0
	for a in accounts:
		bal = 0.0
		try:
			# Prefer GL Entry sum when readable
			if _can("GL Entry"):
				r = frappe.db.sql(
					"""
					select sum(debit) - sum(credit) from `tabGL Entry`
					where account=%s and is_cancelled=0
					"""
					+ (" and company=%s" if company else ""),
					(a.name, company) if company else (a.name,),
				)
				bal = flt(r[0][0] if r else 0)
		except Exception:
			bal = 0.0
		total += bal
		rows_out.append([a.name, a.account_type, bal])
	if not accounts:
		return {
			"key": "cash",
			"title": "Cash / Bank",
			"meta": {"note": "No cash/bank accounts found"},
			"table": {"headers": ["Account", "Type", "Balance"], "rows": []},
		}
	return {
		"key": "cash",
		"title": "Cash / Bank",
		"meta": {"account_count": len(accounts), "total_balance": total},
		"table": {"headers": ["Account", "Type", "Balance"], "rows": rows_out[:20]},
	}


def _low_stock(company: str):
	if not _can("Bin"):
		return None
	# Actual qty <= 0 or below reserved; top N by negative/zero
	try:
		# get_list, not raw SQL: Warehouse / Company User Permissions apply.
		bins = frappe.get_list(
			"Bin",
			filters={"actual_qty": ("<=", 0)},
			fields=["item_code", "warehouse", "actual_qty", "reserved_qty"],
			order_by="actual_qty asc",
			limit_page_length=25,
		)
	except Exception:
		return None
	# Optionally filter warehouses by company
	rows = []
	for b in bins:
		wh = b.warehouse
		if company and frappe.db.exists("Warehouse", wh):
			wh_co = frappe.db.get_value("Warehouse", wh, "company")
			if wh_co and wh_co != company:
				continue
		rows.append([b.item_code, b.warehouse, flt(b.actual_qty), flt(b.reserved_qty)])
	return {
		"key": "stock",
		"title": "Low / Zero Stock",
		"meta": {"low_count": len(rows)},
		"table": {
			"headers": ["Item", "Warehouse", "Actual Qty", "Reserved"],
			"rows": rows[:20],
		},
	}


def _crm_open():
	parts = []
	meta = {}
	if _can("Lead"):
		n = _count("Lead", {"status": ("not in", ["Converted", "Do Not Contact"])})
		meta["open_leads"] = n
		parts.append(["Lead", n])
	if _can("Opportunity"):
		n = _count("Opportunity", {"status": ("not in", ["Closed", "Converted", "Lost"])})
		meta["open_opportunities"] = n
		parts.append(["Opportunity", n])
	if not parts:
		return None
	return {
		"key": "crm",
		"title": "Sales / CRM",
		"meta": meta,
		"table": {"headers": ["DocType", "Open count"], "rows": parts},
	}


def _projects_tasks():
	if not (_can("Project") or _can("Task")):
		return None
	meta = {}
	rows = []
	if _can("Project"):
		n = _count("Project", {"status": ("not in", ["Completed", "Cancelled"])})
		meta["open_projects"] = n
		rows.append(["Project", n, ""])
	if _can("Task"):
		open_n = _count("Task", {"status": ("not in", ["Completed", "Cancelled"])})
		meta["open_tasks"] = open_n
		overdue = 0
		try:
			overdue = _count(
				"Task",
				{
					"status": ("not in", ["Completed", "Cancelled"]),
					"exp_end_date": ("<", today()),
				},
			)
		except Exception:
			overdue = 0
		meta["overdue_tasks"] = overdue
		rows.append(["Task", open_n, f"overdue={overdue}"])
	return {
		"key": "projects",
		"title": "Projects / Tasks",
		"meta": meta,
		"table": {"headers": ["Type", "Open", "Note"], "rows": rows},
	}


def _hr_optional():
	if not _can("Leave Application"):
		return None
	try:
		n = _count("Leave Application", {"status": "Open"})
	except Exception:
		return None
	return {
		"key": "hr",
		"title": "HR (optional)",
		"meta": {"open_leave_applications": n},
		"table": {"headers": ["Metric", "Value"], "rows": [["Open Leave Applications", n]]},
	}


def _build_summary_md(company: str, sections: list, omitted: list) -> str:
	who = company or "your company"
	lines = [
		f"Here’s a quick look at how {who} is doing as of {today()}.",
		"",
	]
	for s in sections:
		meta = s.get("meta") or {}
		title = s.get("title") or s.get("key")
		key = s.get("key")
		if key == "receivables":
			lines.append(
				f"**Receivables** — {meta.get('open_count', 0)} open invoices "
				f"({meta.get('overdue_count', 0)} overdue, about {meta.get('overdue_amount', 0)} outstanding overdue)."
			)
		elif key == "payables":
			lines.append(
				f"**Payables** — {meta.get('open_count', 0)} open bills "
				f"({meta.get('overdue_count', 0)} overdue)."
			)
		elif key == "cash":
			if meta.get("note"):
				lines.append(f"**Cash / bank** — {meta['note']}.")
			else:
				lines.append(
					f"**Cash / bank** — {meta.get('account_count', 0)} accounts; "
					f"combined balance about {meta.get('total_balance', 0)}."
				)
		elif key == "stock":
			n = meta.get("low_count") or 0
			lines.append(
				f"**Stock** — {n} item(s) at low or zero qty"
				+ (" — worth a look." if n else " — looking fine from this scan.")
			)
		elif key == "crm":
			bits = []
			if "open_leads" in meta:
				bits.append(f"{meta['open_leads']} open leads")
			if "open_opportunities" in meta:
				bits.append(f"{meta['open_opportunities']} open opportunities")
			lines.append("**Sales / CRM** — " + (", ".join(bits) if bits else "no open pipeline visible") + ".")
		elif key == "projects":
			lines.append(
				f"**Projects / tasks** — {meta.get('open_projects', 0)} open projects, "
				f"{meta.get('open_tasks', 0)} open tasks"
				+ (f" ({meta.get('overdue_tasks', 0)} overdue)." if meta.get("overdue_tasks") else ".")
			)
		else:
			bits = [f"{k}: {v}" for k, v in meta.items() if v is not None and k != "note"]
			lines.append(f"**{title}** — " + (", ".join(bits) if bits else str(meta.get("note") or "ok")) + ".")
		lines.append("")
	if omitted:
		lines.append("_Skipped (no access or not installed):_ " + ", ".join(omitted))
	return "\n".join(lines)
