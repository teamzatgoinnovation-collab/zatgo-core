"""Hybrid search: ERP + Global + Vector + Metadata."""

from __future__ import annotations

import frappe

from zatgo_core.chat_ai.erpnext.metadata import search_metadata
from zatgo_core.chat_ai.erpnext.permissions import can_read, filter_readable


def retrieve(query: str, modes: list[str] | None = None, doctypes: list[str] | None = None) -> list[dict]:
	settings = _settings()
	modes = modes or _enabled_modes(settings)
	hits: list[dict] = []
	if "erp" in modes:
		hits.extend(erp_search(query, doctypes=doctypes))
	if "global" in modes:
		hits.extend(global_search(query))
	if "vector" in modes:
		hits.extend(vector_search(query, doctypes=doctypes))
	if "metadata" in modes:
		for m in search_metadata(query):
			hits.append({"source": "metadata", "doctype": m.get("doctype") or "DocType", "name": m.get("name") or m.get("fieldname"), "snippet": m, "score": 0.4})
	return _dedupe(hits)


def erp_search(query: str, doctype: str | None = None, doctypes: list[str] | None = None, filters: dict | None = None) -> list[dict]:
	targets = []
	if doctype:
		targets = [doctype]
	elif doctypes:
		targets = doctypes
	else:
		# common searchable doctypes that exist
		for dt in ("Task", "Project", "Customer", "Item", "Sales Invoice", "Issue", "Lead"):
			if frappe.db.exists("DocType", dt) and frappe.has_permission(dt, "read"):
				targets.append(dt)
	hits = []
	for dt in targets:
		try:
			rows = frappe.get_list(
				dt,
				filters=filters or {},
				or_filters=[[frappe.get_meta(dt).title_field or "name", "like", f"%{query}%"]] if query else None,
				fields=["name", frappe.get_meta(dt).title_field or "name as title"],
				limit_page_length=20,
			)
		except Exception:
			try:
				rows = frappe.get_list(dt, filters=[["name", "like", f"%{query}%"]], fields=["name"], limit_page_length=20)
			except Exception:
				rows = []
		for r in rows:
			if can_read(dt, r.name):
				hits.append({"source": "erp", "doctype": dt, "name": r.name, "snippet": r, "score": 0.8})
	return hits


def global_search(query: str) -> list[dict]:
	if not query:
		return []
	try:
		from frappe.utils.global_search import search as gs

		results = gs(query, limit=20) or []
	except Exception:
		results = []
	hits = []
	for r in results:
		dt = r.get("doctype") or r.get("doc_type")
		name = r.get("name") or r.get("id")
		if dt and name and can_read(dt, name):
			hits.append({"source": "global", "doctype": dt, "name": name, "snippet": r.get("content") or r, "score": 0.7})
	return hits


def vector_search(query: str, doctypes: list[str] | None = None, top_k: int | None = None) -> list[dict]:
	settings = _settings()
	if not settings.get("enable_vector_search"):
		return []
	if not frappe.db.exists("DocType", "AI Search Index"):
		return []
	# Without embedding call in hot path when no provider configured — keyword fallback on chunks
	filters = {}
	rows = frappe.get_all(
		"AI Search Index",
		filters=filters,
		fields=["ref_doctype", "ref_name", "chunk_text", "name"],
		limit_page_length=200,
	)
	q = (query or "").lower()
	scored = []
	for r in rows:
		if doctypes and r.ref_doctype not in doctypes:
			continue
		text = (r.chunk_text or "").lower()
		if q and q not in text:
			continue
		if can_read(r.ref_doctype, r.ref_name):
			scored.append({"source": "vector", "doctype": r.ref_doctype, "name": r.ref_name, "snippet": r.chunk_text, "score": 0.6})
	k = top_k or int(settings.get("vector_top_k") or 8)
	return scored[:k]


def _enabled_modes(settings: dict) -> list[str]:
	modes = []
	if settings.get("enable_erp_search", 1):
		modes.append("erp")
	if settings.get("enable_global_search", 1):
		modes.append("global")
	if settings.get("enable_vector_search"):
		modes.append("vector")
	if settings.get("enable_metadata_search", 1):
		modes.append("metadata")
	return modes or ["erp"]


def _settings() -> dict:
	try:
		return frappe.get_single("Chat AI Settings").as_dict()
	except Exception:
		return {}


def _dedupe(hits: list[dict]) -> list[dict]:
	seen = set()
	out = []
	for h in hits:
		key = (h.get("doctype"), h.get("name"), h.get("source"))
		if key in seen:
			continue
		seen.add(key)
		out.append(h)
	return out
