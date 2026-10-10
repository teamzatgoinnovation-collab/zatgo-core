import frappe
from zatgo_core.chat_ai.core.tool_router.spec import CATEGORY_READ, CATEGORY_WRITE, ToolSpec
from zatgo_core.chat_ai.erpnext.permissions import require

def get_tools():
	return [
		ToolSpec(name="get_purchase_orders", description="List purchase orders", category=CATEGORY_READ, skill="purchase",
			supported_doctypes=["Purchase Order"], required_doctypes=["Purchase Order"],
			parameters={"type":"object","properties":{"limit":{"type":"integer"}}},
			handler=lambda limit=20: _list("Purchase Order", limit)),
		ToolSpec(name="create_purchase_order", description="Create purchase order", category=CATEGORY_WRITE, skill="purchase",
			confirmation_required=True, supported_doctypes=["Purchase Order"], required_doctypes=["Purchase Order"],
			parameters={"type":"object","properties":{"values":{"type":"object"}},"required":["values"]},
			handler=lambda values: _create("Purchase Order", values)),
	]

def _list(doctype, limit=20):
	if not frappe.db.exists("DocType", doctype): return []
	require(doctype, "read")
	return [{"doctype": doctype, "name": r.name} for r in frappe.get_list(doctype, fields=["name"], limit_page_length=limit)]

def _create(doctype, values):
	require(doctype, "create")
	doc = frappe.get_doc({"doctype": doctype, **(values or {})}); doc.insert()
	return {"doctype": doctype, "name": doc.name}
