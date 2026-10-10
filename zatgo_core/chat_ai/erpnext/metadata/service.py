"""Metadata Service — sole schema discovery API for the AI."""

from __future__ import annotations

import frappe
from frappe.utils import cint


def list_doctypes(module: str | None = None) -> list[dict]:
	filters = {"istable": 0}
	if module:
		filters["module"] = module
	rows = frappe.get_all("DocType", filters=filters, fields=["name", "module", "issingle", "is_submittable"], limit_page_length=500)
	return [r for r in rows if frappe.has_permission(r.name, "read")]


def get_meta(doctype: str) -> dict:
	if not frappe.has_permission(doctype, "read"):
		raise PermissionError(f"No read permission for {doctype}")
	meta = frappe.get_meta(doctype)
	fields = []
	for df in meta.fields:
		fields.append({
			"fieldname": df.fieldname,
			"label": df.label,
			"fieldtype": df.fieldtype,
			"options": df.options,
			"reqd": cint(df.reqd),
			"read_only": cint(df.read_only),
			"in_list_view": cint(df.in_list_view),
		})
	children = [
		{"fieldname": df.fieldname, "options": df.options}
		for df in meta.fields
		if df.fieldtype == "Table"
	]
	links = [
		{"fieldname": df.fieldname, "options": df.options}
		for df in meta.fields
		if df.fieldtype in ("Link", "Dynamic Link")
	]
	return {
		"doctype": doctype,
		"module": meta.module,
		"is_submittable": cint(meta.is_submittable),
		"issingle": cint(meta.issingle),
		"fields": fields,
		"child_tables": children,
		"links": links,
		"mandatory_fields": [f["fieldname"] for f in fields if f["reqd"]],
	}


def get_workflows(doctype: str) -> list[dict]:
	if not frappe.db.exists("DocType", "Workflow"):
		return []
	workflows = frappe.get_all("Workflow", filters={"document_type": doctype, "is_active": 1}, fields=["name", "workflow_name"])
	out = []
	for w in workflows:
		doc = frappe.get_doc("Workflow", w.name)
		out.append({
			"name": doc.name,
			"states": [{"state": s.state, "doc_status": s.doc_status} for s in doc.states],
			"transitions": [
				{"state": t.state, "action": t.action, "next_state": t.next_state, "allowed": t.allowed}
				for t in doc.transitions
			],
		})
	return out


def search_metadata(query: str) -> list[dict]:
	q = (query or "").lower().strip()
	if not q:
		return []
	hits = []
	for dt in frappe.get_all("DocType", filters={"istable": 0}, fields=["name", "module"], limit_page_length=1000):
		if not frappe.has_permission(dt.name, "read"):
			continue
		if q in dt.name.lower() or q in (dt.module or "").lower():
			hits.append({"type": "doctype", "name": dt.name, "module": dt.module})
			continue
		try:
			meta = frappe.get_meta(dt.name)
			for df in meta.fields:
				label = (df.label or "").lower()
				if q in df.fieldname.lower() or q in label:
					hits.append({"type": "field", "doctype": dt.name, "fieldname": df.fieldname, "label": df.label, "fieldtype": df.fieldtype})
					if len(hits) >= 50:
						return hits
		except Exception:
			continue
	return hits[:50]
