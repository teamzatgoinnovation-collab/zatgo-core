import frappe
from zatgo_core.chat_ai.core.tool_router.spec import CATEGORY_READ, CATEGORY_WRITE, ToolSpec
from zatgo_core.chat_ai.erpnext.permissions import require


def get_tools():
	return [
		ToolSpec(name="get_projects", description="List projects", category=CATEGORY_READ, skill="projects",
			supported_doctypes=["Project"], required_doctypes=["Project"],
			parameters={"type":"object","properties":{"limit":{"type":"integer"}}},
			handler=lambda limit=20: _list("Project", limit=limit)),
		ToolSpec(name="get_tasks", description="List tasks", category=CATEGORY_READ, skill="projects",
			supported_doctypes=["Task"], required_doctypes=["Task"],
			parameters={"type":"object","properties":{"filters":{"type":"object"},"limit":{"type":"integer"}}},
			handler=lambda filters=None, limit=20: _list("Task", filters=filters, limit=limit)),
		ToolSpec(name="create_task", description="Create a task", category=CATEGORY_WRITE, skill="projects",
			confirmation_required=True, supported_doctypes=["Task"], required_doctypes=["Task"],
			parameters={"type":"object","properties":{"values":{"type":"object"}},"required":["values"]},
			handler=lambda values: _create("Task", values)),
		ToolSpec(name="assign_task", description="Assign task to a user", category=CATEGORY_WRITE, skill="projects",
			confirmation_required=True, supported_doctypes=["Task"], required_doctypes=["Task"],
			parameters={"type":"object","properties":{"name":{"type":"string"},"user":{"type":"string"}},"required":["name","user"]},
			handler=_assign_task),
	]


def _list(doctype, filters=None, limit=20):
	if not frappe.db.exists("DocType", doctype):
		return []
	require(doctype, "read")
	return [{"doctype": doctype, **r} for r in frappe.get_list(doctype, filters=filters or {}, fields=["name"], limit_page_length=limit)]


def _create(doctype, values):
	require(doctype, "create")
	doc = frappe.get_doc({"doctype": doctype, **(values or {})})
	doc.insert()
	return {"doctype": doctype, "name": doc.name}


def _assign_task(name, user):
	require("Task", "write", name)
	from frappe.desk.form.assign_to import add
	add({"assign_to": [user], "doctype": "Task", "name": name})
	return {"doctype": "Task", "name": name, "assigned_to": user}
