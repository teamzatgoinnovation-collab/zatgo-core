"""Unit tests for chat_ai core (no Frappe required for these)."""

from __future__ import annotations

import unittest

from zatgo_core.chat_ai.core.agent_limits import AgentLimits
from zatgo_core.chat_ai.core.planner import Plan, _parse_plan
from zatgo_core.chat_ai.core.providers.capabilities import Capabilities, negotiate
from zatgo_core.chat_ai.core.response import plan_approval
from zatgo_core.chat_ai.core.tool_router import ToolRouter
from zatgo_core.chat_ai.core.tool_router.spec import CATEGORY_READ, CATEGORY_WRITE, ConfirmationPolicy, ToolSpec
from zatgo_core.chat_ai.core.approval import is_plan_approval_text
from zatgo_core.chat_ai.core.tool_enrichment import enrich_tool_args


class TestCapabilities(unittest.TestCase):
	def test_negotiate_ok(self):
		caps = Capabilities(chat=True, tool_calling=True, streaming=True)
		r = negotiate(caps, "chat", "tool_calling")
		self.assertTrue(r.ok)
		self.assertEqual(r.missing, [])

	def test_negotiate_missing(self):
		caps = Capabilities(chat=True)
		r = negotiate(caps, "streaming")
		self.assertFalse(r.ok)
		self.assertIn("streaming", r.missing)


class TestConfirmation(unittest.TestCase):
	def test_write_requires_confirm_medium(self):
		policy = ConfirmationPolicy(require_confirmation_for_writes=True)
		tool = ToolSpec(name="create_sales_order", description="x", category=CATEGORY_WRITE)
		self.assertTrue(policy.needs_confirmation(tool, {}, risk_level="medium"))

	def test_low_risk_task_skips_confirm(self):
		policy = ConfirmationPolicy(require_confirmation_for_writes=True)
		tool = ToolSpec(name="create_task", description="x", category=CATEGORY_WRITE)
		self.assertFalse(policy.needs_confirmation(tool, {}, risk_level="low"))

	def test_high_risk_always_confirms(self):
		policy = ConfirmationPolicy(require_confirmation_for_writes=True)
		tool = ToolSpec(name="create_task", description="x", category=CATEGORY_WRITE)
		self.assertTrue(policy.needs_confirmation(tool, {}, risk_level="high"))

	def test_read_no_confirm(self):
		policy = ConfirmationPolicy()
		tool = ToolSpec(name="get_tasks", description="x", category=CATEGORY_READ)
		self.assertFalse(policy.needs_confirmation(tool, {}))

	def test_bulk_names_confirm(self):
		policy = ConfirmationPolicy()
		tool = ToolSpec(name="update_document", description="x", category=CATEGORY_WRITE)
		self.assertTrue(policy.needs_confirmation(tool, {"names": ["A", "B"]}, risk_level="low"))


class TestToolRouter(unittest.TestCase):
	def test_unknown_tool(self):
		router = ToolRouter([])
		r = router.run("nope", {})
		self.assertFalse(r.ok)

	def test_category_blocked(self):
		policy = ConfirmationPolicy(allowed_categories={CATEGORY_READ})
		tool = ToolSpec(
			name="create_x",
			description="x",
			category=CATEGORY_WRITE,
			handler=lambda: {"ok": True},
		)
		router = ToolRouter([tool], policy=policy)
		r = router.run("create_x", {})
		self.assertFalse(r.ok)
		self.assertFalse(r.permission_ok)

	def test_confirm_gate(self):
		tool = ToolSpec(
			name="create_x",
			description="x",
			category=CATEGORY_WRITE,
			confirmation_required=True,
			handler=lambda: {"ok": True},
		)
		router = ToolRouter([tool])
		r = router.run("create_x", {})
		self.assertTrue(r.needs_confirmation)
		r2 = router.run("create_x", {}, confirmed=True)
		self.assertTrue(r2.ok)


class TestEnrichment(unittest.TestCase):
	def test_enrich_does_not_override(self):
		tool = ToolSpec(name="create_document", description="x", category=CATEGORY_WRITE)
		ctx = {"intelligent_defaults": {"company": "Acme", "warehouse": "Stores - A"}}
		args = enrich_tool_args(tool, {"values": {"company": "Other"}}, ctx)
		self.assertEqual(args["values"]["company"], "Other")

	def test_enrich_fills_missing(self):
		tool = ToolSpec(name="create_document", description="x", category=CATEGORY_WRITE)
		ctx = {"intelligent_defaults": {"company": "Acme", "warehouse": "Stores - A"}}
		args = enrich_tool_args(tool, {"values": {"title": "Test"}}, ctx)
		self.assertEqual(args["values"]["company"], "Acme")
		self.assertEqual(args["values"]["warehouse"], "Stores - A")


class TestPlanner(unittest.TestCase):
	def test_parse_plan_extended_fields(self):
		raw = """{
			"intent": "create project",
			"is_simple_question": false,
			"risk_level": "high",
			"assumptions": ["Using Company: Acme"],
			"implementation_plan": ["Create Project", "Add tasks"],
			"needs_plan_approval": true,
			"needs_clarification": false,
			"candidate_skills": ["projects", "core"]
		}"""
		plan = _parse_plan(raw, ["projects", "core"], {"assumptions": []})
		self.assertTrue(plan.needs_plan_approval)
		self.assertEqual(plan.risk_level, "high")
		self.assertEqual(len(plan.implementation_plan), 2)
		# Routine "Using …" lines are stripped from chat-facing assumptions
		self.assertEqual(plan.assumptions, [])

	def test_parse_candidate_tools(self):
		raw = """{
			"intent": "create task",
			"candidate_skills": ["projects", "core"],
			"candidate_tools": ["create_task", "search", "unknown_tool"],
			"risk_level": "low",
			"is_simple_question": false,
			"needs_plan_approval": false,
			"needs_clarification": false
		}"""
		plan = _parse_plan(
			raw,
			["projects", "core"],
			{},
			available_tool_names=["create_task", "search", "list_documents"],
		)
		self.assertEqual(plan.candidate_tools, ["create_task", "search"])


class TestRestToolSpec(unittest.TestCase):
	def test_build_rest_tool_spec(self):
		from zatgo_core.chat_ai.core.tool_sources.rest import build_rest_tool_spec

		spec = build_rest_tool_spec(tool_name="get_weather", description="Weather")
		self.assertEqual(spec.source, "rest")
		self.assertEqual(spec.name, "get_weather")
		self.assertTrue(callable(spec.handler))
		openai = spec.to_openai_tool()
		self.assertEqual(openai["function"]["name"], "get_weather")


class TestAssistantModeResolve(unittest.TestCase):
	def test_form_context_document(self):
		from zatgo_core.chat_ai.core.assistant_mode import MODE_DOCUMENT, resolve_assistant_mode

		mode = resolve_assistant_mode(
			{"route": {"path": ["Form", "Task", "TASK-1"]}, "form": {"doctype": "Task", "name": "TASK-1"}},
			"update status",
		)
		self.assertEqual(mode, MODE_DOCUMENT)

	def test_analytics_keywords(self):
		from zatgo_core.chat_ai.core.assistant_mode import MODE_ANALYTICS, resolve_assistant_mode

		self.assertEqual(resolve_assistant_mode({}, "Show sales report summary"), MODE_ANALYTICS)

	def test_developer_keywords(self):
		from zatgo_core.chat_ai.core.assistant_mode import MODE_DEVELOPER, resolve_assistant_mode

		self.assertEqual(resolve_assistant_mode({}, "Explain the whitelist API for this DocType"), MODE_DEVELOPER)

	def test_admin_keywords(self):
		from zatgo_core.chat_ai.core.assistant_mode import MODE_ADMIN, resolve_assistant_mode

		self.assertEqual(resolve_assistant_mode({}, "Change role permissions for Sales User"), MODE_ADMIN)

	def test_default_erp(self):
		from zatgo_core.chat_ai.core.assistant_mode import MODE_ERP, normalize_mode, resolve_assistant_mode

		self.assertEqual(resolve_assistant_mode({}, "Create a task for tomorrow"), MODE_ERP)
		self.assertEqual(normalize_mode("Normal Chat"), MODE_ERP)



class TestStripUsingPreamble(unittest.TestCase):
	def test_strips_company_currency_fy(self):
		import importlib.util
		from pathlib import Path

		path = Path(__file__).resolve().parents[1] / "erpnext" / "context" / "defaults.py"
		spec = importlib.util.spec_from_file_location("chat_ai_defaults_under_test", path)
		mod = importlib.util.module_from_spec(spec)
		# defaults imports frappe; stub before exec
		import sys
		import types

		sys.modules.setdefault("frappe", types.SimpleNamespace(db=None, defaults=None, utils=None))
		spec.loader.exec_module(mod)
		sample = (
			"Using Company: erpZatgo.\n"
			"Using Currency: SAR (company default).\n"
			"Using Fiscal Year: 2026 (active).\n"
			"\n"
			"Hi there! How can I help you today?"
		)
		self.assertEqual(mod.strip_using_preamble(sample), "Hi there! How can I help you today?")
		self.assertEqual(
			mod.filter_user_visible_assumptions(
				["Using Company: X", "Using Currency: SAR", "Chose warehouse A over B"]
			),
			["Chose warehouse A over B"],
		)


class TestPlanApprovalResponse(unittest.TestCase):
	def test_plan_approval_shape(self):
		resp = plan_approval("Proceed?", ["Step 1", "Step 2"], ["Using Company: X"], token="abc")
		cj = resp.to_content_json()
		self.assertTrue(cj["needs_plan_approval"])
		self.assertEqual(cj["pending_plan"], ["Step 1", "Step 2"])
		self.assertEqual(cj["confirmation_token"], "abc")


class TestPlanApprovalText(unittest.TestCase):
	def test_ok_variants(self):
		self.assertTrue(is_plan_approval_text("OK"))
		self.assertTrue(is_plan_approval_text("yes"))
		self.assertFalse(is_plan_approval_text("maybe"))


class TestAgentLimits(unittest.TestCase):
	def test_from_settings(self):
		lim = AgentLimits.from_settings({"max_tool_calls": "5"})
		self.assertEqual(lim.max_tool_calls, 5)


class TestI18n(unittest.TestCase):
	def test_normalize_arabic(self):
		from zatgo_core.chat_ai.core.i18n import get_language, normalize_language

		self.assertEqual(normalize_language("ar"), "ar")
		self.assertEqual(normalize_language("Arabic"), "ar")
		self.assertEqual(get_language("ar")["dir"], "rtl")

	def test_malayalam_prompt(self):
		from zatgo_core.chat_ai.core.i18n import language_prompt

		self.assertIn("Malayalam", language_prompt("ml"))


class TestPluginManifest(unittest.TestCase):
	def test_validate(self):
		from zatgo_core.chat_ai.plugin.manifest import validate_manifest

		m = validate_manifest({"name": "x", "version": "1.0.0"}, app="demo")
		self.assertEqual(m.name, "x")
		self.assertEqual(m.app, "demo")


class TestArtifacts(unittest.TestCase):
	def test_status_brief_builder(self):
		from zatgo_core.chat_ai.core.artifacts import ArtifactBuilder

		arts = ArtifactBuilder.from_tool_results(
			[
				{
					"ok": True,
					"tool": "company_status_brief",
					"data": {
						"_artifact_sections": True,
						"company": "Acme",
						"summary_md": "# Status",
						"sections": [
							{
								"key": "stock",
								"title": "Low Stock",
								"table": {"headers": ["Item"], "rows": [["A"]]},
							}
						],
						"actions": ["Reorder A"],
					},
				}
			]
		)
		types = {a.artifact_type for a in arts}
		self.assertIn("report", types)
		self.assertIn("table", types)
		self.assertIn("checklist", types)


class TestEvents(unittest.TestCase):
	def test_chat_event_dict(self):
		from zatgo_core.chat_ai.core.events import ChatEvent

		e = ChatEvent(session="S", type="planning", data={"detail": "x"})
		d = e.to_dict()
		self.assertEqual(d["type"], "planning")
		self.assertEqual(d["session"], "S")
		self.assertTrue(d["ts"])


class TestPromptRegistry(unittest.TestCase):
	def test_compose(self):
		from zatgo_core.chat_ai.core.prompts.framework import PromptBundleRegistry

		PromptBundleRegistry.clear()
		PromptBundleRegistry.register_fragment("p", name="a", text="PLUGIN", priority=10)
		out = PromptBundleRegistry.compose("BASE", skill_prompts=["SKILL"])
		self.assertIn("BASE", out)
		self.assertIn("PLUGIN", out)
		self.assertIn("SKILL", out)


class TestPermissionEngine(unittest.TestCase):
	def test_rule_narrows(self):
		from zatgo_core.chat_ai.erpnext.permissions.engine import PermissionDecision, PermissionEngine
		from zatgo_core.chat_ai.core.tool_router.spec import CATEGORY_READ, ToolSpec

		PermissionEngine.clear_rules()
		PermissionEngine.register_rule(
			"deny_all",
			lambda tool, args, ctx: PermissionDecision(allowed=False, reason="nope"),
			priority=1,
		)
		tool = ToolSpec(name="t", description="x", category=CATEGORY_READ)
		d = PermissionEngine.evaluate(tool, {}, {})
		self.assertFalse(d.allowed)
		PermissionEngine.clear_rules()


class TestAssistantStatusIntent(unittest.TestCase):
	def test_company_status(self):
		from zatgo_core.chat_ai.core.assistant_mode import (
			MODE_ANALYTICS,
			is_company_status_intent,
			resolve_assistant_mode,
		)

		self.assertTrue(is_company_status_intent("what is my company status?"))
		self.assertEqual(resolve_assistant_mode({}, "company health check"), MODE_ANALYTICS)


class TestToolPipeline(unittest.TestCase):
	def test_pipeline_run(self):
		from zatgo_core.chat_ai.core.tool_pipeline import ToolPipeline
		from zatgo_core.chat_ai.core.tool_router.spec import CATEGORY_READ, ToolSpec

		tool = ToolSpec(
			name="ping",
			description="x",
			category=CATEGORY_READ,
			handler=lambda: {"ok": True},
		)
		pipe = ToolPipeline({"ping": tool}, max_retries=0)
		r = pipe.run(
			"ping",
			{},
			category_allowed_fn=lambda t: True,
			needs_confirmation_fn=lambda t, a, rl: False,
			progress_stage_fn=lambda t: "reading_erp",
		)
		self.assertTrue(r.ok)


if __name__ == "__main__":
	unittest.main()
