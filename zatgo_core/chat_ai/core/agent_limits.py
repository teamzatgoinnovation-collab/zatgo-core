"""Agent loop limits from settings dict."""

from __future__ import annotations
from dataclasses import dataclass


@dataclass
class AgentLimits:
	max_tool_calls: int = 12
	max_tool_rounds: int = 8
	max_iterations: int = 10
	max_retries: int = 2
	request_timeout_seconds: int = 120
	tool_timeout_seconds: int = 60
	max_tools_per_request: int = 24

	@classmethod
	def from_settings(cls, s: dict | None) -> "AgentLimits":
		s = s or {}
		def i(key, default):
			try:
				return int(s.get(key) or default)
			except (TypeError, ValueError):
				return default
		return cls(
			max_tool_calls=i("max_tool_calls", 12),
			max_tool_rounds=i("max_tool_rounds", 8),
			max_iterations=i("max_iterations", 10),
			max_retries=i("max_retries", 2),
			request_timeout_seconds=i("request_timeout_seconds", 120),
			tool_timeout_seconds=i("tool_timeout_seconds", 60),
			max_tools_per_request=i("max_tools_per_request", 24),
		)
