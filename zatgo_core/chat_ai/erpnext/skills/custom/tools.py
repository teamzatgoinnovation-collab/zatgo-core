from zatgo_core.chat_ai.core.tool_router.spec import CATEGORY_READ, ToolSpec
from zatgo_core.chat_ai.erpnext.metadata import get_meta

def get_tools():
	return [
		ToolSpec(name="describe_doctype", description="Describe DocType metadata", category=CATEGORY_READ, skill="custom",
			parameters={"type":"object","properties":{"doctype":{"type":"string"}},"required":["doctype"]},
			handler=lambda doctype: get_meta(doctype)),
	]
