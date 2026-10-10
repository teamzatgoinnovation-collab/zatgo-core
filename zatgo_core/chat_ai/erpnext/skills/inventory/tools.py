import frappe
from zatgo_core.chat_ai.core.tool_router.spec import CATEGORY_READ, ToolSpec
from zatgo_core.chat_ai.erpnext.permissions import require

def get_tools():
	return [
		ToolSpec(name="get_items", description="List items", category=CATEGORY_READ, skill="inventory",
			supported_doctypes=["Item"], required_doctypes=["Item"],
			parameters={"type":"object","properties":{"limit":{"type":"integer"}}},
			handler=lambda limit=20: _list("Item", limit)),
		ToolSpec(name="get_stock", description="Get stock qty for item", category=CATEGORY_READ, skill="inventory",
			supported_doctypes=["Item"], required_doctypes=["Item"],
			parameters={"type":"object","properties":{"item_code":{"type":"string"}},"required":["item_code"]},
			handler=_get_stock),
	]

def _list(doctype, limit=20):
	if not frappe.db.exists("DocType", doctype): return []
	require(doctype, "read")
	return [{"doctype": doctype, "name": r.name} for r in frappe.get_list(doctype, fields=["name"], limit_page_length=limit)]

def _get_stock(item_code):
	require("Item", "read", item_code)
	if frappe.db.exists("DocType", "Bin"):
		rows = frappe.get_all("Bin", filters={"item_code": item_code}, fields=["warehouse", "actual_qty"])
		return {"item_code": item_code, "bins": rows}
	return {"item_code": item_code, "bins": []}
