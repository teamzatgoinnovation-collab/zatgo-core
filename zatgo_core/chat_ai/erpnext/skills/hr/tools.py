import frappe
from zatgo_core.chat_ai.core.tool_router.spec import CATEGORY_READ, CATEGORY_WRITE, ToolSpec
from zatgo_core.chat_ai.erpnext.permissions import require
from zatgo_core.chat_ai.erpnext.workflows import apply_action

def get_tools():
	tools = [
		ToolSpec(name="get_employees", description="List employees", category=CATEGORY_READ, skill="hr", required_doctypes=["Employee"], supported_doctypes=["Employee"],
			parameters={"type":"object","properties":{"limit":{"type":"integer"}}},
			handler=lambda limit=20: _list("Employee", limit)),
	]
	if frappe.db.exists("DocType", "Leave Application"):
		tools += [
			ToolSpec(name="get_leave_requests", description="List leave applications", category=CATEGORY_READ, skill="hr", required_doctypes=["Leave Application"],
				parameters={"type":"object","properties":{"limit":{"type":"integer"}}},
				handler=lambda limit=20: _list("Leave Application", limit)),
			ToolSpec(name="approve_leave", description="Approve leave application", category=CATEGORY_WRITE, skill="hr", confirmation_required=True, required_doctypes=["Leave Application"],
				parameters={"type":"object","properties":{"name":{"type":"string"},"action":{"type":"string"}},"required":["name"]},
				handler=lambda name, action="Approve": apply_action("Leave Application", name, action)),
		]
	return tools

def _list(doctype, limit=20):
	if not frappe.db.exists("DocType", doctype): return []
	require(doctype, "read")
	return [{"doctype": doctype, "name": r.name} for r in frappe.get_list(doctype, fields=["name"], limit_page_length=limit)]
