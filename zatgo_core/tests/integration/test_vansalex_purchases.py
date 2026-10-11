"""VanSaleX purchases: Purchase Invoice / Purchase Order into the van warehouse.

Covers services/vansalex_purchase_service.py and api/v1/vansalex/purchases.py:
- an invoice receives the goods into the van warehouse and posts the bill,
  Cash / Bank pay it with an auto Payment Entry, Credit leaves it payable;
- an order moves no stock until it is converted into an invoice;
- replaying a client_id returns the same document (idempotency);
- the module switches (default off) bind field users at the API and on any
  direct insert, and a driver only sees / prints their own documents.

The purchase modules default off; each test that needs them flips the client
rows and restores them in the same test (see test_vansalex_module_access.py).
"""

from __future__ import annotations

from contextlib import contextmanager

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import cint, flt, random_string

from zatgo_core.api.v1.vansalex import purchases as api
from zatgo_core.setup.ensure_vansalex_access import ensure_vansalex_access
from zatgo_core.tests.integration._fixtures import (
    get_or_create_cash_mode_of_payment,
    get_or_create_test_company,
)


class TestVansalexPurchases(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        ensure_vansalex_access()
        cls.company = get_or_create_test_company()
        cls.cash_account = frappe.db.get_value(
            "Account",
            {"company": cls.company, "account_type": "Cash", "is_group": 0, "account_name": "Cash"},
            "name",
        ) or frappe.db.get_value(
            "Account", {"company": cls.company, "account_type": "Cash", "is_group": 0}, "name"
        )
        get_or_create_cash_mode_of_payment(cls.company, cls.cash_account)
        cls.bank_account = cls._make_bank_account()
        cls.warehouse = cls._make_warehouse("VanPurchaseTest")
        cls.item_code = cls._make_item()

    def setUp(self) -> None:
        self.supplier = self._make_supplier(f"Purchase Test {random_string(8)}")
        self.user = self._make_van_user(self.warehouse)

    def tearDown(self) -> None:
        frappe.set_user("Administrator")

    # -- fixtures --------------------------------------------------------------

    @classmethod
    def _make_bank_account(cls) -> str:
        name = frappe.db.get_value(
            "Account", {"company": cls.company, "account_name": "ZG Test Bank", "is_group": 0}, "name"
        )
        if name:
            return name
        parent = frappe.db.get_value(
            "Account", {"company": cls.company, "account_type": "Bank", "is_group": 1}, "name"
        ) or frappe.db.get_value("Account", {"company": cls.company, "root_type": "Asset", "is_group": 1}, "name")
        return frappe.get_doc(
            {
                "doctype": "Account",
                "account_name": "ZG Test Bank",
                "company": cls.company,
                "parent_account": parent,
                "account_type": "Bank",
                "account_currency": "SAR",
            }
        ).insert(ignore_permissions=True).name

    @classmethod
    def _make_warehouse(cls, label: str) -> str:
        abbr = frappe.db.get_value("Company", cls.company, "abbr")
        name = f"{label} - {abbr}" if abbr else label
        if frappe.db.exists("Warehouse", name):
            return name
        return frappe.get_doc(
            {"doctype": "Warehouse", "warehouse_name": label, "company": cls.company}
        ).insert(ignore_permissions=True).name

    @classmethod
    def _make_item(cls) -> str:
        code = f"VAN-BUY-{random_string(6).upper()}"
        frappe.get_doc(
            {
                "doctype": "Item",
                "item_code": code,
                "item_name": code,
                "item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
                "stock_uom": "Nos",
                "is_stock_item": 1,
                "last_purchase_rate": 4,
            }
        ).insert(ignore_permissions=True)
        return code

    @classmethod
    def _make_supplier(cls, name: str) -> str:
        return frappe.get_doc(
            {
                "doctype": "Supplier",
                "supplier_name": name,
                "supplier_group": frappe.db.get_value("Supplier Group", {"is_group": 0}, "name"),
            }
        ).insert(ignore_permissions=True).name

    @classmethod
    def _make_van_user(cls, warehouse: str, **profile) -> str:
        email = f"vansale.purchase.test.{random_string(6).lower()}@zatgo.test"
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "VanSale",
                "last_name": "PurchaseTest",
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
                "allow_bank_payment": "Yes",
                "bank_account": cls.bank_account,
                **profile,
            }
        ).insert(ignore_permissions=True)
        return email

    @contextmanager
    def _modules(self, **switches: int):
        """Flip client-level module rows and restore them after."""
        rows = {
            r.access_key: (r.name, cint(r.enabled))
            for r in frappe.get_all(
                "VanSaleX Access",
                filters={"parenttype": "VanSaleX Settings", "access_key": ["in", list(switches)]},
                fields=["name", "access_key", "enabled"],
            )
        }
        self.assertEqual(set(rows), set(switches), "access rows must be seeded")
        try:
            for key, value in switches.items():
                frappe.db.set_value("VanSaleX Access", rows[key][0], "enabled", value)
            frappe.db.commit()
            yield
        finally:
            for name, old in rows.values():
                frappe.db.set_value("VanSaleX Access", name, "enabled", old)
            frappe.db.commit()

    def _on(self):
        return self._modules(purchase_invoice=1, purchase_order=1)

    def _stock(self) -> float:
        return flt(
            frappe.db.get_value("Bin", {"item_code": self.item_code, "warehouse": self.warehouse}, "actual_qty")
        )

    def _buy(self, **kwargs) -> dict:
        frappe.set_user(self.user)
        args = {
            "client_id": f"test-buy-{random_string(8)}",
            "supplier": self.supplier,
            "items": [{"item_code": self.item_code, "qty": 5, "rate": 10}],
            "payment_type": "Credit",
        }
        args.update(kwargs)
        return api.create_invoice(**args)

    def _pe_for(self, pi: str):
        names = frappe.get_all(
            "Payment Entry Reference", filters={"reference_name": pi, "docstatus": 1}, pluck="parent"
        )
        self.assertEqual(len(names), 1)
        return frappe.db.get_value(
            "Payment Entry", names[0], ["paid_from", "payment_type", "reference_no"], as_dict=True
        )

    # -- access ----------------------------------------------------------------

    def test_modules_are_off_by_default(self) -> None:
        from zatgo_core.services import vansalex_access as access

        eff = access.effective(self.user)
        self.assertFalse(eff["modules"]["purchase_invoice"])
        self.assertFalse(eff["modules"]["purchase_order"])
        frappe.set_user(self.user)
        with self.assertRaises(frappe.PermissionError):
            api.create_invoice(
                client_id="x", supplier=self.supplier, items=[{"item_code": self.item_code, "qty": 1, "rate": 1}]
            )
        with self.assertRaises(frappe.PermissionError):
            api.suppliers()

    def test_the_two_modules_are_independent(self) -> None:
        with self._modules(purchase_invoice=1, purchase_order=0):
            frappe.set_user(self.user)
            with self.assertRaises(frappe.PermissionError):
                api.create_order(
                    client_id="x", supplier=self.supplier, items=[{"item_code": self.item_code, "qty": 1, "rate": 1}]
                )
            self.assertTrue(self._buy()["success"])

    def test_a_user_without_vansale_role_is_refused(self) -> None:
        with self._on():
            email = f"plain.{random_string(6).lower()}@zatgo.test"
            frappe.get_doc(
                {"doctype": "User", "email": email, "first_name": "Plain", "send_welcome_email": 0}
            ).insert(ignore_permissions=True)
            frappe.set_user(email)
            with self.assertRaises(frappe.PermissionError):
                api.suppliers()

    def test_direct_purchase_insert_by_a_field_user_needs_the_module(self) -> None:
        frappe.set_user(self.user)
        doc = frappe.get_doc(
            {
                "doctype": "Purchase Order",
                "supplier": self.supplier,
                "company": self.company,
                "schedule_date": frappe.utils.today(),
                "items": [
                    {
                        "item_code": self.item_code,
                        "qty": 1,
                        "rate": 1,
                        "warehouse": self.warehouse,
                        "schedule_date": frappe.utils.today(),
                    }
                ],
            }
        )
        with self.assertRaises(frappe.PermissionError):
            doc.insert(ignore_permissions=True)

    # -- invoice ---------------------------------------------------------------

    def test_credit_invoice_receives_stock_and_stays_payable(self) -> None:
        with self._on():
            before = self._stock()
            result = self._buy(payment_type="Credit")
            self.assertTrue(result["success"], result.get("error"))
            data = result["data"]
            self.assertEqual(data["docstatus"], 1)
            self.assertEqual(data["supplier"], self.supplier)
            pi = frappe.get_doc("Purchase Invoice", data["erp_name"])
            self.assertEqual(pi.custom_payment_type, "Credit")
            self.assertEqual(pi.set_warehouse, self.warehouse)
            self.assertEqual(flt(pi.outstanding_amount), 50)
            self.assertEqual(self._stock(), before + 5)
            self.assertFalse(
                frappe.db.exists("Payment Entry Reference", {"reference_name": pi.name, "docstatus": 1})
            )

    def test_cash_invoice_is_paid_from_the_cash_account(self) -> None:
        with self._on():
            result = self._buy(payment_type="Cash")
            self.assertTrue(result["success"], result.get("error"))
            pi = frappe.get_doc("Purchase Invoice", result["data"]["erp_name"])
            self.assertEqual(pi.custom_payment_type, "Cash")
            self.assertEqual(flt(pi.outstanding_amount), 0)
            pe = self._pe_for(pi.name)
            self.assertEqual(pe.payment_type, "Pay")
            self.assertEqual(pe.paid_from, self.cash_account)

    def test_bank_invoice_is_paid_from_the_bank_account_with_reference(self) -> None:
        with self._on():
            result = self._buy(payment_type="Bank", bank_reference_no="TRF-55", supplier_invoice_no="BILL-9")
            self.assertTrue(result["success"], result.get("error"))
            pi = frappe.get_doc("Purchase Invoice", result["data"]["erp_name"])
            self.assertEqual(pi.bill_no, "BILL-9")
            self.assertEqual(pi.custom_bank_account, self.bank_account)
            pe = self._pe_for(pi.name)
            self.assertEqual(pe.paid_from, self.bank_account)
            self.assertEqual(pe.reference_no, "TRF-55")

    def test_bank_refused_when_not_allowed(self) -> None:
        with self._on():
            name = frappe.db.get_value("ZG Van Sale Profile", {"user": self.user}, "name")
            frappe.db.set_value("ZG Van Sale Profile", name, "allow_bank_payment", "No")
            with self.assertRaises(frappe.PermissionError):
                self._buy(payment_type="Bank")

    def test_blank_rate_uses_the_last_purchase_rate_and_none_is_refused(self) -> None:
        with self._on():
            priced = self._make_item_without_price()
            frappe.db.set_value("Item", priced, "last_purchase_rate", 4)
            result = self._buy(items=[{"item_code": priced, "qty": 2, "rate": 0}])
            self.assertEqual(result["data"]["items"][0]["rate"], 4)
            bare = self._make_item_without_price()
            with self.assertRaises(frappe.ValidationError):
                self._buy(items=[{"item_code": bare, "qty": 1, "rate": 0}])

    def _make_item_without_price(self) -> str:
        code = f"VAN-NOPRICE-{random_string(6).upper()}"
        frappe.get_doc(
            {
                "doctype": "Item",
                "item_code": code,
                "item_name": code,
                "item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
                "stock_uom": "Nos",
                "is_stock_item": 1,
            }
        ).insert(ignore_permissions=True)
        return code

    def test_replaying_a_client_id_returns_the_same_invoice(self) -> None:
        with self._on():
            cid = f"test-buy-{random_string(8)}"
            first = self._buy(client_id=cid)
            before = self._stock()
            again = self._buy(client_id=cid)
            self.assertEqual(again["data"]["erp_name"], first["data"]["erp_name"])
            self.assertTrue(again["meta"]["idempotent"])
            self.assertEqual(self._stock(), before)  # nothing received twice

    def test_another_users_client_id_is_refused(self) -> None:
        with self._on():
            cid = f"test-buy-{random_string(8)}"
            self._buy(client_id=cid)
            other = self._make_van_user(self.warehouse)
            self.user = other
            with self.assertRaises(frappe.PermissionError):
                self._buy(client_id=cid)

    def test_unknown_or_disabled_supplier_is_refused(self) -> None:
        with self._on():
            with self.assertRaises(frappe.DoesNotExistError):
                self._buy(supplier="No Such Supplier")
            frappe.db.set_value("Supplier", self.supplier, "disabled", 1)
            with self.assertRaises(frappe.ValidationError):
                self._buy()

    # -- order -----------------------------------------------------------------

    def test_order_moves_no_stock_until_it_is_converted(self) -> None:
        with self._on():
            before = self._stock()
            frappe.set_user(self.user)
            order = api.create_order(
                client_id=f"test-po-{random_string(8)}",
                supplier=self.supplier,
                items=[{"item_code": self.item_code, "qty": 3, "rate": 10}],
            )
            self.assertTrue(order["success"], order.get("error"))
            self.assertEqual(order["data"]["docstatus"], 1)
            self.assertEqual(self._stock(), before)
            result = api.confirm(
                client_id=f"test-pi-{random_string(8)}",
                purchase_order=order["data"]["erp_name"],
                payment_type="Cash",
            )
            self.assertTrue(result["success"], result.get("error"))
            self.assertEqual(self._stock(), before + 3)
            pi = frappe.get_doc("Purchase Invoice", result["data"]["erp_name"])
            self.assertEqual(pi.items[0].purchase_order, order["data"]["erp_name"])
            self.assertEqual(self._pe_for(pi.name).paid_from, self.cash_account)

    def test_order_replay_and_foreign_order(self) -> None:
        with self._on():
            frappe.set_user(self.user)
            cid = f"test-po-{random_string(8)}"
            items = [{"item_code": self.item_code, "qty": 1, "rate": 10}]
            first = api.create_order(client_id=cid, supplier=self.supplier, items=items)
            again = api.create_order(client_id=cid, supplier=self.supplier, items=items)
            self.assertEqual(again["data"]["erp_name"], first["data"]["erp_name"])
            other = self._make_van_user(self.warehouse)
            frappe.set_user(other)
            with self.assertRaises(frappe.PermissionError):
                api.confirm(
                    client_id=f"test-pi-{random_string(8)}",
                    purchase_order=first["data"]["erp_name"],
                    payment_type="Credit",
                )

    # -- reads -----------------------------------------------------------------

    def test_suppliers_search_and_own_lists(self) -> None:
        with self._on():
            frappe.set_user(self.user)
            found = api.suppliers(search=self.supplier[-8:])["data"]
            self.assertIn(self.supplier, [s["name"] for s in found])
            mine = self._buy()["data"]["erp_name"]
            other = self._make_van_user(self.warehouse)
            frappe.set_user(other)
            theirs = api.create_invoice(
                client_id=f"test-buy-{random_string(8)}",
                supplier=self.supplier,
                items=[{"item_code": self.item_code, "qty": 1, "rate": 10}],
                payment_type="Credit",
            )["data"]["erp_name"]
            frappe.set_user(self.user)
            names = [r["name"] for r in api.list(kind="invoice")["data"]]
            self.assertIn(mine, names)
            self.assertNotIn(theirs, names)
            with self.assertRaises(frappe.PermissionError):
                api.pdf(kind="invoice", name=theirs)

    def test_pdf_of_own_invoice(self) -> None:
        from unittest.mock import patch

        with self._on():
            name = self._buy()["data"]["erp_name"]
            with patch("frappe.utils.pdf.get_pdf", return_value=b"%PDF-1.4 test"):
                out = api.pdf(kind="invoice", name=name)["data"]
            self.assertEqual(out["filename"], f"{name}.pdf")
            self.assertTrue(out["pdf_base64"])

    def test_context_exposes_the_modules(self) -> None:
        from zatgo_core.api.v1.vansalex.me import context

        with self._on():
            frappe.set_user(self.user)
            modules = context()["data"]["access"]["modules"]
            self.assertTrue(modules["purchase_invoice"])
            self.assertTrue(modules["purchase_order"])
