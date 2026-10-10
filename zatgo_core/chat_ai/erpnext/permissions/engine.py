"""Extended permission rules — only narrow Frappe permissions further."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class PermissionDecision:
	allowed: bool = True
	reason: str = ""


@dataclass
class PermissionRule:
	name: str
	fn: Callable[..., PermissionDecision]
	priority: int = 100


class PermissionEngine:
	_rules: list[PermissionRule] = []

	@classmethod
	def clear_rules(cls):
		cls._rules = []

	@classmethod
	def register_rule(cls, name: str, fn: Callable, *, priority: int = 100):
		cls._rules.append(PermissionRule(name=name, fn=fn, priority=priority))
		cls._rules.sort(key=lambda r: r.priority)
		return fn

	@classmethod
	def evaluate(cls, tool, args: dict | None = None, context: dict | None = None) -> PermissionDecision:
		args = args or {}
		context = context or {}
		# Base: Frappe DocType permission when tool declares supported_doctypes / args.doctype
		base = _base_frappe_check(tool, args)
		if not base.allowed:
			return base
		for rule in cls._rules:
			try:
				d = rule.fn(tool, args, context)
				if d is None:
					continue
				if isinstance(d, bool):
					d = PermissionDecision(allowed=d, reason="" if d else rule.name)
				if not d.allowed:
					return d
			except Exception as exc:
				return PermissionDecision(allowed=False, reason=str(exc))
		return PermissionDecision(allowed=True)


def _base_frappe_check(tool, args: dict) -> PermissionDecision:
	try:
		import frappe
	except Exception:
		return PermissionDecision(allowed=True)
	doctype = args.get("doctype")
	if not doctype and getattr(tool, "supported_doctypes", None):
		# don't block multi-doctype tools at gate
		return PermissionDecision(allowed=True)
	if not doctype:
		return PermissionDecision(allowed=True)
	ptype = "write" if getattr(tool, "category", "read") == "write" else "read"
	name = args.get("name")
	ok = frappe.has_permission(doctype, ptype, doc=name) if name else frappe.has_permission(doctype, ptype)
	if not ok:
		return PermissionDecision(allowed=False, reason=f"Not permitted to {ptype} {doctype}")
	# Role list on tool endpoint_ref is handled elsewhere; company narrowing optional
	company = args.get("company") or (context_company(context={}) if False else None)
	_ = company
	return PermissionDecision(allowed=True)


def context_company(context: dict | None = None) -> str | None:
	ctx = context or {}
	defaults = ctx.get("intelligent_defaults") or {}
	return defaults.get("company") or ctx.get("company")
