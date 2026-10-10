import frappe
from zatgo_core.chat_ai.core.tool_router.spec import CATEGORY_READ, CATEGORY_WRITE, ToolSpec
from zatgo_core.chat_ai.erpnext.permissions import require

def get_tools():
	tools = []
	if frappe.db.exists("DocType", "Lead"):
		tools += [
			ToolSpec(name="get_leads", description="List leads", category=CATEGORY_READ, skill="crm", required_doctypes=["Lead"], supported_doctypes=["Lead"],
				parameters={"type":"object","properties":{"limit":{"type":"integer"}}},
				handler=lambda limit=20: [{"doctype":"Lead","name":r.name} for r in frappe.get_list("Lead", fields=["name"], limit_page_length=limit)]),
			ToolSpec(name="create_lead", description="Create lead", category=CATEGORY_WRITE, skill="crm", confirmation_required=True, required_doctypes=["Lead"], supported_doctypes=["Lead"],
				parameters={"type":"object","properties":{"values":{"type":"object"}},"required":["values"]},
				handler=lambda values: _create("Lead", values)),
		]
	return tools

def _create(doctype, values):
	require(doctype, "create")
	doc = frappe.get_doc({"doctype": doctype, **(values or {})}); doc.insert()
	return {"doctype": doctype, "name": doc.name}
