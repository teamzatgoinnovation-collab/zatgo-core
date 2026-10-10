"""Load Chat AI Settings as a plain dict (passwords resolved)."""

from __future__ import annotations

import frappe


def get_settings_dict() -> dict:
	try:
		doc = frappe.get_single("Chat AI Settings")
	except Exception:
		return {}
	data = doc.as_dict()
	# Resolve passwords
	for field in ("api_key", "embedding_api_key"):
		try:
			data[field] = doc.get_password(field) if doc.get(field) else ""
		except Exception:
			data[field] = ""
	return data
