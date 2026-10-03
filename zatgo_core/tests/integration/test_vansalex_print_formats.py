"""VanSale print formats: the 80mm thermal page and read-only printing.

Covers setup/ensure_print_formats.py as rendered by Frappe's own PDF
pipeline, and the vansalex ``orders.pdf`` endpoint the app prints through:
- "VanSale Tax Invoice 80mm" asks wkhtmltopdf for an 80mm-wide page (Frappe
  reads page size from a ``.print-format`` rule, not CSS @page — the old
  format rendered on A4);
- a return prints as a CREDIT NOTE in both the 80mm and the A4 format;
- the A4 "Total Gross" is the pre-discount total;
- printing (any format, any number of times) writes nothing: no GL, stock
  ledger or Payment Entry rows, and the invoice itself is unchanged.
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import random_string
from frappe.utils.pdf import read_options_from_html

from zatgo_core.api.v1.vansalex.orders import pdf as orders_pdf
from zatgo_core.services.vansalex_service import create_order, create_sales_return
from zatgo_core.setup.ensure_print_formats import (
    PRINT_FORMAT_80MM_NAME,
    PRINT_FORMAT_NAME,
    ensure_print_formats,
)
from zatgo_core.tests.integration._fixtures import (
    get_or_create_cash_mode_of_payment,
    get_or_create_test_company,
)


class TestVansalexPrintFormats(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        ensure_print_formats()
        cls.company = get_or_create_test_company()
        cls.cash_account = frappe.db.get_value(
            "Account", {"company": cls.company, "account_type": "Cash", "is_group": 0}, "name"
        )
        get_or_create_cash_mode_of_payment(cls.company, cls.cash_account)
        cls.warehouse = cls._make_warehouse("VanSalePrintTest")
        cls.item_code = cls._make_stocked_item(cls.warehouse, qty=1000)
        cls.customer = cls._make_customer(f"Print Test {random_string(8)}")
        cls.user = cls._make_van_user(cls.warehouse)

    def tearDown(self) -> None:
        frappe.set_user("Administrator")

    # -- fixtures (mirrors test_vansalex_settings.py) ------------------------

    @classmethod
    def _make_warehouse(cls, label: str) -> str:
        abbr = frappe.db.get_value("Company", cls.company, "abbr")
        name = f"{label} - {abbr}" if abbr else label
        if frappe.db.exists("Warehouse", name):
            return name
        doc = frappe.get_doc({"doctype": "Warehouse", "warehouse_name": label, "company": cls.company})
        doc.insert(ignore_permissions=True)
        return doc.name

    @classmethod
    def _make_stocked_item(cls, warehouse: str, qty: float) -> str:
        code = f"VANSALE-PRINT-{random_string(6).upper()}"
        frappe.get_doc(
            {
                "doctype": "Item",
                "item_code": code,
                # Long on purpose: the 80mm layout must wrap it, not clip it.
                "item_name": f"{code} Premium Assorted Family Pack Extra Large Edition",
                "item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
                "stock_uom": "Nos",
                "is_stock_item": 1,
            }
        ).insert(ignore_permissions=True)
        frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "stock_entry_type": "Material Receipt",
                "company": cls.company,
                "items": [{"item_code": code, "qty": qty, "t_warehouse": warehouse, "basic_rate": 10}],
            }
        ).insert(ignore_permissions=True).submit()
        return code

    @classmethod
    def _make_customer(cls, name: str) -> str:
        doc = frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_name": name,
                "customer_type": "Individual",
                "customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
                "territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
            }
        )
        doc.insert(ignore_permissions=True)
        return doc.name

    @classmethod
    def _make_van_user(cls, warehouse: str) -> str:
        email = f"vansale.print.test.{random_string(6).lower()}@zatgo.test"
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "VanSale",
                "last_name": "PrintTest",
                "send_welcome_email": 0,
                "roles": [{"role": "VanSale User"}],
            }
        ).insert(ignore_permissions=True)
        frappe.get_doc(
            {
                "doctype": "ZG Van Sale Profile",
                "user": email,
                "enabled": 1,
                "user_type": "Field User",
                "warehouse": warehouse,
                "allow_credit_sales": "Yes",
            }
        ).insert(ignore_permissions=True)
        return email

    def _sell(self, payment_type: str = "Cash", **kwargs) -> str:
        frappe.set_user(self.user)
        res = create_order(
            client_id=f"test-print-{random_string(8)}",
            customer=self.customer,
            items=[{"item_code": self.item_code, "qty": 3, "rate": 10}],
            payment_type=payment_type,
            **kwargs,
        )
        frappe.set_user("Administrator")
        return res["data"]["erp_name"]

    def _return(self, against: str) -> str:
        frappe.set_user(self.user)
        res = create_sales_return(
            client_id=f"test-print-ret-{random_string(8)}",
            return_against=against,
            items=[{"item_code": self.item_code, "qty": 1}],
        )
        frappe.set_user("Administrator")
        return res["data"]["erp_name"]

    @staticmethod
    def _html(invoice: str, fmt: str) -> str:
        return frappe.get_print("Sales Invoice", invoice, print_format=fmt)

    # -- 80mm ------------------------------------------------------------------

    def test_80mm_requests_an_80mm_roll_page(self) -> None:
        html = self._html(self._sell(), PRINT_FORMAT_80MM_NAME)
        _, options = read_options_from_html(html)
        self.assertEqual(options.get("page-width"), "80mm")
        self.assertTrue(str(options.get("page-height", "")).endswith("mm"))
        self.assertGreater(int(str(options["page-height"])[:-2]), 80)
        self.assertNotIn("@page", frappe.db.get_value("Print Format", PRINT_FORMAT_80MM_NAME, "css") or "")

    def test_80mm_cash_invoice_shows_totals_and_payment(self) -> None:
        name = self._sell(discount_percentage=10)
        si = frappe.get_doc("Sales Invoice", name)
        html = self._html(name, PRINT_FORMAT_80MM_NAME)
        self.assertIn("SIMPLIFIED TAX INVOICE", html)
        self.assertNotIn("CREDIT NOTE", html)
        self.assertIn("Premium Assorted Family Pack Extra Large Edition", html)
        self.assertIn("Discount (10", html)
        self.assertIn(f"{si.total:,.2f}", html)  # Subtotal, before discount
        self.assertIn(f"{si.grand_total:,.2f}", html)
        self.assertIn("CASH", html)
        self.assertIn("Paid (", html)  # the auto-created cash Payment Entry

    def test_80mm_credit_invoice_shows_balance_due(self) -> None:
        name = self._sell(payment_type="Credit")
        si = frappe.get_doc("Sales Invoice", name)
        html = self._html(name, PRINT_FORMAT_80MM_NAME)
        self.assertIn("CREDIT", html)
        self.assertNotIn("Paid (", html)
        self.assertIn("Balance Due", html)
        self.assertIn(f"{si.outstanding_amount:,.2f}", html)

    def test_return_prints_as_credit_note_in_both_formats(self) -> None:
        sale = self._sell(payment_type="Credit")
        ret = self._return(sale)
        thermal = self._html(ret, PRINT_FORMAT_80MM_NAME)
        self.assertIn("CREDIT NOTE", thermal)
        self.assertNotIn("SIMPLIFIED TAX INVOICE", thermal)
        self.assertIn(sale, thermal)  # "Against"
        # Magnitudes under a CREDIT NOTE heading, like the ZATCA QR.
        grand = abs(frappe.db.get_value("Sales Invoice", ret, "grand_total"))
        self.assertIn(f"{grand:,.2f}", thermal)
        self.assertNotIn(f"-{grand:,.2f}", thermal)

        a4 = self._html(ret, PRINT_FORMAT_NAME)
        self.assertIn("CREDIT NOTE", a4)
        self.assertNotIn('class="vti-title">TAX INVOICE<', a4)
        self.assertIn(f"Against Invoice: {sale}", a4)

    # -- A4 --------------------------------------------------------------------

    def test_a4_gross_is_before_discount(self) -> None:
        name = self._sell(discount_percentage=10)
        si = frappe.get_doc("Sales Invoice", name)
        self.assertNotEqual(si.total, si.net_total)
        html = self._html(name, PRINT_FORMAT_NAME)
        gross = html.split("Total Gross", 1)[1].split("</tr>", 1)[0]
        self.assertIn(f"{si.total:.2f}", gross)
        self.assertIn('class="vti-title">TAX INVOICE<', html)

    # -- printing is read-only ---------------------------------------------------

    def test_printing_writes_nothing(self) -> None:
        name = self._sell()
        ret = self._return(name)

        def snapshot(inv: str) -> tuple:
            si = frappe.db.get_value(
                "Sales Invoice",
                inv,
                ["modified", "docstatus", "grand_total", "outstanding_amount", "status"],
                as_dict=True,
            )
            return (
                tuple(si.values()),
                frappe.db.count("GL Entry", {"voucher_no": inv}),
                frappe.db.count("Stock Ledger Entry", {"voucher_no": inv}),
                frappe.db.count("Payment Entry Reference", {"reference_name": inv}),
                frappe.db.count("Sales Invoice", {"zatgo_client_id": ["is", "set"]}),
            )

        before = {inv: snapshot(inv) for inv in (name, ret)}
        frappe.set_user(self.user)
        # The whole template still renders (where any side effect would
        # live); only wkhtmltopdf is stubbed — outside a web request it has
        # no host to fetch the site's assets from.
        with patch("frappe.utils.pdf.get_pdf", return_value=b"%PDF-stub") as get_pdf:
            for inv in (name, ret):
                for fmt in (None, PRINT_FORMAT_80MM_NAME, PRINT_FORMAT_NAME, PRINT_FORMAT_80MM_NAME):
                    res = orders_pdf(inv, print_format=fmt)
                    self.assertTrue(res["data"]["pdf_base64"])
        frappe.set_user("Administrator")
        self.assertEqual(get_pdf.call_count, 8)
        self.assertTrue(all("<div" in c.args[0] for c in get_pdf.call_args_list))
        self.assertEqual(before, {inv: snapshot(inv) for inv in (name, ret)})
