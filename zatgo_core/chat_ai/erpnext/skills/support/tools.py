import frappe
from zatgo_core.chat_ai.core.tool_router.spec import CATEGORY_READ, CATEGORY_WRITE, ToolSpec
from zatgo_core.chat_ai.erpnext.permissions import require

def get_tools():
	if not frappe.db.exists("DocType", "Issue"):
		return []
	return [
		ToolSpec(name="get_tickets", description="List issues", category=CATEGORY_READ, skill="support", required_doctypes=["Issue"],
			parameters={"type":"object","properties":{"limit":{"type":"integer"}}},
			handler=lambda limit=20: [{"doctype":"Issue","name":r.name} for r in frappe.get_list("Issue", fields=["name"], limit_page_length=limit)]),
		ToolSpec(name="create_issue", description="Create issue", category=CATEGORY_WRITE, skill="support", confirmation_required=True, required_doctypes=["Issue"],
			parameters={"type":"object","properties":{"values":{"type":"object"}},"required":["values"]},
			handler=lambda values: _create("Issue", values)),
	]

def _create(doctype, values):
	require(doctype, "create")
	doc = frappe.get_doc({"doctype": doctype, **(values or {})}); doc.insert()
	return {"doctype": doctype, "name": doc.name}
