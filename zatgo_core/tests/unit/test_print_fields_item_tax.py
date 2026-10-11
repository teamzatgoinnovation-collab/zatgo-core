"""Per-line VAT on the print fields must follow item-wise tax detail, so a
0% (zero-rated) line next to a 15% line isn't given a share of the VAT."""

import json
import unittest

import frappe

from zatgo_core.events.print_fields import _item_wise_tax


def _doc(items, taxes):
    return frappe._dict(items=items, taxes=taxes)


class TestItemWiseTax(unittest.TestCase):
    def test_zero_rated_and_standard_lines(self):
        taxes = [
            frappe._dict(
                item_wise_tax_detail=json.dumps({"A": [15, 15.0], "B": [0, 0.0]})
            )
        ]
        wise = _item_wise_tax(_doc([], taxes))
        self.assertEqual(wise["A"], 15.0)
        self.assertEqual(wise["B"], 0)

    def test_multiple_tax_rows_sum_and_bad_json_ignored(self):
        taxes = [
            frappe._dict(item_wise_tax_detail={"A": [10, 10.0]}),
            frappe._dict(item_wise_tax_detail=json.dumps({"A": [5, 5.0]})),
            frappe._dict(item_wise_tax_detail="not json"),
            frappe._dict(item_wise_tax_detail=None),
        ]
        self.assertEqual(_item_wise_tax(_doc([], taxes)), {"A": 15.0})
