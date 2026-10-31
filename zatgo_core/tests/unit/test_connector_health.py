"""The hourly connector health loop is one function for the REST, MCP and integration connectors (no database)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from zatgo_core.chat_ai.core.tool_sources import health


class TestConnectorHealth(unittest.TestCase):
    def test_each_enabled_connector_is_tested_and_one_failure_does_not_stop_the_rest(self) -> None:
        fake = MagicMock()
        fake.db.exists.return_value = True
        fake.get_all.return_value = ["A", "B", "C"]
        tester = MagicMock(side_effect=[None, RuntimeError("down"), None])
        with patch.object(health, "frappe", fake):
            health._check_connectors("AI MCP Server", tester, "mcp")
        self.assertEqual([c.args for c in tester.call_args_list], [("A",), ("B",), ("C",)])
        self.assertTrue(all(c.kwargs == {"persist": True} for c in tester.call_args_list))
        fake.log_error.assert_called_once_with(title="chat_ai mcp health B")
        filters = fake.get_all.call_args.kwargs["filters"]
        self.assertEqual(filters["enabled"], 1)
        self.assertEqual(filters["lifecycle_status"], ("in", ["Enabled", "Testing"]))

    def test_a_site_without_the_doctype_is_skipped(self) -> None:
        fake = MagicMock()
        fake.db.exists.return_value = False
        tester = MagicMock()
        with patch.object(health, "frappe", fake):
            health._check_connectors("AI REST Tool", tester, "rest")
        tester.assert_not_called()
        fake.get_all.assert_not_called()

    def test_the_three_entry_points_use_their_own_tester_and_log_label(self) -> None:
        with patch.object(health, "_check_connectors") as loop:
            health.check_all_connectors()
        got = [(c.args[0], c.args[1], c.args[2]) for c in loop.call_args_list]
        self.assertEqual(
            got,
            [
                ("AI REST Tool", health.test_rest_tool, "rest"),
                ("AI MCP Server", health.test_mcp_server, "mcp"),
                ("AI Integration Connector", health.test_integration, "integration"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
