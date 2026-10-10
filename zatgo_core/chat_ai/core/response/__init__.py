"""Response builder — structured assistant output."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ContentBlock:
	type: str  # markdown|table|links|chart|badge|status|plan
	data: Any = None


@dataclass
class AssistantResponse:
	markdown: str = ""
	blocks: list[ContentBlock] = field(default_factory=list)
	needs_confirmation: bool = False
	confirmation_message: str = ""
	pending_tool: str = ""
	pending_args: dict = field(default_factory=dict)
	needs_plan_approval: bool = False
	pending_plan: list = field(default_factory=list)
	pending_assumptions: list = field(default_factory=list)
	confirmation_token: str = ""

	def to_content_json(self) -> dict:
		return {
			"markdown": self.markdown,
			"blocks": [{"type": b.type, "data": b.data} for b in self.blocks],
			"needs_confirmation": self.needs_confirmation,
			"confirmation_message": self.confirmation_message,
			"pending_tool": self.pending_tool,
			"pending_args": self.pending_args,
			"needs_plan_approval": self.needs_plan_approval,
			"pending_plan": self.pending_plan,
			"pending_assumptions": self.pending_assumptions,
			"confirmation_token": self.confirmation_token,
		}


def build_from_tool_results(results: list[dict], *, preface: str = "") -> AssistantResponse:
	parts = []
	if preface:
		parts.append(preface)
	blocks: list[ContentBlock] = []
	for r in results:
		if not r.get("ok"):
			parts.append(f"**Error** (`{r.get('tool')}`): {r.get('error')}")
			continue
		data = r.get("data")
		tool = r.get("tool") or "tool"
		if isinstance(data, list) and data and isinstance(data[0], dict):
			headers = list(data[0].keys())
			rows = [[row.get(h) for h in headers] for row in data[:50]]
			blocks.append(ContentBlock(type="table", data={"headers": headers, "rows": rows}))
			parts.append(f"### {tool}\n_{len(data)} row(s)_")
			# doc links
			links = []
			for row in data[:20]:
				if row.get("doctype") and row.get("name"):
					links.append({"doctype": row["doctype"], "name": row["name"]})
				elif row.get("name") and r.get("doctype"):
					links.append({"doctype": r["doctype"], "name": row["name"]})
			if links:
				blocks.append(ContentBlock(type="links", data=links))
		elif isinstance(data, dict):
			if data.get("doctype") and data.get("name"):
				blocks.append(
					ContentBlock(
						type="links",
						data=[{"doctype": data["doctype"], "name": data["name"]}],
					)
				)
			parts.append(f"### {tool}\n```json\n{_safe_json(data)}\n```")
		else:
			parts.append(f"### {tool}\n{data}")
	return AssistantResponse(markdown="\n\n".join(parts), blocks=blocks)


def clarification(question: str) -> AssistantResponse:
	return AssistantResponse(markdown=question or "Could you provide more details?")


def confirmation(message: str, tool: str, args: dict, *, token: str = "") -> AssistantResponse:
	return AssistantResponse(
		markdown=message,
		needs_confirmation=True,
		confirmation_message=message,
		pending_tool=tool,
		pending_args=args or {},
		confirmation_token=token,
	)


def plan_approval(
	message: str,
	plan_steps: list[str],
	assumptions: list[str] | None = None,
	*,
	token: str = "",
) -> AssistantResponse:
	steps = [str(s) for s in (plan_steps or []) if s]
	assumptions = [str(a) for a in (assumptions or []) if a]
	md_parts = [message or "Here is the plan:"]
	if assumptions:
		md_parts.append("**Assumptions:**\n" + "\n".join(f"- {a}" for a in assumptions))
	if steps:
		md_parts.append("**Plan:**\n" + "\n".join(f"{i + 1}. {s}" for i, s in enumerate(steps)))
	md_parts.append("\nReply **OK** to continue or Cancel.")
	blocks = []
	if steps:
		blocks.append(ContentBlock(type="plan", data={"steps": steps, "assumptions": assumptions}))
	return AssistantResponse(
		markdown="\n\n".join(md_parts),
		needs_plan_approval=True,
		pending_plan=steps,
		pending_assumptions=assumptions,
		confirmation_token=token,
		blocks=blocks,
	)


def _safe_json(data: Any) -> str:
	import json

	try:
		return json.dumps(data, indent=2, default=str)[:4000]
	except Exception:
		return str(data)[:4000]
