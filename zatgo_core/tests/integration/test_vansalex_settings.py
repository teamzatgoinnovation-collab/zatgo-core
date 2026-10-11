"""VanSaleX settings: resolution order and server-side enforcement.

Covers services/vansalex_settings.py and its use by create_order:
- defaults come from ERPNext records first (Mode of Payment "Cash" account)
  and zatgo_core's second (ZG Company Settings default warehouse);
- a Cash invoice gets its Payment Entry auto-created (existing
  invoice_cash_payment_service hook), a Credit invoice stays outstanding;
- Bank (when allowed) pays into the Bank account, Cash into the Cash
  account -- the default, or one the driver picks with "Choose payment
  account";
- per-user ZG Van Sale Profile overrides are enforced on the server — the
  app hiding a toggle is not the control.

Per-user rules are exercised through each test's own profile, never by
mutating the VanSaleX Settings single, so nothing global needs restoring.
"""

from __future__ import annotations

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import flt, random_string

from zatgo_core.services.vansalex_service import create_collection, create_order
from zatgo_core.services.vansalex_settings import (
    resolve,
    selectable_payment_accounts,
    selectable_warehouses,
)
from zatgo_core.tests.integration._fixtures import (
    get_or_create_cash_mode_of_payment,
    get_or_create_test_company,
)


class TestVansalexSettings(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.company = get_or_create_test_company()
        # "Cash" itself: this class also makes a second Cash account (Van
        # Till), which a plain "first Cash account" lookup could pick up.
        cls.cash_account = frappe.db.get_value(
            "Account",
            {"company": cls.company, "account_type": "Cash", "is_group": 0, "account_name": "Cash"},
            "name",
        ) or frappe.db.get_value(
            "Account", {"company": cls.company, "account_type": "Cash", "is_group": 0}, "name"
        )
        get_or_create_cash_mode_of_payment(cls.company, cls.cash_account)
        cls.bank_account = cls._make_account("ZG Test Bank", "Bank")
        cls.other_bank_account = cls._make_account("ZG Test Bank 2", "Bank")
        cls.till_account = cls._make_account("Van Till", "Cash")
        cls.warehouse = cls._make_warehouse("VanSaleSettingsTest")
        cls.other_warehouse = cls._make_warehouse("VanSaleSettingsOther")
        cls.item_code = cls._make_stocked_item(cls.warehouse, qty=1000)

    def setUp(self) -> None:
        self.customer = self._make_customer(f"Settings Test {random_string(8)}")
        self.user = self._make_van_user(self.warehouse)

    def tearDown(self) -> None:
        frappe.set_user("Administrator")

    # -- fixtures (mirrors test_vansalex_collection_allocation.py) --------

    @classmethod
    def _make_account(cls, account_name: str, account_type: str) -> str:
        """A ledger account of [account_type] under the company's group of
        that type (as test_invoice_cash_payment.py makes its bank account)."""
        name = frappe.db.get_value(
            "Account", {"company": cls.company, "account_name": account_name, "is_group": 0}, "name"
        )
        if name:
            return name
        parent = frappe.db.get_value(
            "Account", {"company": cls.company, "account_type": account_type, "is_group": 1}, "name"
        ) or frappe.db.get_value("Account", cls.cash_account, "parent_account")
        return frappe.get_doc(
            {
                "doctype": "Account",
                "account_name": account_name,
                "company": cls.company,
                "parent_account": parent,
                "account_type": account_type,
            }
        ).insert(ignore_permissions=True).name

    @classmethod
    def _make_warehouse(cls, label: str) -> str:
        abbr = frappe.db.get_value("Company", cls.company, "abbr")
        name = f"{label} - {abbr}" if abbr else label
        if frappe.db.exists("Warehouse", name):
            return name
        doc = frappe.get_doc(
            {"doctype": "Warehouse", "warehouse_name": label, "company": cls.company}
        )
        doc.insert(ignore_permissions=True)
        return doc.name

    @classmethod
    def _make_stocked_item(cls, warehouse: str, qty: float) -> str:
        code = f"VANSALE-SET-{random_string(6).upper()}"
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
        frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "stock_entry_type": "Material Receipt",
                "company": cls.company,
                "items": [
                    {"item_code": code, "qty": qty, "t_warehouse": warehouse, "basic_rate": 10}
                ],
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
    def _make_van_user(cls, warehouse: str | None, **profile_overrides) -> str:
        email = f"vansale.settings.test.{random_string(6).lower()}@zatgo.test"
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "VanSale",
                "last_name": "SettingsTest",
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
                **profile_overrides,
            }
        ).insert(ignore_permissions=True)
        return email

    def _set_profile(self, **values) -> None:
        name = frappe.db.get_value("ZG Van Sale Profile", {"user": self.user}, "name")
        doc = frappe.get_doc("ZG Van Sale Profile", name)
        doc.update(values)
        doc.save(ignore_permissions=True)

    def _sell(self, **kwargs) -> dict:
        frappe.set_user(self.user)
        return create_order(
            client_id=f"test-settings-{random_string(8)}",
            customer=self.customer,
            items=[{"item_code": self.item_code, "qty": 1, "rate": 10}],
            **kwargs,
        )

    # -- resolution ----------------------------------------------------------

    def test_cash_account_defaults_to_erpnext_mode_of_payment(self) -> None:
        eff = resolve(self.user)
        self.assertEqual(eff["company"], self.company)
        self.assertEqual(eff["warehouse"], self.warehouse)
        self.assertEqual(eff["cash_account"], self.cash_account)

    def test_profile_cash_account_overrides_mode_of_payment(self) -> None:
        self._set_profile(cash_account=self.till_account)
        self.assertEqual(resolve(self.user)["cash_account"], self.till_account)

    def test_profile_overrides_toggles(self) -> None:
        self._set_profile(
            show_warehouse_on_invoice="No",
            allow_warehouse_change="Yes",
            allow_credit_sales="No",
            default_payment_type="Credit",
        )
        eff = resolve(self.user)
        self.assertEqual(eff["show_warehouse_on_invoice"], 0)
        self.assertEqual(eff["allow_warehouse_change"], 1)
        self.assertEqual(eff["allow_credit_sales"], 0)
        # Credit default can't stand when credit isn't allowed.
        self.assertEqual(eff["default_payment_type"], "Cash")

    def test_context_exposes_effective_settings(self) -> None:
        from zatgo_core.api.v1.vansalex.me import context

        frappe.set_user(self.user)
        settings = context()["data"]["settings"]
        self.assertEqual(settings["warehouse"], self.warehouse)
        self.assertIn(settings["default_payment_type"], ("Cash", "Credit"))
        self.assertIn("tax_rate", settings)
        self.assertIn("tax_inclusive", settings)
        self.assertTrue(frappe.db.exists("Print Format", settings["print_format"]))

    def test_tax_summary_uses_erpnext_default_template(self) -> None:
        from zatgo_core.services.vansalex_settings import tax_summary

        tax_account = frappe.db.get_value(
            "Account",
            {
                "company": self.company,
                "account_type": ["in", ["Tax", "Chargeable", "Income Account"]],
                "is_group": 0,
            },
            "name",
        )
        if not tax_account:
            self.skipTest("test company has no account usable as a tax head")
        title = f"VSX Test VAT {random_string(5)}"
        tpl = frappe.get_doc(
            {
                "doctype": "Sales Taxes and Charges Template",
                "title": title,
                "company": self.company,
                "is_default": 1,
                "taxes": [
                    {
                        "charge_type": "On Net Total",
                        "account_head": tax_account,
                        "rate": 15,
                        "description": "VAT 15%",
                    }
                ],
            }
        ).insert(ignore_permissions=True)
        try:
            if frappe.db.get_value("ZG Company Settings", {"company": self.company}, "default_tax_template"):
                self.skipTest("ZG Company Settings pins a tax template on the test company")
            summary = tax_summary(self.company)
            self.assertEqual(summary["tax_template"], tpl.name)
            self.assertEqual(summary["tax_rate"], 15)
            self.assertEqual(summary["tax_inclusive"], 0)
        finally:
            frappe.delete_doc("Sales Taxes and Charges Template", tpl.name, force=True)

    # -- cash / credit -------------------------------------------------------

    def test_cash_invoice_auto_creates_payment_entry(self) -> None:
        result = self._sell(warehouse=self.warehouse, payment_type="Cash")
        self.assertTrue(result["success"], result.get("error"))
        si = frappe.get_doc("Sales Invoice", result["data"]["erp_name"])
        self.assertEqual(si.custom_payment_type, "Cash")
        self.assertEqual(si.custom_cash_account, self.cash_account)
        self.assertEqual(flt(si.outstanding_amount), 0)
        pe = frappe.get_all(
            "Payment Entry Reference",
            filters={"reference_name": si.name, "docstatus": 1},
            pluck="parent",
        )
        self.assertEqual(len(pe), 1)
        self.assertEqual(frappe.db.get_value("Payment Entry", pe[0], "paid_to"), self.cash_account)

    def test_credit_invoice_stays_outstanding(self) -> None:
        result = self._sell(warehouse=self.warehouse, payment_type="Credit")
        self.assertTrue(result["success"], result.get("error"))
        si = frappe.get_doc("Sales Invoice", result["data"]["erp_name"])
        self.assertEqual(si.custom_payment_type, "Credit")
        self.assertGreater(flt(si.outstanding_amount), 0)
        self.assertFalse(
            frappe.db.exists("Payment Entry Reference", {"reference_name": si.name, "docstatus": 1})
        )

    def test_credit_refused_when_not_allowed(self) -> None:
        self._set_profile(allow_credit_sales="No")
        with self.assertRaises(frappe.PermissionError):
            self._sell(warehouse=self.warehouse, payment_type="Credit")

    def test_omitted_payment_type_keeps_legacy_behaviour(self) -> None:
        # Older app builds send no payment_type; their invoices must not
        # silently become Cash with an auto Payment Entry.
        result = self._sell(warehouse=self.warehouse)
        si = frappe.get_doc("Sales Invoice", result["data"]["erp_name"])
        self.assertFalse(si.custom_payment_type)
        self.assertGreater(flt(si.outstanding_amount), 0)

    # -- warehouse -----------------------------------------------------------

    def test_other_warehouse_refused_by_default(self) -> None:
        self._set_profile(allow_warehouse_change="No")
        with self.assertRaises(frappe.PermissionError):
            self._sell(warehouse=self.other_warehouse, payment_type="Credit")

    def test_other_warehouse_allowed_when_enabled(self) -> None:
        self._set_profile(allow_warehouse_change="Yes")
        frappe.set_user(self.user)
        names = {w["name"] for w in selectable_warehouses()}
        self.assertIn(self.other_warehouse, names)
        frappe.set_user("Administrator")
        # other_warehouse has no stock for this item — the server must get
        # past the permission check and fail on stock, not on access.
        with self.assertRaises(frappe.ValidationError) as ctx:
            self._sell(warehouse=self.other_warehouse, payment_type="Credit")
        self.assertNotIsInstance(ctx.exception, frappe.PermissionError)

    def test_profile_without_warehouse_uses_company_default(self) -> None:
        if not frappe.db.exists("ZG Company Settings", {"company": self.company}):
            self.skipTest("no ZG Company Settings row for the test company")
        company_wh = frappe.db.get_value(
            "ZG Company Settings", {"company": self.company}, "default_warehouse"
        )
        if not company_wh:
            self.skipTest("test company has no default warehouse in ZG Company Settings")
        user = self._make_van_user(None)
        frappe.defaults.set_user_default("company", self.company, user)
        self.assertEqual(resolve(user)["warehouse"], company_wh)

    # -- collections route rule --------------------------------------------

    def _admin_invoice_for(self, customer: str) -> None:
        """An open invoice the driver didn't make (admin-created)."""
        frappe.set_user("Administrator")
        result = create_order(
            client_id=f"test-settings-adm-{random_string(8)}",
            customer=customer,
            items=[{"item_code": self.item_code, "qty": 1, "rate": 10}],
            warehouse=self.warehouse,
            payment_type="Credit",
        )
        self.assertTrue(result["success"], result.get("error"))

    def _collect(self, customer: str) -> dict:
        frappe.set_user(self.user)
        return create_collection(
            client_id=f"test-settings-col-{random_string(8)}",
            customer=customer,
            amount=5,
        )

    def test_collection_allowed_from_customer_the_driver_invoiced(self) -> None:
        # Not on the driver's route, but the driver sold to them — the same
        # customers whose balances the app shows on New Collection.
        self._sell(warehouse=self.warehouse, payment_type="Credit")
        self.assertTrue(self._collect(self.customer)["success"])

    def test_collection_refused_from_unrelated_customer(self) -> None:
        other = self._make_customer(f"Settings Other {random_string(8)}")
        self._admin_invoice_for(other)
        with self.assertRaises(frappe.PermissionError):
            self._collect(other)

    def test_collection_from_any_customer_when_restriction_off(self) -> None:
        other = self._make_customer(f"Settings Other {random_string(8)}")
        self._admin_invoice_for(other)
        self._set_profile(restrict_collections_to_route="No")
        self.assertEqual(resolve(self.user)["restrict_collections_to_route"], 0)
        self.assertTrue(self._collect(other)["success"])

    def test_collection_cannot_target_another_customers_invoice(self) -> None:
        # Allowed customer + someone else's invoice must be refused, or the
        # payment would post against the other customer's receivable.
        self._sell(warehouse=self.warehouse, payment_type="Credit")
        other = self._make_customer(f"Settings Other {random_string(8)}")
        self._admin_invoice_for(other)
        other_si = frappe.get_all(
            "Sales Invoice", filters={"customer": other, "docstatus": 1}, pluck="name"
        )[0]
        frappe.set_user(self.user)
        with self.assertRaises(frappe.PermissionError):
            create_collection(
                client_id=f"test-settings-col-{random_string(8)}",
                customer=self.customer,
                amount=5,
                sales_invoice=other_si,
            )

    def test_driver_cannot_convert_another_drivers_order(self) -> None:
        from zatgo_core.services.vansalex_service import confirm_order, create_sales_order

        other_driver = self._make_van_user(self.warehouse)
        frappe.set_user(other_driver)
        so = create_sales_order(
            client_id=f"test-settings-so-{random_string(8)}",
            customer=self.customer,
            items=[{"item_code": self.item_code, "qty": 1, "rate": 10}],
        )["data"]["erp_name"]
        frappe.set_user(self.user)
        with self.assertRaises(frappe.PermissionError):
            confirm_order(
                client_id=f"test-settings-cf-{random_string(8)}",
                sales_order=so,
                payment_type="Credit",
            )

    # -- bank / account choice -----------------------------------------------

    def _pe_for(self, si_name: str) -> frappe._dict:
        names = frappe.get_all(
            "Payment Entry Reference",
            filters={"reference_name": si_name, "docstatus": 1},
            pluck="parent",
        )
        self.assertEqual(len(names), 1)
        return frappe.db.get_value(
            "Payment Entry", names[0], ["paid_to", "reference_no", "mode_of_payment"], as_dict=True
        )

    def _choice_on_for_site(self) -> None:
        from zatgo_core.services.vansalex_access import _client_rows

        if not _client_rows().get("sales_invoice.multiple_payment_accounts", 1):
            self.skipTest("this site has 'Choose payment account' switched off")

    def test_bank_refused_unless_allowed(self) -> None:
        self._set_profile(allow_bank_payment="No", bank_account=self.bank_account)
        with self.assertRaises(frappe.PermissionError):
            self._sell(warehouse=self.warehouse, payment_type="Bank")

    def test_default_payment_type_bank_needs_bank_allowed(self) -> None:
        self._set_profile(default_payment_type="Bank", allow_bank_payment="No")
        self.assertEqual(resolve(self.user)["default_payment_type"], "Cash")
        self._set_profile(allow_bank_payment="Yes")
        eff = resolve(self.user)
        self.assertEqual(eff["default_payment_type"], "Bank")
        self.assertEqual(eff["allow_bank_payment"], 1)

    def test_bank_invoice_pays_into_the_default_bank_account(self) -> None:
        self._set_profile(allow_bank_payment="Yes", bank_account=self.bank_account)
        self.assertEqual(resolve(self.user)["bank_account"], self.bank_account)
        result = self._sell(warehouse=self.warehouse, payment_type="Bank")
        self.assertTrue(result["success"], result.get("error"))
        si = frappe.get_doc("Sales Invoice", result["data"]["erp_name"])
        self.assertEqual(si.custom_payment_type, "Bank")
        self.assertEqual(si.custom_bank_account, self.bank_account)
        self.assertFalse(si.custom_cash_account)
        self.assertEqual(flt(si.outstanding_amount), 0)
        pe = self._pe_for(si.name)
        self.assertEqual(pe.paid_to, self.bank_account)
        # No reference typed: ERPNext's required reference is the invoice no.
        self.assertEqual(pe.reference_no, si.name)

    def test_bank_reference_no_reaches_the_payment_entry(self) -> None:
        self._set_profile(allow_bank_payment="Yes", bank_account=self.bank_account)
        result = self._sell(warehouse=self.warehouse, payment_type="Bank", bank_reference_no=" TRF-0077 ")
        si = frappe.get_doc("Sales Invoice", result["data"]["erp_name"])
        self.assertEqual(si.custom_bank_reference_no, "TRF-0077")
        self.assertEqual(self._pe_for(si.name).reference_no, "TRF-0077")

    def test_driver_picks_another_bank_account(self) -> None:
        self._choice_on_for_site()
        self._set_profile(allow_bank_payment="Yes", bank_account=self.bank_account)
        result = self._sell(
            warehouse=self.warehouse, payment_type="Bank", bank_account=self.other_bank_account
        )
        si = frappe.get_doc("Sales Invoice", result["data"]["erp_name"])
        self.assertEqual(si.custom_bank_account, self.other_bank_account)
        self.assertEqual(self._pe_for(si.name).paid_to, self.other_bank_account)

    def test_driver_picks_another_cash_account(self) -> None:
        self._choice_on_for_site()
        result = self._sell(warehouse=self.warehouse, payment_type="Cash", cash_account=self.till_account)
        si = frappe.get_doc("Sales Invoice", result["data"]["erp_name"])
        self.assertEqual(si.custom_cash_account, self.till_account)
        self.assertEqual(self._pe_for(si.name).paid_to, self.till_account)

    def test_account_choice_needs_the_feature(self) -> None:
        name = frappe.db.get_value("ZG Van Sale Profile", {"user": self.user}, "name")
        doc = frappe.get_doc("ZG Van Sale Profile", name)
        doc.append(
            "access_overrides", {"access_key": "sales_invoice.multiple_payment_accounts", "disabled": 1}
        )
        doc.save(ignore_permissions=True)
        with self.assertRaises(frappe.PermissionError):
            self._sell(warehouse=self.warehouse, payment_type="Cash", cash_account=self.till_account)
        # Naming the default account is not a choice.
        result = self._sell(warehouse=self.warehouse, payment_type="Cash", cash_account=self.cash_account)
        self.assertTrue(result["success"], result.get("error"))
        frappe.set_user(self.user)
        accounts = selectable_payment_accounts()
        self.assertEqual([a["name"] for a in accounts["cash_account"]], [self.cash_account])

    def test_account_of_the_wrong_type_is_refused(self) -> None:
        self._choice_on_for_site()
        self._set_profile(allow_bank_payment="Yes", bank_account=self.bank_account)
        with self.assertRaisesRegex(frappe.ValidationError, "not an enabled Bank-type"):
            self._sell(warehouse=self.warehouse, payment_type="Bank", bank_account=self.cash_account)
        self.assertFalse(
            frappe.db.exists("Sales Invoice", {"customer": self.customer, "docstatus": ["<", 2]})
        )

    def test_selectable_accounts_default_first(self) -> None:
        self._choice_on_for_site()
        self._set_profile(bank_account=self.other_bank_account)
        frappe.set_user(self.user)
        accounts = selectable_payment_accounts()
        bank = [a["name"] for a in accounts["bank_account"]]
        self.assertEqual(bank[0], self.other_bank_account)
        self.assertEqual(accounts["bank_account"][0]["is_default"], 1)
        self.assertIn(self.bank_account, bank)
        cash = [a["name"] for a in accounts["cash_account"]]
        self.assertEqual(cash[0], self.cash_account)
        self.assertIn(self.till_account, cash)
        self.assertNotIn(self.bank_account, cash)

    def test_convert_order_to_bank_invoice(self) -> None:
        from zatgo_core.services.vansalex_service import confirm_order, create_sales_order

        self._set_profile(allow_bank_payment="Yes", bank_account=self.bank_account)
        frappe.set_user(self.user)
        so = create_sales_order(
            client_id=f"test-settings-so-{random_string(8)}",
            customer=self.customer,
            items=[{"item_code": self.item_code, "qty": 1, "rate": 10}],
        )["data"]["erp_name"]
        result = confirm_order(
            client_id=f"test-settings-cf-{random_string(8)}",
            sales_order=so,
            warehouse=self.warehouse,
            payment_type="Bank",
            bank_reference_no="CHQ-12",
        )
        si = frappe.get_doc("Sales Invoice", result["data"]["erp_name"])
        self.assertEqual(si.custom_payment_type, "Bank")
        self.assertEqual(si.custom_bank_account, self.bank_account)
        self.assertEqual(self._pe_for(si.name).reference_no, "CHQ-12")

    def test_profile_bank_account_must_be_a_bank_account(self) -> None:
        with self.assertRaisesRegex(frappe.ValidationError, "not an enabled Bank-type"):
            self._set_profile(bank_account=self.cash_account)

    def test_context_exposes_bank_settings(self) -> None:
        from zatgo_core.api.v1.vansalex.me import context

        self._set_profile(allow_bank_payment="Yes", bank_account=self.bank_account)
        frappe.set_user(self.user)
        data = context()["data"]
        self.assertEqual(data["settings"]["bank_account"], self.bank_account)
        self.assertEqual(data["settings"]["allow_bank_payment"], 1)
        self.assertTrue(data["access"]["features"]["sales_invoice.bank_payment"])

    # -- item selling rate -----------------------------------------------------

    def test_item_list_shows_the_price_list_rate_when_standard_rate_is_empty(self) -> None:
        from zatgo_core.services.erpnext_reads import list_items

        price_list = frappe.db.get_value("Price List", {"selling": 1, "enabled": 1}, "name")
        if not price_list:
            self.skipTest("no selling price list on this site")
        frappe.db.set_single_value("Selling Settings", "selling_price_list", price_list)
        frappe.db.set_value("Item", self.item_code, "standard_rate", 0)
        frappe.db.delete("Item Price", {"item_code": self.item_code, "price_list": price_list})
        frappe.get_doc(
            {
                "doctype": "Item Price",
                "item_code": self.item_code,
                "price_list": price_list,
                "price_list_rate": 37.5,
            }
        ).insert(ignore_permissions=True)
        # Newest first, capped per page: look through the pages for the item.
        row = None
        for page in range(1, 10):
            data = list_items(page=page, page_size=100)["data"]
            row = next((r for r in data if r["item_code"] == self.item_code), None)
            if row or len(data) < 100:
                break
        self.assertIsNotNone(row, "item not listed")
        self.assertEqual(row["standard_rate"], 37.5)
        self.assertEqual(row["rate"], 37.5)
        frappe.db.set_value("Item", self.item_code, "last_purchase_rate", 21)
        row = list_items(page=1, page_size=100)["data"]
        row = next((r for r in row if r["item_code"] == self.item_code), None) or row
        if isinstance(row, dict):
            self.assertEqual(row["buying_rate"], 21)  # the default rate on a purchase
        # That price is the item's price: the rate check accepts it.
        from zatgo_core.services.vansalex_access import check_item_rates

        frappe.set_user(self.user)
        check_item_rates([{"item_code": self.item_code, "rate": 37.5}])
        with self.assertRaises(frappe.PermissionError):
            check_item_rates([{"item_code": self.item_code, "rate": 30}], price_list)
