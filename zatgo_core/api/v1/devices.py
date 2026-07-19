"""Device token register / push send (hub-owned).

Paths:
  zatgo_core.api.v1.devices.register_token
  zatgo_core.api.v1.devices.unregister_token
  zatgo_core.api.v1.devices.send_to_user
"""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe.utils import now_datetime

from zatgo_core.api.response import fail, ok
from zatgo_core.api.validators import parse_json_dict, require_str
from zatgo_core.utils.logging import log_api

DOCTYPE = "ZG Device Token"
SETTINGS = "ZG Notification Settings"


@frappe.whitelist()
def register_token(token: str, platform: str | None = None, app_id: str | None = None) -> dict[str, Any]:
	token = require_str(token, "token")
	user = frappe.session.user
	if not user or user == "Guest":
		return fail("auth", "Login required")
	platform = (platform or "other").strip().lower()
	if platform not in ("android", "ios", "web", "desktop", "other"):
		platform = "other"
	app_id = (app_id or "unknown").strip() or "unknown"
	log_api("devices.register_token", user=user, platform=platform, app_id=app_id)

	existing = frappe.db.get_value(DOCTYPE, {"token": token}, "name")
	now = now_datetime()
	if existing:
		doc = frappe.get_doc(DOCTYPE, existing)
		doc.user = user
		doc.platform = platform
		doc.app_id = app_id
		doc.last_seen = now
		doc.save(ignore_permissions=True)
	else:
		doc = frappe.get_doc(
			{
				"doctype": DOCTYPE,
				"user": user,
				"token": token,
				"platform": platform,
				"app_id": app_id,
				"last_seen": now,
			}
		)
		doc.insert(ignore_permissions=True)
	return ok({"name": doc.name, "user": user, "platform": platform, "app_id": app_id})


@frappe.whitelist()
def unregister_token(token: str) -> dict[str, Any]:
	token = require_str(token, "token")
	user = frappe.session.user
	name = frappe.db.get_value(DOCTYPE, {"token": token}, "name")
	if not name:
		return ok({"removed": False})
	owner = frappe.db.get_value(DOCTYPE, name, "user")
	if owner != user and "System Manager" not in frappe.get_roles(user):
		return fail("forbidden", "Not your device token")
	frappe.delete_doc(DOCTYPE, name, ignore_permissions=True)
	return ok({"removed": True, "name": name})


@frappe.whitelist()
def send_to_user(
	user: str,
	title: str,
	body: str,
	data: Any = None,
) -> dict[str, Any]:
	"""Notify a user: Notification Log + optional FCM. Never raises to callers."""
	try:
		user = require_str(user, "user")
		title = require_str(title, "title")
		body = (body or "").strip() or title
		payload = parse_json_dict(data) if data not in (None, "") else {}
		if not isinstance(payload, dict):
			payload = {}

		push_enabled = 0
		server_key = None
		try:
			push_enabled = int(frappe.db.get_single_value(SETTINGS, "push_enabled") or 0)
			ns = frappe.get_single(SETTINGS)
			if hasattr(ns, "get_password"):
				server_key = ns.get_password("fcm_server_key", raise_exception=False) or None
		except Exception:
			pass
		if not server_key:
			server_key = frappe.conf.get("fcm_server_key")

		# Always leave an in-app trail when Notification Log exists
		try:
			frappe.get_doc(
				{
					"doctype": "Notification Log",
					"subject": title,
					"email_content": body,
					"for_user": user,
					"type": "Alert",
					"document_type": payload.get("doctype"),
					"document_name": payload.get("name"),
					"from_user": frappe.session.user,
				}
			).insert(ignore_permissions=True)
		except Exception:
			pass

		if not push_enabled:
			return ok({"sent": 0, "skipped": "push_disabled"})

		tokens = frappe.get_all(DOCTYPE, filters={"user": user}, pluck="token")
		if not tokens:
			return ok({"sent": 0, "skipped": "no_tokens"})

		sent = 0
		if server_key:
			for tok in tokens:
				if _fcm_send(server_key, tok, title, body, payload):
					sent += 1
		else:
			frappe.logger("zatgo_core").info(
				"push enabled but no fcm_server_key; notified %s via Notification Log only",
				user,
			)
		return ok({"sent": sent, "tokens": len(tokens)})
	except Exception:
		frappe.log_error(title="send_to_user failed", message=frappe.get_traceback())
		return ok({"sent": 0, "skipped": "error"})


def _fcm_send(server_key: str, token: str, title: str, body: str, data: dict) -> bool:
	try:
		import requests

		# Flatten data values to strings (FCM requirement)
		flat = {str(k): str(v) for k, v in (data or {}).items()}
		resp = requests.post(
			"https://fcm.googleapis.com/fcm/send",
			headers={
				"Authorization": f"key={server_key}",
				"Content-Type": "application/json",
			},
			data=json.dumps(
				{
					"to": token,
					"notification": {"title": title, "body": body},
					"data": flat,
					"priority": "high",
				}
			),
			timeout=8,
		)
		return resp.status_code == 200
	except Exception:
		frappe.log_error(title="FCM send failed", message=frappe.get_traceback())
		return False
