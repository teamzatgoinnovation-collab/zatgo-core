"""Saved My Work filter presets (per-user defaults JSON)."""

from __future__ import annotations

import json
import re
from uuid import uuid4

import frappe

from zatgo_core.tracker.api.response import fail, ok

_KEY = "tracker_my_work_filters"
_SCOPES = frozenset({"mine", "team", "both"})


def _blank() -> dict:
	return {"last": None, "presets": []}


def _load() -> dict:
	raw = frappe.defaults.get_user_default(_KEY)
	if not raw:
		return _blank()
	try:
		data = json.loads(raw)
		if not isinstance(data, dict):
			return _blank()
		data.setdefault("last", None)
		data.setdefault("presets", [])
		if not isinstance(data["presets"], list):
			data["presets"] = []
		return data
	except Exception:
		return _blank()


def _save(data: dict) -> None:
	frappe.defaults.set_user_default(_KEY, json.dumps(data, separators=(",", ":")))


def _normalize_filter(
	*,
	scope: str | None = None,
	project: str | None = None,
	status: str | None = None,
) -> dict | None:
	scope = (scope or "mine").strip().lower()
	if scope not in _SCOPES:
		return None
	return {
		"scope": scope,
		"project": (project or "").strip() or None,
		"status": (status or "").strip() or None,
	}


@frappe.whitelist()
def get_presets():
	data = _load()
	return ok({"last": data.get("last"), "presets": data.get("presets") or []})


@frappe.whitelist()
def set_last(scope: str = "mine", project: str | None = None, status: str | None = None):
	filt = _normalize_filter(scope=scope, project=project, status=status)
	if not filt:
		return fail("bad_scope", "scope must be mine, team, or both")
	data = _load()
	data["last"] = filt
	_save(data)
	return ok({"last": filt, "presets": data["presets"]})


@frappe.whitelist()
def save_preset(
	name: str,
	scope: str = "mine",
	project: str | None = None,
	status: str | None = None,
):
	name = (name or "").strip()
	if not name or not re.match(r"^[\w \-]{1,40}$", name):
		return fail("bad_name", "name required (1–40 letters/numbers/spaces/-)")
	filt = _normalize_filter(scope=scope, project=project, status=status)
	if not filt:
		return fail("bad_scope", "scope must be mine, team, or both")
	preset = {"id": str(uuid4())[:8], "name": name, **filt}
	data = _load()
	presets = [p for p in data["presets"] if p.get("name") != name]
	presets.append(preset)
	data["presets"] = presets
	data["last"] = filt
	_save(data)
	return ok({"last": filt, "presets": presets})


@frappe.whitelist()
def delete_preset(id: str | None = None, name: str | None = None):
	if not id and not name:
		return fail("bad_request", "id or name required")
	data = _load()
	before = len(data["presets"])
	if id:
		data["presets"] = [p for p in data["presets"] if p.get("id") != id]
	else:
		data["presets"] = [p for p in data["presets"] if p.get("name") != name]
	_save(data)
	return ok(
		{
			"last": data.get("last"),
			"presets": data["presets"],
			"removed": before != len(data["presets"]),
		}
	)
