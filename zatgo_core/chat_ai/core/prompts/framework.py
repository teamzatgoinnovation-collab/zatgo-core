"""Prompt bundle inheritance — base → plugin fragments → mode."""

from __future__ import annotations

from pathlib import Path


class PromptBundleRegistry:
	"""Plugins contribute named markdown fragments with optional extends/priority."""

	_fragments: dict[str, list[dict]] = {}

	@classmethod
	def clear(cls):
		cls._fragments = {}

	@classmethod
	def register_fragment(
		cls,
		plugin: str,
		*,
		name: str,
		text: str,
		extends: str = "",
		priority: int = 100,
	):
		cls._fragments.setdefault(plugin, []).append(
			{
				"name": name,
				"text": text,
				"extends": extends,
				"priority": int(priority or 100),
			}
		)

	@classmethod
	def register_plugin_dir(cls, plugin: str, path: str):
		p = Path(path)
		if not p.is_dir():
			return
		for f in sorted(p.glob("*.md")):
			cls.register_fragment(
				plugin,
				name=f.stem,
				text=f.read_text(encoding="utf-8", errors="ignore"),
				priority=100,
			)

	@classmethod
	def compose(cls, base_text: str, *, mode_text: str = "", skill_prompts: list[str] | None = None) -> str:
		parts = [base_text or ""]
		if mode_text:
			parts.append(mode_text)
		# Plugin fragments by priority
		all_frags: list[dict] = []
		for frags in cls._fragments.values():
			all_frags.extend(frags)
		all_frags.sort(key=lambda x: x.get("priority", 100))
		for frag in all_frags:
			t = (frag.get("text") or "").strip()
			if t:
				parts.append(t)
		for p in skill_prompts or []:
			if p:
				parts.append(p)
		return "\n\n".join(parts)


def get_prompt_text_composed(
	settings: dict,
	skill_prompts: list[str] | None = None,
	*,
	base_loader=None,
) -> str:
	"""Compose using registry; fall back to orchestrator loader if provided."""
	if base_loader:
		base = base_loader(settings, skill_prompts=None)
	else:
		base = "You are an ERPNext AI Assistant."
	# base_loader already includes mode; still append plugin chain
	plugin_only = PromptBundleRegistry.compose("", skill_prompts=skill_prompts)
	if plugin_only.strip():
		return base + "\n\n" + plugin_only
	if skill_prompts:
		extra = "\n\n".join(p for p in skill_prompts if p)
		return base + (("\n\n" + extra) if extra else "")
	return base
