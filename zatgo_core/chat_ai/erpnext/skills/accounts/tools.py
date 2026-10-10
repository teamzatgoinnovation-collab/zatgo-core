import frappe
from zatgo_core.chat_ai.core.tool_router.spec import CATEGORY_READ, ToolSpec
from zatgo_core.chat_ai.erpnext.permissions import require

def get_tools():
	return [
		ToolSpec(name="get_sales_invoices", description="List sales invoices", category=CATEGORY_READ, skill="accounts",
			supported_doctypes=["Sales Invoice"], required_doctypes=["Sales Invoice"],
			parameters={"type":"object","properties":{"filters":{"type":"object"},"limit":{"type":"integer"}}},
			handler=lambda filters=None, limit=20: _list("Sales Invoice", filters, limit)),
	]

def _list(doctype, filters=None, limit=20):
	if not frappe.db.exists("DocType", doctype): return []
	require(doctype, "read")
	fields = ["name"]
	meta = frappe.get_meta(doctype)
	for f in ("status", "outstanding_amount", "grand_total"):
		if meta.has_field(f):
			fields.append(f)
	return [{"doctype": doctype, **r} for r in frappe.get_list(doctype, filters=filters or {}, fields=fields, limit_page_length=limit)]
