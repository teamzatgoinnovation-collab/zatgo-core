"""MyBis builds some SQL from fixed fragments (column lists, join conditions, an item/party table name). That is safe only while
every fragment is chosen by the server from an allow-list and every client value is a bound parameter. This test makes that a
reviewed list: a new interpolation into SQL text fails here until someone has read where it comes from and added it below.
"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[2]
SERVICES = sorted((PACKAGE / "services" / "mybis").glob("*.py"))
API = sorted((PACKAGE / "api" / "v1" / "mybis").glob("*.py"))
SQL_WORDS = re.compile(r"\b(SELECT|FROM|WHERE|JOIN|ORDER BY|LIMIT|GROUP BY)\b")

# Each entry is reviewed: it is a module constant, a number, or a lookup in a dict/config the server owns (a validated
# dimension / side / kind / bucket), never text that arrived in a request.
REVIEWED = {
    # module constants and numbers
    "DEAD_DAYS", "OVERSTOCK_COVER_DAYS", "_GL_PERIOD", "_ITEM_TOTALS", "_LAST_OUT", "_OUT_90", "int(limit)",
    # fragments assembled from the allow-lists in breakdown.py / inventory.py / parties.py / forecasting.py / queries.py
    "_RANK_LABEL[by]", "amount", "base", "bucket", "c['doc']", "c['party']", "cat_expr", "cfg['doc']", "cfg['item']",
    "cfg['party']", "cfg['party_name']", "code_expr", "cost", "doc", "expr", "extra", "in_clause", "join", "key",
    "limit_sql", "name_expr", "order", "order_col", "select", "value", "where",
}


def _sql_interpolations(path: Path) -> list[tuple[str, int]]:
    source = path.read_text()
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.JoinedStr):
            text = "".join(v.value for v in node.values if isinstance(v, ast.Constant))
            if SQL_WORDS.search(text):
                found += [(ast.get_source_segment(source, v.value), node.lineno) for v in node.values if isinstance(v, ast.FormattedValue)]
    return found


class TestMyBisSqlSafety(unittest.TestCase):
    def test_every_interpolation_into_sql_text_is_reviewed(self) -> None:
        unreviewed = [f"{p.name}:{line}: {{{expr}}}" for p in SERVICES for expr, line in _sql_interpolations(p) if expr not in REVIEWED]
        self.assertEqual(unreviewed, [], "new text interpolated into SQL: read where it comes from, then add it to REVIEWED")

    def test_sql_text_is_never_built_with_percent_or_format(self) -> None:
        bad = []
        for p in SERVICES:
            source = p.read_text()
            for node in ast.walk(ast.parse(source)):
                text = None
                if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod) and isinstance(node.left, ast.Constant) and isinstance(node.left.value, str):
                    text = node.left.value
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "format" and isinstance(node.func.value, ast.Constant) and isinstance(node.func.value.value, str):
                    text = node.func.value.value
                if text and SQL_WORDS.search(text):
                    bad.append(f"{p.name}:{node.lineno}")
        self.assertEqual(bad, [])

    def test_endpoints_hold_no_sql_of_their_own(self) -> None:
        offenders = [p.name for p in API if "frappe.db.sql" in p.read_text() or "frappe.db.multisql" in p.read_text()]
        self.assertEqual(offenders, [], "SQL belongs in services/mybis so the guard and the scope are applied once")
