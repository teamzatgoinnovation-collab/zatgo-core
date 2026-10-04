"""Multi-method / multi-account payment allocation (services/payment_allocation.py).

Real documents through real submit/cancel on the bench: Sales Invoice
payment rows are posted by ERPNext's own make_pos_gl_entries(), Payment
Entry Payment Details rows by overrides/payment_entry.py on top of ERPNext's
build_gl_map(). Every GL assertion reads the actual GL Entry rows.
"""

from __future__ import annotations

from collections import defaultdict

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import flt, random_string

from zatgo_core.services.payment_allocation import allowed_accounts
from zatgo_core.tests.integration._fixtures import (
    get_or_create_cash_mode_of_payment,
    get_or_create_test_company,
)

OTHER_COMPANY_NAME = "ZatGo Core Test Co Two"
OTHER_COMPANY_ABBR = "ZCT2"


class TestMultiPayment(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.company = get_or_create_test_company()
        cls.abbr = frappe.db.get_value("Company", cls.company, "abbr")
        cls.cash = frappe.get_cached_value("Company", cls.company, "default_cash_account")
        cls.cash_group = frappe.db.get_value("Account", cls.cash, "parent_account")
        get_or_create_cash_mode_of_payment(cls.company, cls.cash)

        # Blank account_type on purpose: other suites pick "any Cash-type
        # account" of this shared test company, and the collection service
        # commits mid-test, so these ledgers outlive the class rollback.
        # (Bank-type ledgers would also make ERPNext demand a Reference No.)
        cls.petty = cls._account("ZG Test Petty Cash")
        cls.hdfc_pos = cls._account("ZG Test HDFC POS")
        cls.sbi_pos = cls._account("ZG Test SBI POS")
        cls.hdfc_upi = cls._account("ZG Test HDFC UPI")
        cls.sbi_upi = cls._account("ZG Test SBI UPI")
        cls.disabled_till = cls._account("ZG Test Disabled Till", disabled=1)
        cls.usd_till = cls._account("ZG Test USD Till", currency="USD")

        cls._configure_mode("Cash", "Cash", [(cls.cash, 1), (cls.petty, 0)])
        cls._configure_mode("Card", "Bank", [(cls.hdfc_pos, 1), (cls.sbi_pos, 0)])
        cls._configure_mode("UPI", "Bank", [(cls.hdfc_upi, 1), (cls.sbi_upi, 0), (cls.usd_till, 0)])

        cls.other_company = cls._other_company()
        cls.other_cash = frappe.db.get_value(
            "Account", {"company": cls.other_company, "account_type": "Cash", "is_group": 0}, "name"
        )

        cls.item_code = cls._make_item()
        cls.expense_account = frappe.db.get_value(
            "Account", {"company": cls.company, "account_type": "Expense Account", "is_group": 0}, "name"
        )
        cls.customer = cls._make_customer("Multi Payment Test Customer")
        cls.supplier = cls._make_supplier("Multi Payment Test Supplier")

    # -- fixtures ---------------------------------------------------------

    @classmethod
    def _account(cls, label: str, disabled: int = 0, currency: str | None = None) -> str:
        name = f"{label} - {cls.abbr}"
        if not frappe.db.exists("Account", name):
            frappe.get_doc(
                {
                    "doctype": "Account",
                    "account_name": label,
                    "parent_account": cls.cash_group,
                    "company": cls.company,
                    "account_currency": currency or "SAR",
                    "is_group": 0,
                }
            ).insert(ignore_permissions=True)
        frappe.db.set_value("Account", name, {"disabled": disabled, "account_type": ""})
        return name

    @classmethod
    def _configure_mode(cls, mode: str, mop_type: str, accounts: list[tuple[str, int]]) -> None:
        if not frappe.db.exists("Mode of Payment", mode):
            frappe.get_doc(
                {"doctype": "Mode of Payment", "mode_of_payment": mode, "type": mop_type, "enabled": 1}
            ).insert(ignore_permissions=True)
        mop = frappe.get_doc("Mode of Payment", mode)
        mop.enabled = 1
        mop.set("custom_zg_accounts", [r for r in mop.custom_zg_accounts if r.company != cls.company])
        for account, is_default in accounts:
            mop.append(
                "custom_zg_accounts",
                {"company": cls.company, "account": account, "is_default": is_default, "enabled": 1},
            )
        mop.save(ignore_permissions=True)

    @classmethod
    def _other_company(cls) -> str:
        if not frappe.db.exists("Company", OTHER_COMPANY_NAME):
            frappe.get_doc(
                {
                    "doctype": "Company",
                    "company_name": OTHER_COMPANY_NAME,
                    "abbr": OTHER_COMPANY_ABBR,
                    "default_currency": "SAR",
                    "country": "Saudi Arabia",
                }
            ).insert(ignore_permissions=True)
        return OTHER_COMPANY_NAME

    @classmethod
    def _make_item(cls) -> str:
        code = f"MULTI-PAY-TEST-{random_string(6).upper()}"
        frappe.get_doc(
            {
                "doctype": "Item",
                "item_code": code,
                "item_name": code,
                "item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
                "stock_uom": "Nos",
                "is_stock_item": 0,
            }
        ).insert(ignore_permissions=True)
        return code

    @classmethod
    def _make_customer(cls, name: str) -> str:
        if not frappe.db.exists("Customer", name):
            frappe.get_doc(
                {
                    "doctype": "Customer",
                    "customer_name": name,
                    "customer_type": "Individual",
                    "customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
                    "territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
                }
            ).insert(ignore_permissions=True)
        return name

    @classmethod
    def _make_supplier(cls, name: str) -> str:
        if not frappe.db.exists("Supplier", name):
            frappe.get_doc(
                {
                    "doctype": "Supplier",
                    "supplier_name": name,
                    "supplier_group": frappe.db.get_value("Supplier Group", {"is_group": 0}, "name"),
                }
            ).insert(ignore_permissions=True)
        return name

    def _si(self, total: float, payments: list[tuple[str, str, float]], payment_type: str | None = None):
        doc = frappe.get_doc(
            {
                "doctype": "Sales Invoice",
                "customer": self.customer,
                "company": self.company,
                "currency": "SAR",
                "conversion_rate": 1,
                "due_date": frappe.utils.nowdate(),
                "custom_payment_type": payment_type,
                "items": [{"item_code": self.item_code, "qty": 1, "rate": total}],
            }
        )
        if payments:
            doc.is_pos = 1
            doc.flags.ignore_pos_profile = True
            for mop, account, amount in payments:
                doc.append("payments", {"mode_of_payment": mop, "account": account, "amount": amount})
        return doc

    def _submit_si(self, total, payments, payment_type=None):
        doc = self._si(total, payments, payment_type)
        doc.insert(ignore_permissions=True)
        doc.submit()
        return doc

    def _credit_si(self, total: float):
        return self._submit_si(total, [], "Credit")

    def _credit_pi(self, total: float):
        pi = frappe.get_doc(
            {
                "doctype": "Purchase Invoice",
                "supplier": self.supplier,
                "company": self.company,
                "currency": "SAR",
                "conversion_rate": 1,
                "due_date": frappe.utils.nowdate(),
                "custom_payment_type": "Credit",
                "items": [
                    {"item_code": self.item_code, "qty": 1, "rate": total, "expense_account": self.expense_account}
                ],
            }
        )
        pi.insert(ignore_permissions=True)
        pi.submit()
        return pi

    def _pe_for(self, doctype: str, name: str, rows: list[tuple[str, str, float]]):
        from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

        pe = get_payment_entry(doctype, name)
        for mop, account, amount in rows:
            pe.append("custom_payment_details", {"mode_of_payment": mop, "account": account, "amount": amount})
        return pe

    @staticmethod
    def _gl(voucher_type: str, voucher_no: str) -> list:
        return frappe.get_all(
            "GL Entry",
            filters={"voucher_type": voucher_type, "voucher_no": voucher_no, "is_cancelled": 0},
            fields=["account", "debit", "credit", "party_type", "party"],
        )

    def _by_account(self, gl) -> dict[str, tuple[float, float]]:
        out: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
        for g in gl:
            out[g.account][0] += flt(g.debit)
            out[g.account][1] += flt(g.credit)
        return {k: (flt(v[0], 2), flt(v[1], 2)) for k, v in out.items()}

    def _assert_balanced(self, gl) -> None:
        self.assertAlmostEqual(sum(flt(g.debit) for g in gl), sum(flt(g.credit) for g in gl), places=2)

    def _assert_si_paid(self, si, expected: dict[str, float]) -> None:
        """Payment accounts debited exactly as allocated, receivable credited
        with the same total, GL balanced, no extra Payment Entry."""
        gl = self._gl("Sales Invoice", si.name)
        self._assert_balanced(gl)
        by_acc = self._by_account(gl)
        for account, amount in expected.items():
            self.assertEqual(by_acc[account], (amount, 0.0), account)
        receivable = by_acc[si.debit_to]
        self.assertEqual(receivable, (flt(si.grand_total, 2), flt(sum(expected.values()), 2)))
        self.assertEqual(frappe.db.get_value("Sales Invoice", si.name, "outstanding_amount"), 0)
        self.assertFalse(
            frappe.db.exists("Payment Entry Reference", {"reference_name": si.name, "docstatus": 1}),
            "a Payment Entry was also created -- money would be booked twice",
        )

    # -- configuration ------------------------------------------------------

    def test_allowed_accounts_default_first(self) -> None:
        accounts = allowed_accounts("Cash", self.company)
        self.assertEqual(accounts[0], {"account": self.cash, "is_default": True})
        self.assertIn(self.petty, [a["account"] for a in accounts])
        self.assertNotIn(self.disabled_till, [a["account"] for a in accounts])

    def test_mode_of_payment_rejects_other_company_and_duplicate_rows(self) -> None:
        mop = frappe.get_doc("Mode of Payment", "Card")
        mop.append("custom_zg_accounts", {"company": self.company, "account": self.other_cash, "enabled": 1})
        with self.assertRaises(frappe.ValidationError):
            mop.save(ignore_permissions=True)
        mop = frappe.get_doc("Mode of Payment", "Card")
        mop.append("custom_zg_accounts", {"company": self.company, "account": self.hdfc_pos, "enabled": 1})
        with self.assertRaises(frappe.ValidationError):
            mop.save(ignore_permissions=True)

    # -- Sales Invoice (tests 1-10, 13) ---------------------------------------

    def test_01_cash_only(self) -> None:
        # Payment Type Cash: the existing auto-Payment-Entry hook must NOT
        # also fire -- the invoice is already paid by its own rows.
        si = self._submit_si(1000, [("Cash", self.cash, 1000)], "Cash")
        self._assert_si_paid(si, {self.cash: 1000})

    def test_02_cash_and_card(self) -> None:
        si = self._submit_si(1000, [("Cash", self.cash, 500), ("Card", self.hdfc_pos, 500)])
        self._assert_si_paid(si, {self.cash: 500, self.hdfc_pos: 500})

    def test_03_same_method_multiple_accounts(self) -> None:
        # ERPNext core would reset Petty Cash to the mode default (Cash);
        # overrides/sales_invoice.py must keep it.
        si = self._submit_si(1000, [("Cash", self.cash, 500), ("Cash", self.petty, 500)])
        self.assertEqual([p.account for p in si.payments], [self.cash, self.petty])
        self._assert_si_paid(si, {self.cash: 500, self.petty: 500})

    def test_04_multiple_methods_multiple_accounts(self) -> None:
        si = self._submit_si(
            4000,
            [
                ("Cash", self.cash, 500),
                ("Cash", self.petty, 500),
                ("Card", self.hdfc_pos, 1000),
                ("Card", self.sbi_pos, 1000),
                ("UPI", self.hdfc_upi, 1000),
            ],
        )
        self._assert_si_paid(
            si, {self.cash: 500, self.petty: 500, self.hdfc_pos: 1000, self.sbi_pos: 1000, self.hdfc_upi: 1000}
        )

    def test_05_partial_payment_needs_credit_and_keeps_outstanding(self) -> None:
        with self.assertRaisesRegex(frappe.ValidationError, "does not match invoice total"):
            self._submit_si(1000, [("Cash", self.cash, 600)])

        si = self._submit_si(1000, [("Cash", self.cash, 600)], "Credit")
        self.assertEqual(frappe.db.get_value("Sales Invoice", si.name, "outstanding_amount"), 400)
        by_acc = self._by_account(self._gl("Sales Invoice", si.name))
        self.assertEqual(by_acc[self.cash], (600.0, 0.0))
        self.assertEqual(by_acc[si.debit_to], (1000.0, 600.0))
        ple = frappe.db.sql(
            "select sum(amount) from `tabPayment Ledger Entry` where against_voucher_no=%s and delinked=0",
            si.name,
        )[0][0]
        self.assertEqual(flt(ple), 400)

    def test_06_overpayment_rejected(self) -> None:
        with self.assertRaisesRegex(frappe.ValidationError, "exceed"):
            self._submit_si(1000, [("Card", self.hdfc_pos, 1200)])
        # Cash rows would otherwise turn the excess into ERPNext "change".
        with self.assertRaisesRegex(frappe.ValidationError, "exceed"):
            self._submit_si(1000, [("Cash", self.cash, 1200)], "Credit")

    def test_07_disabled_account_rejected(self) -> None:
        with self.assertRaisesRegex(frappe.ValidationError, "disabled"):
            self._si(1000, [("Cash", self.disabled_till, 1000)]).insert(ignore_permissions=True)

    def test_08_group_account_rejected(self) -> None:
        with self.assertRaisesRegex(frappe.ValidationError, "group account"):
            self._si(1000, [("Cash", self.cash_group, 1000)]).insert(ignore_permissions=True)

    def test_09_other_company_account_rejected(self) -> None:
        with self.assertRaisesRegex(frappe.ValidationError, "belongs to company"):
            self._si(1000, [("Cash", self.other_cash, 1000)]).insert(ignore_permissions=True)

    def test_account_not_configured_for_method_rejected(self) -> None:
        with self.assertRaisesRegex(frappe.ValidationError, "not configured for Payment Method"):
            self._si(1000, [("Cash", self.sbi_pos, 1000)]).insert(ignore_permissions=True)

    def test_foreign_currency_account_rejected(self) -> None:
        with self.assertRaisesRegex(frappe.ValidationError, "USD"):
            self._si(1000, [("UPI", self.usd_till, 1000)]).insert(ignore_permissions=True)

    def test_negative_and_duplicate_rows_rejected(self) -> None:
        # ERPNext's own verify_payment_amount_is_positive() gets there first.
        with self.assertRaisesRegex(frappe.ValidationError, "positive|greater than zero"):
            self._si(1000, [("Cash", self.cash, 1200), ("Cash", self.petty, -200)]).insert(
                ignore_permissions=True
            )
        with self.assertRaisesRegex(frappe.ValidationError, "duplicates"):
            self._si(1000, [("Cash", self.cash, 500), ("Cash", self.cash, 500)]).insert(ignore_permissions=True)

    def test_10_gl_balanced_and_no_duplicates_then_cancel_reverses(self) -> None:
        si = self._submit_si(
            3000, [("Cash", self.cash, 1000), ("Card", self.sbi_pos, 1000), ("UPI", self.sbi_upi, 1000)]
        )
        gl = self._gl("Sales Invoice", si.name)
        self._assert_balanced(gl)
        # one income credit, one receivable debit, and one Dr/Cr pair per
        # payment row -- nothing more.
        payment_lines = [g for g in gl if g.account in (self.cash, self.sbi_pos, self.sbi_upi)]
        self.assertEqual(len(payment_lines), 3)
        self.assertEqual(sum(flt(g.debit) for g in gl if g.account == si.debit_to), 3000)

        si.reload()
        si.cancel()
        self.assertEqual(self._gl("Sales Invoice", si.name), [])
        net = frappe.db.sql(
            "select sum(debit) - sum(credit) from `tabGL Entry` where voucher_no=%s and account=%s",
            (si.name, self.cash),
        )[0][0]
        self.assertEqual(flt(net), 0)

    def test_13_standard_sales_invoice_without_rows_unchanged(self) -> None:
        si = self._credit_si(700)
        self.assertEqual(si.is_pos, 0)
        self.assertEqual(frappe.db.get_value("Sales Invoice", si.name, "outstanding_amount"), 700)
        by_acc = self._by_account(self._gl("Sales Invoice", si.name))
        self.assertEqual(by_acc[si.debit_to], (700.0, 0.0))
        self.assertNotIn(self.cash, by_acc)

    # -- Payment Entry (tests 11, 12, 14) ---------------------------------------

    def test_11_payment_entry_receive_split(self) -> None:
        si = self._credit_si(1000)
        pe = self._pe_for(
            "Sales Invoice",
            si.name,
            [("Cash", self.cash, 300), ("Cash", self.petty, 200), ("Card", self.hdfc_pos, 500)],
        )
        pe.insert(ignore_permissions=True)
        self.assertEqual(pe.paid_to, self.cash)
        self.assertEqual(pe.received_amount, 1000)
        self.assertIsNone(pe.mode_of_payment)  # mixed methods
        pe.submit()

        gl = self._gl("Payment Entry", pe.name)
        self._assert_balanced(gl)
        by_acc = self._by_account(gl)
        self.assertEqual(by_acc[self.cash], (300.0, 0.0))
        self.assertEqual(by_acc[self.petty], (200.0, 0.0))
        self.assertEqual(by_acc[self.hdfc_pos], (500.0, 0.0))
        self.assertEqual(by_acc[si.debit_to], (0.0, 1000.0))
        self.assertEqual(len(gl), 4)
        self.assertEqual(frappe.db.get_value("Sales Invoice", si.name, "outstanding_amount"), 0)
        self.assertEqual([r.base_amount for r in pe.custom_payment_details], [300, 200, 500])

        pe.reload()
        pe.cancel()
        self.assertEqual(self._gl("Payment Entry", pe.name), [])
        self.assertEqual(frappe.db.get_value("Sales Invoice", si.name, "outstanding_amount"), 1000)

    def test_12_payment_entry_pay_split(self) -> None:
        pi = self._credit_pi(1000)
        pe = self._pe_for("Purchase Invoice", pi.name, [("Cash", self.cash, 400), ("Card", self.hdfc_pos, 600)])
        pe.insert(ignore_permissions=True)
        self.assertEqual(pe.paid_from, self.cash)
        pe.submit()

        gl = self._gl("Payment Entry", pe.name)
        self._assert_balanced(gl)
        by_acc = self._by_account(gl)
        self.assertEqual(by_acc[pi.credit_to], (1000.0, 0.0))
        self.assertEqual(by_acc[self.cash], (0.0, 400.0))
        self.assertEqual(by_acc[self.hdfc_pos], (0.0, 600.0))
        self.assertEqual(frappe.db.get_value("Purchase Invoice", pi.name, "outstanding_amount"), 0)

    def test_payment_entry_total_mismatch_and_mixed_currency_rejected(self) -> None:
        si = self._credit_si(500)
        pe = self._pe_for("Sales Invoice", si.name, [("Cash", self.cash, 300), ("UPI", self.usd_till, 200)])
        with self.assertRaisesRegex(frappe.ValidationError, "one currency"):
            pe.insert(ignore_permissions=True)

        pe = self._pe_for("Sales Invoice", si.name, [("Cash", self.cash, 600)])
        # 600 against a 500 invoice: ERPNext keeps the extra as an
        # unallocated advance -- allowed, exactly as with a single account.
        pe.insert(ignore_permissions=True)
        self.assertEqual(pe.paid_amount, 600)
        self.assertEqual(pe.unallocated_amount, 100)

    def test_internal_transfer_rows_rejected(self) -> None:
        pe = frappe.get_doc(
            {
                "doctype": "Payment Entry",
                "payment_type": "Internal Transfer",
                "company": self.company,
                "paid_from": self.cash,
                "paid_to": self.petty,
                "paid_amount": 100,
                "received_amount": 100,
                "custom_payment_details": [{"mode_of_payment": "Cash", "account": self.petty, "amount": 100}],
            }
        )
        with self.assertRaisesRegex(frappe.ValidationError, "only supported on Receive and Pay"):
            pe.insert(ignore_permissions=True)

    def test_14_standard_payment_entry_without_rows_unchanged(self) -> None:
        from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

        si = self._credit_si(800)
        pe = get_payment_entry("Sales Invoice", si.name, bank_account=self.hdfc_pos)
        pe.insert(ignore_permissions=True)
        pe.submit()
        by_acc = self._by_account(self._gl("Payment Entry", pe.name))
        self.assertEqual(by_acc, {self.hdfc_pos: (800.0, 0.0), si.debit_to: (0.0, 800.0)})

    # -- API (tests 15, 16) -----------------------------------------------------

    def test_15_api_sales_invoice_payment_details(self) -> None:
        """The VanSale create path, with stock/warehouse taken out of the
        picture: the same parse + apply the service runs, then a real
        insert/submit."""
        from zatgo_core.services.payment_allocation import apply_to_sales_invoice, parse_payment_details

        rows = parse_payment_details(
            '[{"payment_method": "Cash", "amount": 2000},'
            ' {"payment_method": "Card", "account": "%s", "amount": 3000, "reference_no": "AUTH-1"},'
            ' {"payment_method": "UPI", "amount": 5000, "remarks": "upi ref 9"}]' % self.sbi_pos,
            self.company,
        )
        # Missing accounts resolve to each method's default.
        self.assertEqual([r["account"] for r in rows], [self.cash, self.sbi_pos, self.hdfc_upi])
        si = self._si(10000, [])
        apply_to_sales_invoice(si, rows)
        si.insert(ignore_permissions=True)
        si.submit()
        self._assert_si_paid(si, {self.cash: 2000, self.sbi_pos: 3000, self.hdfc_upi: 5000})
        self.assertEqual(si.payments[1].reference_no, "AUTH-1")
        self.assertEqual(si.payments[2].custom_remarks, "upi ref 9")

        for bad in ('[{"payment_method": "Cash", "amount": 0}]', '{"payment_method": "Cash"}', "[1]"):
            with self.assertRaises(frappe.ValidationError):
                parse_payment_details(bad, self.company)

    def test_16_api_payment_entry_payment_details(self) -> None:
        from zatgo_core.services.vansalex_service import create_collection

        si = self._credit_si(900)
        resp = create_collection(
            client_id=f"multi-pay-test-{random_string(10)}",
            customer=self.customer,
            amount=None,
            sales_invoice=si.name,
            payment_details=[
                {"payment_method": "Cash", "account": self.petty, "amount": 400},
                {"payment_method": "UPI", "amount": 500},
            ],
        )
        data = resp["data"]
        self.assertEqual(
            [(r["account"], r["amount"]) for r in data["payment_details"]],
            [(self.petty, 400), (self.hdfc_upi, 500)],
        )
        by_acc = self._by_account(self._gl("Payment Entry", data["erp_name"]))
        self.assertEqual(by_acc[self.petty], (400.0, 0.0))
        self.assertEqual(by_acc[self.hdfc_upi], (500.0, 0.0))
        self.assertEqual(by_acc[si.debit_to], (0.0, 900.0))
        self.assertEqual(frappe.db.get_value("Sales Invoice", si.name, "outstanding_amount"), 0)

        with self.assertRaisesRegex(frappe.ValidationError, "does not match"):
            create_collection(
                client_id=f"multi-pay-test-{random_string(10)}",
                customer=self.customer,
                amount=100,
                payment_details=[{"payment_method": "Cash", "amount": 50}],
            )

    def test_report_groups_by_method_and_account(self) -> None:
        from zatgo_core.zatgo_core.report.payment_method_summary.payment_method_summary import execute

        si = self._submit_si(1000, [("Card", self.sbi_pos, 1000)])
        _, data = execute(
            {
                "company": self.company,
                "from_date": si.posting_date,
                "to_date": si.posting_date,
                "account": self.sbi_pos,
            }
        )
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["mode_of_payment"], "Card")
        self.assertGreaterEqual(data[0]["received"], 1000)

    def test_preview_totals_match_the_invoice_split_must_cover(self) -> None:
        """orders.preview_totals: ERPNext's own totals for a sale, nothing
        saved -- payable_total (rounded_total when rounding is on) is what a
        split must add up to, so the app never has to re-implement rounding."""
        from frappe.utils import round_based_on_smallest_currency_fraction

        from zatgo_core.services.vansalex_service import preview_invoice_totals

        warehouse = frappe.db.get_value("Warehouse", {"company": self.company, "is_group": 0}, "name")
        before = frappe.db.count("Sales Invoice")
        data = preview_invoice_totals(
            customer=self.customer,
            items=[{"item_code": self.item_code, "qty": 1, "rate": 57.5}],
            warehouse=warehouse,
        )["data"]
        self.assertEqual(frappe.db.count("Sales Invoice"), before, "preview must not save anything")
        self.assertEqual(data["grand_total"], 57.5)
        if frappe.db.get_single_value("Global Defaults", "disable_rounded_total"):
            self.assertEqual(data["payable_total"], 57.5)
        else:
            self.assertEqual(
                data["payable_total"], round_based_on_smallest_currency_fraction(57.5, "SAR", 2)
            )
            self.assertEqual(data["payable_total"], data["rounded_total"])

