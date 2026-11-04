"""The pure parts of the MyBis daily report: which day a report covers and how a report reads as text. No database."""

from __future__ import annotations

import unittest
from datetime import date, datetime

from zatgo_core.services.mybis import daily_report

NA = {"available": False}


def _m(value):
    return {"value": value}


REPORT = {
    "sales": {"net_sales": _m(1200.5), "invoices": _m(4.0)},
    "purchases": {"net_purchases": _m(300.0), "invoices": _m(2.0)},
    "money": {"received": _m(900.0), "paid": _m(100.0), "net_cash": _m(800.0)},
    "receivable": _m(5000.0),
    "payable": _m(750.25),
}


class TestReportDate(unittest.TestCase):
    def test_evening_report_covers_today(self):
        self.assertEqual(daily_report.report_date(datetime(2026, 11, 4, 20, 5), 20), date(2026, 11, 4))
        self.assertEqual(daily_report.report_date(datetime(2026, 11, 4, 12, 0), 12), date(2026, 11, 4))

    def test_morning_report_covers_yesterday(self):
        self.assertEqual(daily_report.report_date(datetime(2026, 11, 4, 7, 0), 7), date(2026, 11, 3))
        self.assertEqual(daily_report.report_date(datetime(2026, 11, 1, 0, 0), 0), date(2026, 10, 31))


class TestLines(unittest.TestCase):
    def test_rows_in_order_with_counts_as_whole_numbers(self):
        rows = dict(daily_report.lines(REPORT))
        self.assertEqual(rows["Sales (net)"], "1,200.50")
        self.assertEqual(rows["Sales invoices"], "4")
        self.assertEqual(rows["Payable balance"], "750.25")
        self.assertEqual(len(daily_report.lines(REPORT)), 9)

    def test_unavailable_sections_read_as_a_dash(self):
        report = {**REPORT, "sales": NA, "money": {"received": NA, "paid": NA, "net_cash": NA}, "receivable": NA}
        rows = dict(daily_report.lines(report))
        self.assertEqual(rows["Sales (net)"], "—")
        self.assertEqual(rows["Received from customers"], "—")
        self.assertEqual(rows["Receivable balance"], "—")
        self.assertEqual(rows["Purchases (net)"], "300.00")

    def test_custom_money_format(self):
        rows = dict(daily_report.lines(REPORT, lambda v: f"SAR {v:.0f}"))
        self.assertEqual(rows["Paid to suppliers"], "SAR 100")
