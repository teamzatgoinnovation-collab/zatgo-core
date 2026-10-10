"""Artifact types and builder — durable + inline ContentBlock bridge."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

ARTIFACT_TYPES = (
	"markdown",
	"text",
	"json",
	"table",
	"chart",
	"code",
	"report",
	"plan",
	"checklist",
	"kanban",
	"timeline",
	"mermaid",
	"sql",
	"csv",
	"file",
	"image_ref",
	"links",
)


@dataclass
class Artifact:
	artifact_type: str
	title: str = ""
	content: Any = None
	metadata: dict = field(default_factory=dict)
	plugin: str = ""

	def to_dict(self) -> dict:
		return {
			"artifact_type": self.artifact_type,
			"title": self.title,
			"content": self.content,
			"metadata": self.metadata,
			"plugin": self.plugin,
		}


class ArtifactBuilder:
	"""Build Artifact list from tool results / ContentBlocks."""

	@staticmethod
	def from_tool_results(results: list[dict]) -> list[Artifact]:
		arts: list[Artifact] = []
		for r in results or []:
			if not r.get("ok"):
				continue
			data = r.get("data")
			tool = r.get("tool") or "tool"
			# Company status brief structured payload
			if isinstance(data, dict) and data.get("_artifact_sections"):
				arts.extend(ArtifactBuilder.from_status_brief(data))
				continue
			if isinstance(data, list) and data and isinstance(data[0], dict):
				headers = list(data[0].keys())
				rows = [[row.get(h) for h in headers] for row in data[:50]]
				arts.append(
					Artifact(
						artifact_type="table",
						title=tool,
						content={"headers": headers, "rows": rows},
					)
				)
			elif isinstance(data, dict):
				arts.append(
					Artifact(
						artifact_type="json",
						title=tool,
						content=data,
					)
				)
		return arts

	@staticmethod
	def from_status_brief(payload: dict) -> list[Artifact]:
		arts: list[Artifact] = []
		company = payload.get("company") or ""
		summary = payload.get("summary_md") or payload.get("executive_summary") or ""
		if summary:
			arts.append(
				Artifact(
					artifact_type="report",
					title=f"Company Status — {company}".strip(" —"),
					content={"markdown": summary},
					metadata={"company": company},
				)
			)
		for sec in payload.get("sections") or []:
			if not isinstance(sec, dict):
				continue
			title = sec.get("title") or sec.get("key") or "Section"
			table = sec.get("table")
			if table and isinstance(table, dict):
				arts.append(
					Artifact(
						artifact_type="table",
						title=title,
						content=table,
						metadata={"section": sec.get("key")},
					)
				)
			chart = sec.get("chart")
			if chart:
				arts.append(
					Artifact(
						artifact_type="chart",
						title=f"{title} chart",
						content=chart,
						metadata={"section": sec.get("key")},
					)
				)
		actions = payload.get("actions") or payload.get("checklist") or []
		if actions:
			arts.append(
				Artifact(
					artifact_type="checklist",
					title="Recommended next actions",
					content={"items": actions},
				)
			)
		return arts

	@staticmethod
	def from_content_blocks(blocks: list) -> list[Artifact]:
		arts: list[Artifact] = []
		for b in blocks or []:
			btype = getattr(b, "type", None) or (b.get("type") if isinstance(b, dict) else None)
			data = getattr(b, "data", None) if not isinstance(b, dict) else b.get("data")
			if not btype:
				continue
			mapped = btype if btype in ARTIFACT_TYPES else "json"
			arts.append(Artifact(artifact_type=mapped, title=btype, content=data))
		return arts


def persist_artifacts(
	*,
	session: str,
	message: str | None,
	artifacts: list[Artifact],
	user: str | None = None,
	publisher=None,
) -> list[str]:
	"""Insert AI Artifact rows; return names. No-op if DocType/settings off."""
	ids: list[str] = []
	try:
		import frappe
	except Exception:
		return ids
	if not frappe.db.exists("DocType", "AI Artifact"):
		return ids
	try:
		if not frappe.db.get_single_value("Chat AI Settings", "enable_artifact_store"):
			return ids
	except Exception:
		pass
	user = user or frappe.session.user
	for art in artifacts or []:
		try:
			content = art.content
			if not isinstance(content, str):
				content = json.dumps(content, default=str)
			doc = frappe.get_doc(
				{
					"doctype": "AI Artifact",
					"session": session,
					"message": message,
					"artifact_type": art.artifact_type,
					"title": art.title or art.artifact_type,
					"content": content,
					"metadata_json": json.dumps(art.metadata or {}, default=str),
					"plugin": art.plugin or "",
					"user": user,
				}
			)
			doc.insert(ignore_permissions=True)
			ids.append(doc.name)
			if publisher:
				publisher.artifact_created(doc.name, art.artifact_type, art.title or "")
		except Exception:
			frappe.log_error(title="chat_ai persist artifact")
	return ids
