from zatgo_core.chat_ai.core.tool_router.spec import CATEGORY_READ, CATEGORY_WRITE, ToolSpec
from zatgo_core.chat_ai.erpnext.workflows import apply_action, list_actions

def get_tools():
	return [
		ToolSpec(name="list_approval_actions", description="List approval actions for a document",
			category=CATEGORY_READ, skill="workflow",
			parameters={"type":"object","properties":{"doctype":{"type":"string"},"name":{"type":"string"}},"required":["doctype","name"]},
			handler=lambda doctype, name: list_actions(doctype, name)),
		ToolSpec(name="approve_document", description="Approve document via Approval Engine",
			category=CATEGORY_WRITE, skill="workflow", confirmation_required=True,
			parameters={"type":"object","properties":{"doctype":{"type":"string"},"name":{"type":"string"},"action":{"type":"string"}},"required":["doctype","name"]},
			handler=lambda doctype, name, action="Approve": apply_action(doctype, name, action)),
		ToolSpec(name="reject_document", description="Reject document via Approval Engine",
			category=CATEGORY_WRITE, skill="workflow", confirmation_required=True,
			parameters={"type":"object","properties":{"doctype":{"type":"string"},"name":{"type":"string"},"action":{"type":"string"},"comment":{"type":"string"}},"required":["doctype","name"]},
			handler=lambda doctype, name, action="Reject", comment=None: apply_action(doctype, name, action, comment)),
	]
