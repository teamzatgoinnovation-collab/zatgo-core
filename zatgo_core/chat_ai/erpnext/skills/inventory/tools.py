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
		ToolSpec(name="stock_balance", category=CATEGORY_READ, skill="inventory",
			description="Stock on hand per item and warehouse (actual, reserved, projected quantity), highest quantity first. Optional warehouse / item filters.",
			supported_doctypes=["Bin"], required_doctypes=["Bin"],
			parameters={"type":"object","properties":{"warehouse":{"type":"string"},"item_code":{"type":"string"},"limit":{"type":"integer"}}},
			handler=_stock_balance),
		ToolSpec(name="low_stock_items", category=CATEGORY_READ, skill="inventory",
			description="Items whose projected quantity is below their reorder level (Item reorder rules), biggest shortage first. Optional warehouse filter.",
			supported_doctypes=["Bin", "Item"], required_doctypes=["Bin", "Item"],
			parameters={"type":"object","properties":{"warehouse":{"type":"string"},"limit":{"type":"integer"}}},
			handler=_low_stock_items),
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


MAX_ROWS = 100


def _clamp(limit, default=50):
	try:
		return max(1, min(int(limit or default), MAX_ROWS))
	except (TypeError, ValueError):
		return default


def _stock_balance(warehouse=None, item_code=None, limit=50):
	"""Permission-aware (get_list): a user only sees bins they may read."""
	require("Bin", "read")
	filters = {}
	if warehouse:
		filters["warehouse"] = warehouse
	if item_code:
		filters["item_code"] = item_code
	rows = frappe.get_list(
		"Bin", filters=filters, fields=["item_code", "warehouse", "actual_qty", "reserved_qty", "projected_qty"],
		order_by="actual_qty desc", limit_page_length=_clamp(limit),
	)
	return {"count": len(rows), "rows": rows, "truncated": len(rows) >= _clamp(limit)}


def _low_stock_items(warehouse=None, limit=50):
	"""Bins below the reorder level set on the Item (exact warehouse match), shortage first."""
	require("Bin", "read")
	require("Item", "read")
	bins = frappe.get_list(
		"Bin", filters={"warehouse": warehouse} if warehouse else {},
		fields=["item_code", "warehouse", "actual_qty", "projected_qty"], limit_page_length=5000,
	)
	rules = {}
	for r in frappe.get_all(
		"Item Reorder", filters={"parenttype": "Item"},
		fields=["parent", "warehouse", "warehouse_reorder_level", "warehouse_reorder_qty"], limit_page_length=20000,
	):
		rules[(r.parent, r.warehouse)] = r
	out = []
	for b in bins:
		rule = rules.get((b.item_code, b.warehouse))
		level = frappe.utils.flt(rule.warehouse_reorder_level) if rule else 0
		if rule and level > 0 and frappe.utils.flt(b.projected_qty) < level:
			out.append({
				"item_code": b.item_code, "warehouse": b.warehouse, "projected_qty": b.projected_qty,
				"actual_qty": b.actual_qty, "reorder_level": level, "reorder_qty": rule.warehouse_reorder_qty,
				"shortage": round(level - frappe.utils.flt(b.projected_qty), 3),
			})
	out.sort(key=lambda r: r["shortage"], reverse=True)
	n = _clamp(limit)
	return {"count": len(out), "rows": out[:n], "truncated": len(out) > n}
