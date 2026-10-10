"""Indexer stub for vector search."""

from __future__ import annotations

import hashlib

import frappe


def index_document(doctype: str, name: str):
	if not frappe.db.exists("DocType", "AI Search Index"):
		return
	if not frappe.db.exists(doctype, name):
		return
	doc = frappe.get_doc(doctype, name)
	# Index title-like fields only
	chunks = []
	meta = frappe.get_meta(doctype)
	title = meta.title_field or "name"
	text = str(doc.get(title) or doc.name)
	chunks.append(text)
	for chunk in chunks:
		checksum = hashlib.sha256(f"{doctype}:{name}:{chunk}".encode()).hexdigest()
		existing = frappe.db.exists("AI Search Index", {"ref_doctype": doctype, "ref_name": name, "checksum": checksum})
		if existing:
			continue
		frappe.get_doc(
			{
				"doctype": "AI Search Index",
				"ref_doctype": doctype,
				"ref_name": name,
				"fieldname": title,
				"chunk_text": chunk,
				"checksum": checksum,
			}
		).insert(ignore_permissions=True)
