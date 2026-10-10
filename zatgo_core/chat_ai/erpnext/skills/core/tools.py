"""Core skill — generic DocType CRUD + hybrid search (fallback)."""

from __future__ import annotations

import frappe

from zatgo_core.chat_ai.core.skills import SkillSpec
from zatgo_core.chat_ai.core.tool_router.spec import CATEGORY_READ, CATEGORY_WRITE, ToolSpec
from zatgo_core.chat_ai.erpnext.metadata import get_meta, search_metadata
from zatgo_core.chat_ai.erpnext.permissions import require
from zatgo_core.chat_ai.erpnext.search import erp_search, global_search, retrieve, vector_search


def get_tools() -> list[ToolSpec]:
	return [
		ToolSpec(
			name="search",
			description="Hybrid search across ERP, global, vector, and metadata",
			category=CATEGORY_READ,
			skill="core",
			parameters={
				"type": "object",
				"properties": {
					"query": {"type": "string"},
					"modes": {"type": "array", "items": {"type": "string"}},
				},
				"required": ["query"],
			},
			handler=lambda query, modes=None: retrieve(query, modes=modes),
		),
		ToolSpec(
			name="erp_search",
			description="Permission-aware DocType field search",
			category=CATEGORY_READ,
			skill="core",
			parameters={
				"type": "object",
				"properties": {
					"query": {"type": "string"},
					"doctype": {"type": "string"},
				},
				"required": ["query"],
			},
			handler=lambda query, doctype=None: erp_search(query, doctype=doctype),
		),
		ToolSpec(
			name="global_search",
			description="Site-wide keyword search",
			category=CATEGORY_READ,
			skill="core",
			parameters={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
			handler=lambda query: global_search(query),
		),
		ToolSpec(
			name="vector_search",
			description="Semantic search over indexed chunks",
			category=CATEGORY_READ,
			skill="core",
			parameters={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
			handler=lambda query: vector_search(query),
		),
		ToolSpec(
			name="metadata_search",
			description="Search DocTypes and fields metadata",
			category=CATEGORY_READ,
			skill="core",
			parameters={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
			handler=lambda query: search_metadata(query),
		),
		ToolSpec(
			name="list_documents",
			description="List documents of a DocType with optional filters",
			category=CATEGORY_READ,
			skill="core",
			parameters={
				"type": "object",
				"properties": {
					"doctype": {"type": "string"},
					"filters": {"type": "object"},
					"fields": {"type": "array", "items": {"type": "string"}},
					"limit": {"type": "integer"},
				},
				"required": ["doctype"],
			},
			handler=_list_documents,
		),
		ToolSpec(
			name="get_document",
			description="Get a document by doctype and name",
			category=CATEGORY_READ,
			skill="core",
			parameters={
				"type": "object",
				"properties": {"doctype": {"type": "string"}, "name": {"type": "string"}},
				"required": ["doctype", "name"],
			},
			handler=_get_document,
		),
		ToolSpec(
			name="create_document",
			description="Create a document",
			category=CATEGORY_WRITE,
			skill="core",
			confirmation_required=True,
			parameters={
				"type": "object",
				"properties": {"doctype": {"type": "string"}, "values": {"type": "object"}},
				"required": ["doctype", "values"],
			},
			handler=_create_document,
		),
		ToolSpec(
			name="update_document",
			description="Update fields on a document",
			category=CATEGORY_WRITE,
			skill="core",
			confirmation_required=True,
			parameters={
				"type": "object",
				"properties": {
					"doctype": {"type": "string"},
					"name": {"type": "string"},
					"values": {"type": "object"},
				},
				"required": ["doctype", "name", "values"],
			},
			handler=_update_document,
		),
		ToolSpec(
			name="submit_document",
			description="Submit a submittable document",
			category=CATEGORY_WRITE,
			skill="core",
			confirmation_required=True,
			parameters={
				"type": "object",
				"properties": {"doctype": {"type": "string"}, "name": {"type": "string"}},
				"required": ["doctype", "name"],
			},
			handler=_submit_document,
		),
		ToolSpec(
			name="get_doctype_meta",
			description="Get DocType metadata (fields, links, workflows)",
			category=CATEGORY_READ,
			skill="core",
			parameters={"type": "object", "properties": {"doctype": {"type": "string"}}, "required": ["doctype"]},
			handler=lambda doctype: get_meta(doctype),
		),
	]


def _list_documents(doctype: str, filters=None, fields=None, limit: int = 20):
	require(doctype, "read")
	rows = frappe.get_list(doctype, filters=filters or {}, fields=fields or ["name"], limit_page_length=limit or 20)
	return [{"doctype": doctype, **r} for r in rows]


def _get_document(doctype: str, name: str):
	require(doctype, "read", name)
	doc = frappe.get_doc(doctype, name)
	data = doc.as_dict()
	data["doctype"] = doctype
	return data


def _create_document(doctype: str, values: dict):
	require(doctype, "create")
	doc = frappe.get_doc({"doctype": doctype, **(values or {})})
	doc.insert()
	return {"doctype": doctype, "name": doc.name}


def _update_document(doctype: str, name: str, values: dict):
	require(doctype, "write", name)
	doc = frappe.get_doc(doctype, name)
	doc.update(values or {})
	doc.save()
	return {"doctype": doctype, "name": doc.name}


def _submit_document(doctype: str, name: str):
	require(doctype, "submit", name)
	doc = frappe.get_doc(doctype, name)
	doc.submit()
	return {"doctype": doctype, "name": doc.name, "docstatus": doc.docstatus}


def register() -> SkillSpec:
	return SkillSpec(
		name="core",
		label="Core",
		description="Generic document operations and hybrid search",
		tools=get_tools(),
		prompt="Use core tools for generic CRUD and search when no domain skill fits.",
	)
