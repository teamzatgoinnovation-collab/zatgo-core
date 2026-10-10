import frappe
from zatgo_core.chat_ai.core.tool_router.spec import CATEGORY_READ, CATEGORY_WRITE, ToolSpec
from zatgo_core.chat_ai.erpnext.permissions import require

def get_tools():
	return [
		ToolSpec(name="get_sales_orders", description="List sales orders", category=CATEGORY_READ, skill="sales",
			supported_doctypes=["Sales Order"], required_doctypes=["Sales Order"],
			parameters={"type":"object","properties":{"limit":{"type":"integer"}}},
			handler=lambda limit=20: _list("Sales Order", limit=limit)),
		ToolSpec(name="create_sales_order", description="Create sales order", category=CATEGORY_WRITE, skill="sales",
			confirmation_required=True, supported_doctypes=["Sales Order"], required_doctypes=["Sales Order"],
			parameters={"type":"object","properties":{"values":{"type":"object"}},"required":["values"]},
			handler=lambda values: _create("Sales Order", values)),
		ToolSpec(name="get_customers", description="List customers", category=CATEGORY_READ, skill="sales",
			supported_doctypes=["Customer"], required_doctypes=["Customer"],
			parameters={"type":"object","properties":{"limit":{"type":"integer"}}},
			handler=lambda limit=20: _list("Customer", limit=limit)),
	]

def _list(doctype, limit=20):
	if not frappe.db.exists("DocType", doctype): return []
	require(doctype, "read")
	return [{"doctype": doctype, "name": r.name} for r in frappe.get_list(doctype, fields=["name"], limit_page_length=limit)]

def _create(doctype, values):
	require(doctype, "create")
	doc = frappe.get_doc({"doctype": doctype, **(values or {})}); doc.insert()
	return {"doctype": doctype, "name": doc.name}
