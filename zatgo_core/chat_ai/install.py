"""Setup for Chat AI (formerly the chat_ai app) — run by
services/bundled_apps.py where ZG System Settings -> Enable Chat AI is on,
never on other sites. Desk entries are tagged app "zatgo_core" and found by
the sidebar they link to, never by app (that would match all of zatgo_core)."""

from __future__ import annotations

import frappe

SIDEBAR_NAMES = ("Chat AI", "AI Admin")


def has_app_permission():
	"""Shown on Apps screen for System Manager / Chat AI Manager."""
	return bool(
		frappe.db.exists("Module Def", "Chat AI")
		and (
			"System Manager" in frappe.get_roles()
			or "Chat AI Manager" in frappe.get_roles()
			or "Chat AI User" in frappe.get_roles()
		)
	)


def bootstrap():
	_ensure_module_map()
	_ensure_module_def()
	_ensure_roles()
	_ensure_admin_roles()
	_ensure_settings()
	_sanitize_provider_settings()
	_ensure_desk_entry()
	_bootstrap_connectors()
	_load_plugins()
	try:
		frappe.clear_cache()
	except Exception:
		frappe.log_error(title="chat_ai clear_cache")


def _bootstrap_connectors():
	try:
		from zatgo_core.chat_ai.core.tool_sources.health import bootstrap_lifecycle_statuses

		bootstrap_lifecycle_statuses()
	except Exception:
		frappe.log_error(title="chat_ai connector bootstrap")


def _ensure_module_map():
	"""Invalidate cached app/module maps so Chat AI resolves after install."""
	try:
		frappe.cache.delete_value("app_modules")
		frappe.cache.delete_value("all_apps")
		try:
			frappe.client_cache.delete_value("installed_app_modules")
		except Exception:
			pass
		frappe.setup_module_map(include_all_apps=True)
	except Exception:
		frappe.log_error(title="chat_ai module map refresh")


def _ensure_module_def():
	if frappe.db.exists("Module Def", "Chat AI"):
		doc = frappe.get_doc("Module Def", "Chat AI")
		if doc.app_name != "zatgo_core":
			doc.app_name = "zatgo_core"
			doc.save(ignore_permissions=True)
		return
	frappe.get_doc(
		{
			"doctype": "Module Def",
			"module_name": "Chat AI",
			"app_name": "zatgo_core",
		}
	).insert(ignore_permissions=True)


def _ensure_roles():
	for role in ("Chat AI User", "Chat AI Manager"):
		if not frappe.db.exists("Role", role):
			doc = frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1})
			doc.insert(ignore_permissions=True)


def _ensure_admin_roles():
	"""Give Administrator both Chat AI roles so Desk works without manual assignment."""
	if not frappe.db.exists("User", "Administrator"):
		return
	user = frappe.get_doc("User", "Administrator")
	existing = {r.role for r in user.roles}
	changed = False
	for role in ("Chat AI User", "Chat AI Manager"):
		if role not in existing:
			user.append("roles", {"role": role})
			changed = True
	if changed:
		user.save(ignore_permissions=True)


def _ensure_settings():
	if not frappe.db.exists("DocType", "Chat AI Settings"):
		return
	try:
		doc = frappe.get_single("Chat AI Settings")
		# Touch defaults if brand-new empty single
		if not doc.provider:
			doc.provider = "OpenAI"
		# Default Model stays blank unless the operator sets it
		if not getattr(doc, "default_language", None):
			doc.default_language = "en"
		# Bootstrap v4 once for upgrades from v1–v3 (flag keyed to v0.2 release)
		if not frappe.db.get_global("chat_ai_prompt_v4_bootstrapped_02"):
			cur = getattr(doc, "prompt_bundle_version", None) or ""
			if cur in ("", "v1", "v2", "v3"):
				doc.prompt_bundle_version = "v4"
			frappe.db.set_global("chat_ai_prompt_v4_bootstrapped_02", "1")
		elif not getattr(doc, "prompt_bundle_version", None):
			doc.prompt_bundle_version = "v4"
		# Check fields migrate as 0; turn voice on once unless already bootstrapped
		if not frappe.db.get_global("chat_ai_voice_bootstrapped"):
			doc.enable_voice_input = 1
			doc.enable_voice_output = 1
			doc.auto_speak_replies = 1
			frappe.db.set_global("chat_ai_voice_bootstrapped", "1")
		if not frappe.db.get_global("chat_ai_auto_speak_bootstrapped"):
			# Speak on in settings → automatic speech by default
			if int(getattr(doc, "enable_voice_output", 0) or 0):
				doc.auto_speak_replies = 1
			frappe.db.set_global("chat_ai_auto_speak_bootstrapped", "1")
		if not frappe.db.get_global("chat_ai_voicebox_bootstrapped"):
			doc.tts_engine = "Voicebox"
			if not getattr(doc, "voicebox_url", None):
				doc.voicebox_url = "http://127.0.0.1:17493"
			frappe.db.set_global("chat_ai_voicebox_bootstrapped", "1")
		# Platform v0.2.5 defaults (Check fields migrate as 0)
		if not frappe.db.get_global("chat_ai_platform_025_bootstrapped"):
			doc.enable_plugin_discovery = 1
			doc.enable_event_stream = 1
			doc.enable_artifact_store = 1
			if not getattr(doc, "max_parallel_tools", None):
				doc.max_parallel_tools = 1
			if getattr(doc, "tool_max_retries", None) in (None, 0) and not frappe.db.get_global(
				"chat_ai_platform_025_retries_touched"
			):
				doc.tool_max_retries = 1
			frappe.db.set_global("chat_ai_platform_025_bootstrapped", "1")
		doc.save(ignore_permissions=True)
	except Exception:
		frappe.log_error(title="chat_ai ensure settings")


def _sanitize_provider_settings():
	"""Fix common misconfigs left from older installs / Custom→localhost."""
	if not frappe.db.exists("DocType", "Chat AI Settings"):
		return
	try:
		doc = frappe.get_single("Chat AI Settings")
		key = ""
		try:
			key = doc.get_password("api_key") or ""
		except Exception:
			key = ""
		endpoint = (doc.api_endpoint or "").strip()
		provider = doc.provider or ""
		changed = False

		if key.startswith("sk-or-") and provider != "OpenRouter":
			doc.provider = "OpenRouter"
			changed = True
			provider = "OpenRouter"

		if provider == "OpenRouter":
			if not endpoint or "127.0.0.1" in endpoint or "localhost" in endpoint:
				doc.api_endpoint = ""
				changed = True

		if provider == "Custom OpenAI-compatible" and (
			not endpoint or "127.0.0.1" in endpoint or "localhost" in endpoint
		):
			# Avoid silent Connection refused to local dummy port
			doc.api_endpoint = ""
			if key.startswith("sk-or-"):
				doc.provider = "OpenRouter"
			changed = True

		if changed:
			doc.save(ignore_permissions=True)
	except Exception:
		frappe.log_error(title="chat_ai sanitize provider")


def _ensure_desk_entry():
	"""Ensure Workspace Sidebar + a top-level Desktop Icon that does not depend on App logos.

	Frappe v16 App icons fall back to plain text when /assets/<app>/images is missing
	(common on frappe_docker until assets are linked). Prefer a Link icon with a lucide name.
	"""
	try:
		_ensure_sidebar()
		# Workspace Sidebar created from workspace sync — pin app name
		if frappe.db.exists("Workspace Sidebar", "AI Admin"):
			sb = frappe.get_doc("Workspace Sidebar", "AI Admin")
			if sb.app != "zatgo_core":
				sb.app = "zatgo_core"
				sb.save(ignore_permissions=True)

		# Collapse broken App-type "Chat AI" + nested "AI Admin" into one top-level Link.
		# Frappe v16 permits Link icons only when label.lower() == Workspace Sidebar name.lower().
		sidebar_name = "AI Admin"
		if frappe.db.exists("Workspace Sidebar", "Chat AI"):
			sidebar_name = "Chat AI"
		elif frappe.db.exists("Workspace Sidebar", "AI Admin"):
			# Prefer Desk label "Chat AI" — rename sidebar so boot key matches.
			try:
				frappe.rename_doc("Workspace Sidebar", "AI Admin", "Chat AI", force=True, show_alert=False)
				sidebar_name = "Chat AI"
			except Exception:
				sidebar_name = "AI Admin"

		desk_label = sidebar_name
		for name in _chat_ai_icons():
			doc = frappe.get_doc("Desktop Icon", name)
			dirty = False
			if doc.app != "zatgo_core":
				doc.app = "zatgo_core"
				dirty = True
			if (doc.logo_url or "").startswith("/assets/chat_ai/"):
				doc.logo_url = doc.logo_url.replace("/assets/chat_ai/", "/assets/zatgo_core/chat_ai/", 1)
				dirty = True
			if doc.label != desk_label:
				doc.label = desk_label
				dirty = True
			if doc.icon_type != "Link":
				doc.icon_type = "Link"
				dirty = True
			if doc.link_type != "Workspace Sidebar":
				doc.link_type = "Workspace Sidebar"
				dirty = True
			if doc.link_to != sidebar_name:
				doc.link_to = sidebar_name
				dirty = True
			if doc.icon != "bot":
				doc.icon = "bot"
				dirty = True
			if doc.parent_icon:
				doc.parent_icon = ""
				dirty = True
			if doc.hidden:
				doc.hidden = 0
				dirty = True
			if dirty:
				doc.flags.ignore_links = True
				doc.save(ignore_permissions=True)

		if not _chat_ai_icons():
			icon = frappe.get_doc(
				{
					"doctype": "Desktop Icon",
					"label": desk_label,
					"app": "zatgo_core",
					"icon_type": "Link",
					"link_type": "Workspace Sidebar",
					"link_to": sidebar_name,
					"icon": "bot",
					"standard": 1,
					"hidden": 0,
				}
			)
			icon.flags.ignore_links = True
			icon.insert(ignore_permissions=True)

		# Deduplicate: keep one top-level icon for chat_ai
		keepers = frappe.get_all(
			"Desktop Icon",
			filters={"name": ["in", _chat_ai_icons() or [""]], "label": desk_label},
			pluck="name",
			order_by="modified desc",
		)
		keep = keepers[0] if keepers else None
		for name in _chat_ai_icons():
			if name == keep:
				continue
			try:
				frappe.delete_doc("Desktop Icon", name, force=1, ignore_permissions=True)
			except Exception:
				pass
	except Exception:
		frappe.log_error(title="chat_ai desk entry")


def _ensure_sidebar():
	"""The "Chat AI" Workspace Sidebar for the AI Admin workspace, made the way
	Frappe's create_workspace_sidebar_for_workspaces() does at app install --
	which no longer runs for this module (it is switched on later, per site),
	and which would also make sidebars for every other public workspace."""
	if not frappe.db.exists("Workspace", "AI Admin"):
		return
	if any(frappe.db.exists("Workspace Sidebar", n) for n in SIDEBAR_NAMES):
		return
	workspace = frappe.get_doc("Workspace", "AI Admin")
	items = [{"label": "Home", "link_to": "AI Admin", "link_type": "Workspace", "type": "Link", "idx": 0}]
	for idx, s in enumerate(workspace.shortcuts or [], start=1):
		items.append({"label": s.label, "link_to": s.link_to, "link_type": s.type, "type": "Link", "idx": idx})
	sidebar = frappe.get_doc(
		{
			"doctype": "Workspace Sidebar",
			"title": "Chat AI",
			"header_icon": "bot",
			"module": "Chat AI",
			"app": "zatgo_core",
			"items": items,
		}
	)
	sidebar.flags.ignore_links = True
	sidebar.insert(ignore_permissions=True)


def _load_plugins():
	try:
		from zatgo_core.chat_ai.plugin.loader import load_all

		load_all()
	except Exception:
		frappe.log_error(title="chat_ai plugin load")


def _chat_ai_icons() -> list[str]:
	"""Desktop Icons of Chat AI: linked to its sidebar, or still tagged with
	the old app name."""
	linked = frappe.get_all(
		"Desktop Icon", filters={"link_to": ["in", list(SIDEBAR_NAMES)]}, pluck="name"
	)
	legacy = frappe.get_all("Desktop Icon", filters={"app": "chat_ai"}, pluck="name")
	return list(dict.fromkeys(linked + legacy))
