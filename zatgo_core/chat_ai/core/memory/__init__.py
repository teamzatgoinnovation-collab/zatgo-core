"""Conversation / entity memory (backend-agnostic structures)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConversationMemory:
	messages: list[dict] = field(default_factory=list)
	summary: str = ""
	entities: dict[str, Any] = field(default_factory=dict)

	def add(self, role: str, content: str, **extra):
		self.messages.append({"role": role, "content": content, **extra})

	def window(self, max_messages: int = 40) -> list[dict]:
		if max_messages <= 0:
			return list(self.messages)
		return self.messages[-max_messages:]

	def set_entity(self, key: str, value: Any):
		self.entities[key] = value

	def update_entities_from_tool(self, tool_name: str, result: Any):
		if not isinstance(result, dict):
			return
		# Soft conventions
		for key in ("name", "doctype"):
			if key in result:
				self.entities[f"last_{key}"] = result[key]
		if "doctype" in result and "name" in result:
			dt = str(result["doctype"]).lower().replace(" ", "_")
			self.entities[f"current_{dt}"] = result["name"]
			self.entities["last_document"] = {"doctype": result["doctype"], "name": result["name"]}
