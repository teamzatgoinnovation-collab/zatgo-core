"""VanSaleX Modules & Features: effective access and server-side enforcement.

Covers services/vansalex_access.py and where it's applied:
- effective(): client rows, catalog defaults, parent→feature dependency,
  per-user profile switch-offs, keys derived from existing settings;
- migration seeding only adds rows and never overwrites an admin's switch;
- config_version moves when a switch changes;
- the vansalex endpoints reject a disabled module/feature (API layer);
- the DocType backstop rejects a field user's direct insert/edit on any
  entry point, while the Cash invoice's own Payment Entry still goes through.

Client-level switches are flipped per test and restored in the same test's
`finally` (not tearDownClass — see the teardown-commit gotcha), so the site's
global configuration is left as it was.
"""

from __future__ import annotations

from contextlib import contextmanager

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import cint, random_string

from zatgo_core.api.v1.vansalex import collections as collections_api
from zatgo_core.api.v1.vansalex import me as me_api
from zatgo_core.api.v1.vansalex import orders as orders_api
from zatgo_core.api.v1.vansalex import returns as returns_api
from zatgo_core.api.v1.vansalex import trips as trips_api
from zatgo_core.services import vansalex_access as access
from zatgo_core.services.vansalex_service import create_order
from zatgo_core.setup.ensure_vansalex_access import ensure_vansalex_access
from zatgo_core.tests.integration._fixtures import (
    get_or_create_cash_mode_of_payment,
    get_or_create_test_company,
)


class TestVansalexModuleAccess(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        ensure_vansalex_access()
        cls.company = get_or_create_test_company()
        cls.cash_account = frappe.db.get_value(
            "Account", {"company": cls.company, "account_type": "Cash", "is_group": 0}, "name"
        )
        get_or_create_cash_mode_of_payment(cls.company, cls.cash_account)
        cls.warehouse = cls._make_warehouse("VanSaleAccessTest")
        cls.item_code = cls._make_stocked_item(cls.warehouse, qty=1000)
        cls.card_mode = cls._make_card_mode()

    def setUp(self) -> None:
        self.customer = self._make_customer(f"Access Test {random_string(8)}")
        self.user = self._make_van_user(self.warehouse)

    def tearDown(self) -> None:
        frappe.set_user("Administrator")

    # -- fixtures (mirrors test_vansalex_settings.py) ----------------------------

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
        code = f"VANSALE-ACC-{random_string(6).upper()}"
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
                "items": [{"item_code": code, "qty": qty, "t_warehouse": warehouse, "basic_rate": 10}],
            }
        ).insert(ignore_permissions=True).submit()
        return code

    @classmethod
    def _make_card_mode(cls) -> str:
        name = "VSX Access Test Card"
        if not frappe.db.exists("Mode of Payment", name):
            frappe.get_doc(
                {"doctype": "Mode of Payment", "mode_of_payment": name, "type": "Bank", "enabled": 1}
            ).insert(ignore_permissions=True)
        return name

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
    def _make_van_user(cls, warehouse: str, user_type: str = "Field User") -> str:
        email = f"vansale.access.test.{random_string(6).lower()}@zatgo.test"
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "VanSale",
                "last_name": "AccessTest",
                "send_welcome_email": 0,
                "roles": [{"role": "VanSale User"}],
            }
        ).insert(ignore_permissions=True)
        frappe.get_doc(
            {
                "doctype": "ZG Van Sale Profile",
                "user": email,
                "enabled": 1,
                "user_type": user_type,
                "warehouse": warehouse,
                "allow_credit_sales": "Yes",
                "restrict_collections_to_route": "No",
            }
        ).insert(ignore_permissions=True)
        return email

    def _disable_for_user(self, *keys: str) -> None:
        name = frappe.db.get_value("ZG Van Sale Profile", {"user": self.user}, "name")
        doc = frappe.get_doc("ZG Van Sale Profile", name)
        for key in keys:
            doc.append("access_overrides", {"access_key": key, "disabled": 1})
        doc.save(ignore_permissions=True)

    @contextmanager
    def _client(self, **switches: int):
        """Flip client-level rows (keys with '.' passed as '__'), restore after."""
        keys = {k.replace("__", "."): v for k, v in switches.items()}
        rows = {
            r.access_key: (r.name, cint(r.enabled))
            for r in frappe.get_all(
                "VanSaleX Access",
                filters={"parenttype": "VanSaleX Settings", "access_key": ["in", list(keys)]},
                fields=["name", "access_key", "enabled"],
            )
        }
        self.assertEqual(set(rows), set(keys), "access rows must be seeded")
        try:
            for key, value in keys.items():
                frappe.db.set_value("VanSaleX Access", rows[key][0], "enabled", value)
            frappe.db.commit()
            yield
        finally:
            for _key, (name, old) in rows.items():
                frappe.db.set_value("VanSaleX Access", name, "enabled", old)
            frappe.db.commit()

    def _as_user(self):
        frappe.set_user(self.user)

    def _sell(self, **kwargs) -> dict:
        self._as_user()
        return create_order(
            client_id=f"test-access-{random_string(8)}",
            customer=self.customer,
            items=[{"item_code": self.item_code, "qty": 1, "rate": 10}],
            **kwargs,
        )

    # -- effective configuration ----------------------------------------------------

    def test_seeded_rows_cover_catalog_and_existing_functionality_is_on(self) -> None:
        keys = set(
            frappe.get_all(
                "VanSaleX Access", filters={"parenttype": "VanSaleX Settings"}, pluck="access_key"
            )
        )
        self.assertTrue(set(access.ROW_KEYS) <= keys)
        eff = access.effective(self.user)
        self.assertEqual(set(eff["modules"]), set(access.MODULE_KEYS))
        self.assertEqual(set(eff["features"]), set(access.FEATURE_KEYS))
        self.assertIsInstance(eff["config_version"], int)

    def test_every_more_tab_entry_has_its_own_row_in_app_order(self) -> None:
        rows = frappe.get_all(
            "VanSaleX Access",
            filters={"parenttype": "VanSaleX Settings"},
            fields=["access_key", "label", "app_location", "enabled"],
            order_by="idx",
        )
        keys = [r.access_key for r in rows]
        self.assertEqual(keys, list(access.ROW_KEYS))
        for key in ("activities", "documents", "my_performance"):
            row = next(r for r in rows if r.access_key == key)
            self.assertTrue(row.enabled)  # split out of existing functionality
            self.assertIn("More →", row.app_location)
        labels = {r.access_key: r.label for r in rows}
        self.assertEqual(labels["route_plan"], "Plan & Route")
        self.assertEqual(labels["reports"], "Reports")

    def test_split_rows_start_from_the_switch_they_came_from(self) -> None:
        settings = frappe.get_single("VanSaleX Settings")
        snapshot = [(r.access_key, r.enabled) for r in settings.access]
        try:
            for r in settings.access:
                if r.access_key == "route_plan":
                    r.enabled = 0
            settings.access = [r for r in settings.access if r.access_key != "activities"]
            settings.save(ignore_permissions=True)
            ensure_vansalex_access()
            row = frappe.db.get_value(
                "VanSaleX Access",
                {"parenttype": "VanSaleX Settings", "access_key": "activities"},
                "enabled",
            )
            self.assertEqual(cint(row), 0)  # hidden before the split, still hidden
        finally:
            settings = frappe.get_single("VanSaleX Settings")
            old = dict(snapshot)
            for r in settings.access:
                r.enabled = old.get(r.access_key, r.enabled)
            settings.save(ignore_permissions=True)
            frappe.db.commit()

    def test_split_entries_are_switched_on_their_own(self) -> None:
        # Activities alone still lists today's stops; switching it off too
        # closes the endpoint (Dashboard / Plan & Route / My Performance off).
        self._disable_for_user("dashboard", "route_plan", "my_performance")
        self._as_user()
        self.assertIn("data", trips_api.list())
        frappe.set_user("Administrator")
        self._disable_for_user("activities")
        self._as_user()
        with self.assertRaises(frappe.PermissionError):
            trips_api.list()

    def test_documents_alone_can_list_and_print(self) -> None:
        invoice = self._sell(payment_type="Credit")["data"]["erp_name"]
        from unittest.mock import patch

        frappe.set_user("Administrator")
        self._disable_for_user("sales_invoice", "sales_return", "dashboard", "reports", "my_performance")
        self._as_user()
        self.assertIn("data", orders_api.list())
        with patch("frappe.utils.pdf.get_pdf", return_value=b"%PDF-stub"):
            self.assertTrue(orders_api.pdf(invoice)["data"]["pdf_base64"])

    def test_disabling_a_module_turns_off_its_features(self) -> None:
        with self._client(collections=0):
            eff = access.effective(self.user)
            self.assertFalse(eff["modules"]["collections"])
            self.assertFalse(eff["features"]["collections.card"])
            self.assertFalse(eff["features"]["collections.multiple_payment_modes"])
        self.assertTrue(access.effective(self.user)["modules"]["collections"])

    def test_profile_can_only_switch_off(self) -> None:
        self._disable_for_user("customers", "sales_invoice.print_80mm")
        eff = access.effective(self.user)
        self.assertFalse(eff["modules"]["customers"])
        self.assertFalse(eff["features"]["sales_invoice.print_80mm"])
        # Other users of the same client are unaffected.
        other = self._make_van_user(self.warehouse)
        self.assertTrue(access.effective(other)["modules"]["customers"])
        # A profile can't turn on what the client has off.
        with self._client(reports=0):
            self.assertFalse(access.effective(self.user)["modules"]["reports"])

    def test_derived_keys_follow_existing_settings(self) -> None:
        name = frappe.db.get_value("ZG Van Sale Profile", {"user": self.user}, "name")
        frappe.db.set_value("ZG Van Sale Profile", name, "allow_credit_sales", "No")
        eff = access.effective(self.user)
        self.assertFalse(eff["features"]["sales_invoice.credit_sale"])
        from zatgo_core.services.vansalex_settings import resolve

        self.assertEqual(eff["modules"]["sales_order"], bool(cint(resolve(self.user)["allow_orders"])))

    def test_profile_rejects_duplicate_and_unknown_keys(self) -> None:
        name = frappe.db.get_value("ZG Van Sale Profile", {"user": self.user}, "name")
        doc = frappe.get_doc("ZG Van Sale Profile", name)
        doc.append("access_overrides", {"access_key": "customers"})
        doc.append("access_overrides", {"access_key": "customers"})
        self.assertRaises(frappe.ValidationError, doc.save, ignore_permissions=True)
        doc.reload()
        doc.append("access_overrides", {"access_key": "no_such_module"})
        self.assertRaises(frappe.ValidationError, doc.save, ignore_permissions=True)

    def test_seeding_never_overwrites_and_version_moves(self) -> None:
        with self._client(inventory=0):
            ensure_vansalex_access()
            self.assertFalse(access.effective(self.user)["modules"]["inventory"])
        settings = frappe.get_single("VanSaleX Settings")
        before = cint(settings.config_version)
        row = next(r for r in settings.access if r.access_key == "reports")
        original = cint(row.enabled)
        try:
            row.enabled = 0 if original else 1
            settings.save(ignore_permissions=True)
            self.assertEqual(cint(settings.config_version), before + 1)
            settings.reload()
            settings.save(ignore_permissions=True)  # no switch changed
            self.assertEqual(cint(settings.config_version), before + 1)
        finally:
            settings.reload()
            next(r for r in settings.access if r.access_key == "reports").enabled = original
            settings.save(ignore_permissions=True)
            frappe.db.commit()

    def test_me_context_carries_access(self) -> None:
        self._disable_for_user("route_plan")
        self._as_user()
        data = me_api.context()["data"]
        self.assertIn("access", data)
        self.assertFalse(data["access"]["modules"]["route_plan"])
        self.assertTrue(data["access"]["modules"]["sales_invoice"])

    # -- API layer -------------------------------------------------------------------

    def test_disabled_module_endpoints_are_rejected(self) -> None:
        self._disable_for_user("collections", "route_plan", "sales_return")
        self._as_user()
        with self.assertRaises(frappe.PermissionError):
            collections_api.create(client_id=f"c-{random_string(8)}", customer=self.customer, amount=5)
        with self.assertRaises(frappe.PermissionError):
            trips_api.create(client_id=f"t-{random_string(8)}", customer=self.customer)
        with self.assertRaises(frappe.PermissionError):
            returns_api.returnable(sales_invoice="ANY")
        # Read-only lists the dashboard also uses stay open while it is on.
        self.assertIn("data", returns_api.list())

    def test_orders_off_rejects_order_even_for_admin_profile(self) -> None:
        name = frappe.db.get_value("ZG Van Sale Profile", {"user": self.user}, "name")
        frappe.db.set_value("ZG Van Sale Profile", name, "user_type", "Admin")
        settings = frappe.get_single("VanSaleX Settings")
        old = cint(settings.allow_orders)
        try:
            frappe.db.set_single_value("VanSaleX Settings", "allow_orders", 0)
            frappe.db.commit()
            frappe.clear_document_cache("VanSaleX Settings", "VanSaleX Settings")
            self._as_user()
            with self.assertRaises(frappe.PermissionError):
                orders_api.create_order_draft(
                    client_id=f"so-{random_string(8)}",
                    customer=self.customer,
                    items=[{"item_code": self.item_code, "qty": 1}],
                )
        finally:
            frappe.set_user("Administrator")
            frappe.db.set_single_value("VanSaleX Settings", "allow_orders", old)
            frappe.db.commit()
            frappe.clear_document_cache("VanSaleX Settings", "VanSaleX Settings")

    def test_sales_invoice_disabled_rejects_invoice(self) -> None:
        self._disable_for_user("sales_invoice")
        self._as_user()
        with self.assertRaises(frappe.PermissionError):
            orders_api.create(
                client_id=f"o-{random_string(8)}",
                customer=self.customer,
                items=[{"item_code": self.item_code, "qty": 1, "rate": 10}],
                payment_type="Cash",
            )

    def test_print_papers_are_independent(self) -> None:
        invoice = self._sell(payment_type="Credit")["data"]["erp_name"]
        from unittest.mock import patch

        from zatgo_core.setup.ensure_print_formats import PRINT_FORMAT_80MM_NAME

        self._disable_for_user("sales_invoice.print_80mm")
        self._as_user()
        with patch("frappe.utils.pdf.get_pdf", return_value=b"%PDF-stub"):
            with self.assertRaises(frappe.PermissionError):
                orders_api.pdf(invoice, print_format=PRINT_FORMAT_80MM_NAME)
            self.assertTrue(orders_api.pdf(invoice)["data"]["pdf_base64"])  # A4 still on

    def test_item_rate_is_fixed_unless_edit_rate_is_on(self) -> None:
        frappe.db.set_value("Item", self.item_code, "standard_rate", 10)
        try:
            self.assertTrue(self._sell(payment_type="Credit")["data"]["erp_name"])  # 10 = standard
            frappe.set_user("Administrator")
            with self.assertRaises(frappe.PermissionError):
                self._as_user()
                create_order(
                    client_id=f"test-rate-{random_string(8)}",
                    customer=self.customer,
                    items=[{"item_code": self.item_code, "qty": 1, "rate": 7.5}],
                    payment_type="Credit",
                )
            frappe.set_user("Administrator")
            with self._client(sales_invoice__edit_rate=1):
                self._as_user()
                res = create_order(
                    client_id=f"test-rate-{random_string(8)}",
                    customer=self.customer,
                    items=[{"item_code": self.item_code, "qty": 1, "rate": 7.5}],
                    payment_type="Credit",
                )
                frappe.set_user("Administrator")
                inv = frappe.get_doc("Sales Invoice", res["data"]["erp_name"])
                self.assertEqual(inv.items[0].rate, 7.5)
        finally:
            frappe.set_user("Administrator")
            frappe.db.set_value("Item", self.item_code, "standard_rate", 0)

    def test_zero_rate_gets_the_items_price_without_edit_rate(self) -> None:
        # "0 / blank lets ERPNext fill the price in" -- but ERPNext only fills
        # from an Item Price, never from the Standard Selling Rate the app
        # shows, so a 0 sent by a driver without Edit item rate was a free sale.
        frappe.db.set_value("Item", self.item_code, "standard_rate", 10)
        try:
            self._as_user()
            res = create_order(
                client_id=f"test-rate-{random_string(8)}",
                customer=self.customer,
                items=[{"item_code": self.item_code, "qty": 2, "rate": 0}],
                payment_type="Credit",
            )
            frappe.set_user("Administrator")
            inv = frappe.get_doc("Sales Invoice", res["data"]["erp_name"])
            self.assertEqual(inv.items[0].rate, 10)
            self.assertEqual(inv.net_total, 20)
        finally:
            frappe.set_user("Administrator")
            frappe.db.set_value("Item", self.item_code, "standard_rate", 0)

    def _priced_line(self, discount: float, qty: float = 2) -> list[dict]:
        return [{"item_code": self.item_code, "qty": qty, "rate": 10, "discount_percentage": discount}]

    def test_line_discount_is_off_until_switched_on(self) -> None:
        frappe.db.set_value("Item", self.item_code, "standard_rate", 10)
        try:
            self._as_user()
            with self.assertRaises(frappe.PermissionError):
                create_order(
                    client_id=f"test-ld-{random_string(8)}",
                    customer=self.customer,
                    items=self._priced_line(10),
                    payment_type="Credit",
                )
            frappe.set_user("Administrator")
            with self._client(sales_invoice__line_discount=1):
                self._as_user()
                res = create_order(
                    client_id=f"test-ld-{random_string(8)}",
                    customer=self.customer,
                    items=self._priced_line(10),
                    payment_type="Credit",
                )
                frappe.set_user("Administrator")
                line = frappe.get_doc("Sales Invoice", res["data"]["erp_name"]).items[0]
                # The item's price stays visible; ERPNext's own line discount.
                self.assertEqual(line.price_list_rate, 10)
                self.assertEqual(line.discount_percentage, 10)
                self.assertEqual(line.rate, 9)
                self.assertEqual(line.amount, 18)
        finally:
            frappe.set_user("Administrator")
            frappe.db.set_value("Item", self.item_code, "standard_rate", 0)

    def test_line_discount_is_capped_by_max_discount(self) -> None:
        frappe.db.set_value("Item", self.item_code, "standard_rate", 10)
        old = frappe.db.get_single_value("VanSaleX Settings", "max_discount_percent")
        try:
            frappe.db.set_single_value("VanSaleX Settings", "max_discount_percent", 5)
            frappe.db.commit()
            frappe.clear_document_cache("VanSaleX Settings", "VanSaleX Settings")
            with self._client(sales_invoice__line_discount=1):
                self._as_user()
                with self.assertRaises(frappe.ValidationError):
                    create_order(
                        client_id=f"test-ld-{random_string(8)}",
                        customer=self.customer,
                        items=self._priced_line(10),
                        payment_type="Credit",
                    )
        finally:
            frappe.set_user("Administrator")
            frappe.db.set_single_value("VanSaleX Settings", "max_discount_percent", old)
            frappe.db.set_value("Item", self.item_code, "standard_rate", 0)
            frappe.db.commit()
            frappe.clear_document_cache("VanSaleX Settings", "VanSaleX Settings")

    def test_line_discount_carries_from_order_to_invoice(self) -> None:
        from zatgo_core.services.vansalex_service import confirm_order, create_sales_order

        frappe.db.set_value("Item", self.item_code, "standard_rate", 10)
        try:
            with self._client(sales_invoice__line_discount=1):
                self._as_user()
                so = create_sales_order(
                    client_id=f"test-ld-so-{random_string(8)}",
                    customer=self.customer,
                    items=self._priced_line(20, qty=1),
                )["data"]["erp_name"]
                si = confirm_order(
                    client_id=f"test-ld-si-{random_string(8)}",
                    sales_order=so,
                    payment_type="Credit",
                )["data"]["erp_name"]
                frappe.set_user("Administrator")
                line = frappe.get_doc("Sales Invoice", si).items[0]
                self.assertEqual(line.discount_percentage, 20)
                self.assertEqual(line.rate, 8)
        finally:
            frappe.set_user("Administrator")
            frappe.db.set_value("Item", self.item_code, "standard_rate", 0)

    def test_total_discount_has_its_own_switch(self) -> None:
        with self._client(sales_invoice__discount=0):
            self.assertFalse(access.effective(self.user)["features"]["sales_invoice.discount"])
            with self.assertRaises(frappe.PermissionError):
                self._sell(payment_type="Credit", discount_percentage=5)
        frappe.set_user("Administrator")
        self.assertTrue(self._sell(payment_type="Credit", discount_percentage=5)["data"]["erp_name"])

    def test_split_payment_needs_the_feature(self) -> None:
        self._disable_for_user("sales_invoice.multiple_payment_modes")
        with self.assertRaises(frappe.PermissionError):
            self._sell(
                payment_type="Cash",
                payment_details=[
                    {"payment_method": "Cash", "amount": 4},
                    {"payment_method": "Cash", "amount": 7.5},
                ],
            )

    def test_card_collection_needs_the_feature(self) -> None:
        self._disable_for_user("collections.card")
        self._as_user()
        with self.assertRaises(frappe.PermissionError):
            collections_api.create(
                client_id=f"c-{random_string(8)}",
                customer=self.customer,
                amount=5,
                method=self.card_mode,
            )

    # -- DocType backstop ------------------------------------------------------------

    def test_backstop_blocks_field_user_direct_writes(self) -> None:
        self._disable_for_user("customers")
        self._as_user()
        with self.assertRaises(frappe.PermissionError):
            self._make_customer(f"Blocked {random_string(6)}")  # e.g. via /api/resource or Desk
        frappe.set_user("Administrator")
        self._make_customer(f"Allowed {random_string(6)}")  # not a field user

    def test_cash_invoice_payment_is_not_a_collection(self) -> None:
        self._disable_for_user("collections")
        res = self._sell(payment_type="Cash")
        invoice = res["data"]["erp_name"]
        self.assertTrue(
            frappe.db.exists(
                "Payment Entry Reference",
                {"reference_name": invoice, "docstatus": 1},
            )
        )
