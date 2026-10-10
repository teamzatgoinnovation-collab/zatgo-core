"""Merge intelligent defaults into tool arguments before execution (no Frappe)."""

from __future__ import annotations

from zatgo_core.chat_ai.core.tool_router.spec import ToolSpec

_FIELD_ALIASES = {
	"company": ("company", "company_name"),
	"warehouse": ("warehouse", "set_warehouse", "source_warehouse", "target_warehouse"),
	"branch": ("branch",),
	"currency": ("currency",),
	"fiscal_year": ("fiscal_year",),
}


def enrich_tool_args(tool: ToolSpec | None, args: dict | None, context: dict | None) -> dict:
	"""Fill missing args from context intelligent_defaults; never override explicit values."""
	args = dict(args or {})
	context = context or {}
	defaults = (context.get("intelligent_defaults") or {}).copy()
	if not defaults:
		return args

	values = args.get("values")
	if isinstance(values, dict):
		args["values"] = _merge_defaults(values, defaults)
	else:
		args = _merge_defaults(args, defaults)

	return args


def _merge_defaults(target: dict, defaults: dict) -> dict:
	out = dict(target)
	for key, val in defaults.items():
		if not val:
			continue
		aliases = _FIELD_ALIASES.get(key, (key,))
		for alias in aliases:
			if alias not in out or out.get(alias) in (None, ""):
				out[alias] = val
		if key == "company" and "company" not in out:
			out["company"] = val
	return out
