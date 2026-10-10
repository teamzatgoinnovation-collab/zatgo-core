"""Tool specifications, categories, and confirmation policy (backend-agnostic)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


CATEGORY_READ = "read"
CATEGORY_WRITE = "write"
CATEGORY_ADMIN = "admin"

# Low-risk writes: single safe creates — skip confirmation when risk_level is low
LOW_RISK_TOOLS = frozenset(
	{
		"create_task",
		"create_lead",
		"create_issue",
		"rename_document",
	}
)


@dataclass
class ToolSpec:
	name: str
	description: str
	parameters: dict = field(default_factory=dict)  # JSON Schema
	handler: Callable[..., Any] | None = None
	source: str = "python"  # erp|plugin|rest|mcp|python
	category: str = CATEGORY_READ
	skill: str = "core"
	required_doctypes: list[str] = field(default_factory=list)
	required_apps: list[str] = field(default_factory=list)
	confirmation_required: bool = False
	permissions: list[str] = field(default_factory=list)
	examples: list[str] = field(default_factory=list)
	supported_doctypes: list[str] = field(default_factory=list)
	endpoint_ref: str = ""
	mcp_server: str = ""
	mcp_tool: str = ""

	def to_openai_tool(self) -> dict:
		return {
			"type": "function",
			"function": {
				"name": self.name,
				"description": self.description,
				"parameters": self.parameters
				or {"type": "object", "properties": {}, "additionalProperties": True},
			},
		}


@dataclass
class ConfirmationPolicy:
	require_confirmation_for_writes: bool = True
	confirm_delete: bool = True
	confirm_cancel: bool = True
	confirm_submit: bool = True
	confirm_workflow: bool = True
	confirm_financial: bool = True
	allowed_categories: set[str] = field(default_factory=lambda: {CATEGORY_READ, CATEGORY_WRITE})

	@classmethod
	def from_settings(cls, s: dict | None) -> "ConfirmationPolicy":
		s = s or {}
		cats = s.get("allowed_tool_categories") or "read,write"
		if isinstance(cats, str):
			allowed = {c.strip().lower() for c in cats.replace("\\n", ",").split(",") if c.strip()}
		else:
			allowed = set(cats)
		return cls(
			require_confirmation_for_writes=bool(s.get("require_confirmation_for_writes", 1)),
			confirm_delete=bool(s.get("confirm_delete", 1)),
			confirm_cancel=bool(s.get("confirm_cancel", 1)),
			confirm_submit=bool(s.get("confirm_submit", 1)),
			confirm_workflow=bool(s.get("confirm_workflow", 1)),
			confirm_financial=bool(s.get("confirm_financial", 1)),
			allowed_categories=allowed or {CATEGORY_READ, CATEGORY_WRITE},
		)

	def category_allowed(self, category: str) -> bool:
		return (category or CATEGORY_READ).lower() in self.allowed_categories

	def needs_confirmation(
		self,
		tool: ToolSpec,
		args: dict | None = None,
		*,
		risk_level: str = "medium",
	) -> bool:
		args = args or {}
		risk = (risk_level or "medium").lower()
		name = (tool.name or "").lower()
		action = str(args.get("action") or args.get("operation") or "").lower()

		# High risk from planner always confirms
		if risk == "high":
			return True

		# Bulk operations
		if "bulk" in name:
			return True
		names = args.get("names") or args.get("documents") or []
		if isinstance(names, list) and len(names) > 1:
			return True

		if tool.confirmation_required and name not in LOW_RISK_TOOLS:
			return True
		if tool.category == CATEGORY_ADMIN:
			return True

		if self.confirm_delete and ("delete" in name or action == "delete"):
			return True
		if self.confirm_cancel and ("cancel" in name or action == "cancel"):
			return True
		if self.confirm_submit and ("submit" in name or action == "submit"):
			return True
		if self.confirm_workflow and (
			"approve" in name or "reject" in name or "workflow" in name
		):
			return True
		if self.confirm_financial and any(
			x in name for x in ("invoice", "payment", "journal", "payroll")
		):
			return True

		# Low risk: whitelisted single creates skip confirmation
		if risk == "low" and name in LOW_RISK_TOOLS:
			return False
		if tool.category == CATEGORY_READ:
			return False

		if self.require_confirmation_for_writes and tool.category == CATEGORY_WRITE:
			return True
		return False


@dataclass
class ToolResult:
	ok: bool
	data: Any = None
	error: str = ""
	needs_confirmation: bool = False
	confirmation_message: str = ""
	latency_ms: int = 0
	permission_ok: bool = True
