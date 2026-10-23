"""Audit H2: what a VanSaleX field user may do with stock and money outside the
module / feature switches.

Covers services/vansalex_stock_rules.py and its callers:
- stock.transfer: own van <-> a "VanSaleX Transfer Point" only, behind the
  `inventory.transfer` feature (off by default);
- stock.adjust: own van, decrease only, within Max Stock Write-off Qty, behind
  `inventory.adjust` (off by default);
- opening stock through the item sync (item bundle, sync.batch): admin only;
- the DocType backstop on Stock Entry, Payment Entry Pay / Internal Transfer
  and the sales feature switches (rate, discount, credit, warehouse) for a
  field user who bypasses the vansalex API (/api/resource, Desk);
- ensure_vansale_perms seeds each grant once and then leaves it to the admin.

Real documents on the local site, no mocks. Client-level switches and settings
are flipped per test and restored in the same test's `finally` (see the
teardown-commit gotcha), so the site is left as it was.
"""

from __future__ import annotations

from contextlib import contextmanager
from threading import Thread
from unittest.mock import patch

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import cint, flt, get_test_client, random_string, today
from frappe.utils.password import update_password

from zatgo_core.api.v1.sync.batch import batch as sync_batch
from zatgo_core.api.v1.vansalex import stock as stock_api
from zatgo_core.services import vansalex_access as access
from zatgo_core.services.item_sync_service import sync_item_bundle
from zatgo_core.services.vansalex_stock_rules import is_transfer_point
from zatgo_core.setup.ensure_vansale_perms import _seeded_key, ensure_vansale_perms
from zatgo_core.setup.ensure_vansalex_access import ensure_vansalex_access
from zatgo_core.tests.integration._fixtures import (
    get_or_create_cash_mode_of_payment,
    get_or_create_test_company,
)

SETTINGS = "VanSaleX Settings"


class TestVansalexStockScope(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        ensure_vansalex_access()
        cls.company = get_or_create_test_company()
        cash = frappe.db.get_value(
            "Account", {"company": cls.company, "account_type": "Cash", "is_group": 0}, "name"
        )
        get_or_create_cash_mode_of_payment(cls.company, cash)
        cls.van = cls._make_warehouse("VSX Scope Van")
        cls.peer_van = cls._make_warehouse("VSX Scope Peer Van")
        cls.main = cls._make_warehouse("VSX Scope Main")
        cls.other = cls._make_warehouse("VSX Scope Other")
        cls.item = cls._make_item("VSX-SCOPE", cls.van, cls.peer_van, cls.main, cls.other)
        cls.priced = cls._make_item("VSX-PRICED", cls.van, standard_rate=10)

    def setUp(self) -> None:
        self.user = self._make_van_user(self.van)
        self.customer = self._make_customer(f"Scope Test {random_string(8)}")

    def tearDown(self) -> None:
        frappe.set_user("Administrator")

    # -- fixtures --------------------------------------------------------------------

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
    def _make_item(cls, prefix: str, *warehouses: str, standard_rate: float = 0) -> str:
        code = f"{prefix}-{random_string(6).upper()}"
        frappe.get_doc(
            {
                "doctype": "Item",
                "item_code": code,
                "item_name": code,
                "item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
                "stock_uom": "Nos",
                "is_stock_item": 1,
                "standard_rate": standard_rate,
            }
        ).insert(ignore_permissions=True)
        for wh in warehouses:
            frappe.get_doc(
                {
                    "doctype": "Stock Entry",
                    "stock_entry_type": "Material Receipt",
                    "company": cls.company,
                    "items": [{"item_code": code, "qty": 1000, "t_warehouse": wh, "basic_rate": 10}],
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
    def _make_van_user(cls, warehouse: str, user_type: str = "Field User", roles=("VanSale User",)) -> str:
        email = f"vansale.scope.test.{random_string(6).lower()}@zatgo.test"
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "VanSale",
                "last_name": "ScopeTest",
                "send_welcome_email": 0,
                "roles": [{"role": r} for r in roles],
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

    def _as_user(self) -> None:
        frappe.set_user(self.user)

    def _set_profile(self, **values) -> None:
        name = frappe.db.get_value("ZG Van Sale Profile", {"user": self.user}, "name")
        frappe.db.set_value("ZG Van Sale Profile", name, values)
        frappe.clear_document_cache("ZG Van Sale Profile", name)

    @contextmanager
    def _client(self, **switches: int):
        """Flip client-level rows (keys with '.' passed as '__'), restore after."""
        keys = {k.replace("__", "."): v for k, v in switches.items()}
        rows = {
            r.access_key: (r.name, cint(r.enabled))
            for r in frappe.get_all(
                "VanSaleX Access",
                filters={"parenttype": SETTINGS, "access_key": ["in", list(keys)]},
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

    @contextmanager
    def _setting(self, field: str, value):
        old = frappe.db.get_single_value(SETTINGS, field)
        try:
            frappe.db.set_single_value(SETTINGS, field, value)
            frappe.clear_document_cache(SETTINGS, SETTINGS)
            yield
        finally:
            frappe.db.set_single_value(SETTINGS, field, old)
            frappe.clear_document_cache(SETTINGS, SETTINGS)

    @contextmanager
    def _flag(self, warehouse: str, field: str):
        try:
            frappe.db.set_value("Warehouse", warehouse, field, 1)
            yield
        finally:
            frappe.db.set_value("Warehouse", warehouse, field, 0)

    def _transfer_point(self, warehouse: str):
        return self._flag(warehouse, "zg_vansalex_transfer_point")

    @staticmethod
    def _qty(item: str, warehouse: str) -> float:
        return flt(frappe.db.get_value("Bin", {"item_code": item, "warehouse": warehouse}, "actual_qty"))

    def _cid(self) -> str:
        return f"scope-{random_string(10)}"

    def _transfer(self, **kw) -> dict:
        self._as_user()
        args = {"client_id": self._cid(), "item_code": self.item, "qty": 2, "company": self.company}
        args.update(kw)
        return stock_api.transfer(**args)

    def _adjust(self, delta: float, **kw) -> dict:
        self._as_user()
        args = {"client_id": self._cid(), "item_code": self.item, "delta": delta, "company": self.company}
        args.update(kw)
        return stock_api.adjust(**args)

    def _stock_entry(self, purpose: str, rows: list[dict]):
        return frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "stock_entry_type": purpose,
                "company": self.company,
                "items": [{"item_code": self.item, "basic_rate": 10, **r} for r in rows],
            }
        )

    # -- catalog and schema ------------------------------------------------------------

    def test_new_keys_are_seeded_off_and_the_warehouse_flag_exists(self) -> None:
        for key in ("inventory.transfer", "inventory.adjust"):
            self.assertIn(key, access.CATALOG)
            self.assertEqual(access.CATALOG[key][3], 0, "fail-closed by default")
            self.assertEqual(access.CATALOG[key][2], "inventory")
            self.assertIn(key, access.ROW_KEYS)
        rows = frappe.get_all(
            "VanSaleX Access",
            filters={"parenttype": SETTINGS, "access_key": ["in", ["inventory.transfer", "inventory.adjust"]]},
            pluck="access_key",
        )
        self.assertEqual(len(rows), 2)
        self.assertTrue(frappe.get_meta("Warehouse").has_field("zg_vansalex_transfer_point"))
        options = frappe.get_meta("ZG Van Sale Profile Access").get_field("access_key").options.split("\n")
        self.assertTrue({"inventory.transfer", "inventory.adjust"} <= set(options))
        self.assertTrue(frappe.get_meta(SETTINGS).has_field("max_adjust_qty"))

    def test_a_feature_is_only_on_while_its_module_is(self) -> None:
        with self._client(inventory__transfer=1, inventory=0):
            self.assertFalse(access.is_enabled("inventory.transfer", self.user))
        with self._client(inventory__transfer=1):
            self.assertTrue(access.is_enabled("inventory.transfer", self.user))

    def test_transfer_point_needs_the_same_company_a_leaf_and_the_tick(self) -> None:
        self.assertFalse(is_transfer_point(self.main, self.company))
        with self._transfer_point(self.main):
            self.assertTrue(is_transfer_point(self.main, self.company))
            self.assertFalse(is_transfer_point(self.main, "Some Other Company"))
            self.assertFalse(is_transfer_point(None, self.company))
            self.assertFalse(is_transfer_point("No Such Warehouse", self.company))

    # -- transfer (R1) -----------------------------------------------------------------

    def test_transfer_is_closed_until_the_feature_is_on(self) -> None:
        with self._transfer_point(self.main):
            with self.assertRaises(frappe.PermissionError):
                self._transfer(from_warehouse=self.main, to_warehouse=self.van)
        # ... and, the feature on, until a warehouse is ticked as a transfer point
        with self._client(inventory__transfer=1):
            with self.assertRaises(frappe.PermissionError):
                self._transfer(from_warehouse=self.main, to_warehouse=self.van)

    def test_transfer_between_the_van_and_a_transfer_point(self) -> None:
        van_before, main_before = self._qty(self.item, self.van), self._qty(self.item, self.main)
        with self._client(inventory__transfer=1), self._transfer_point(self.main):
            res = self._transfer(from_warehouse=self.main, to_warehouse=self.van, qty=3)
            self.assertTrue(res["meta"]["submitted"])
            self.assertEqual(self._qty(self.item, self.van), van_before + 3)
            self.assertEqual(self._qty(self.item, self.main), main_before - 3)
            # a blank from_warehouse is the van: push stock back
            self._transfer(to_warehouse=self.main, qty=1)
            self.assertEqual(self._qty(self.item, self.van), van_before + 2)
            self.assertEqual(self._qty(self.item, self.main), main_before - 2)

    def test_transfer_replay_is_idempotent(self) -> None:
        cid = self._cid()
        with self._client(inventory__transfer=1), self._transfer_point(self.main):
            first = self._transfer(client_id=cid, from_warehouse=self.main, to_warehouse=self.van)
            again = self._transfer(client_id=cid, from_warehouse=self.main, to_warehouse=self.van)
        self.assertTrue(again["meta"]["idempotent"])
        self.assertEqual(first["data"]["name"], again["data"]["name"])
        self.assertEqual(frappe.db.count("Stock Entry", {"zatgo_client_id": cid}), 1)

    def test_transfer_refuses_any_other_warehouse(self) -> None:
        with self._client(inventory__transfer=1), self._transfer_point(self.main):
            before = frappe.db.count("Stock Entry")
            for src, dst in (
                (self.other, self.van),  # pull from a warehouse that isn't a transfer point
                (self.van, self.other),  # push to one
                (self.main, self.other),  # not touching the van at all
                (self.peer_van, self.van),  # another driver's van
                (self.van, self.peer_van),
            ):
                with self.assertRaises(frappe.PermissionError, msg=f"{src} -> {dst}"):
                    self._transfer(from_warehouse=src, to_warehouse=dst)
            self.assertEqual(frappe.db.count("Stock Entry"), before, "nothing was booked")

    def test_a_transfer_point_is_not_a_van_for_someone_else(self) -> None:
        # ticking the peer's van does not let this driver reach it from the other side either
        with self._client(inventory__transfer=1), self._transfer_point(self.main):
            with self.assertRaises(frappe.PermissionError):
                self._transfer(from_warehouse=self.main, to_warehouse=self.peer_van)

    def test_admin_transfer_is_unchanged(self) -> None:
        # not a field user: any pair, no feature needed (inventory module only)
        frappe.set_user("Administrator")
        res = stock_api.transfer(
            client_id=self._cid(),
            item_code=self.item,
            qty=1,
            from_warehouse=self.other,
            to_warehouse=self.main,
            company=self.company,
        )
        self.assertTrue(res["meta"]["created"])

    # -- adjust (R2) -------------------------------------------------------------------

    def test_adjust_is_closed_until_the_feature_is_on(self) -> None:
        with self.assertRaises(frappe.PermissionError):
            self._adjust(-1)

    def test_adjust_is_a_decrease_in_the_own_van_with_the_reason_kept(self) -> None:
        before = self._qty(self.item, self.van)
        with self._client(inventory__adjust=1):
            res = self._adjust(-2, reason="Broken in transit")
            self.assertEqual(self._qty(self.item, self.van), before - 2)
            self.assertEqual(frappe.db.get_value("Stock Entry", res["data"]["name"], "remarks"), "Broken in transit")
            self.assertEqual(frappe.db.get_value("Stock Entry", res["data"]["name"], "purpose"), "Material Issue")
            with self.assertRaises(frappe.PermissionError):
                self._adjust(5)  # stock does not appear from nowhere
            with self.assertRaises(frappe.PermissionError):
                self._adjust(-1, warehouse=self.other)
            with self.assertRaises(frappe.PermissionError):
                self._adjust(-1, warehouse=self.peer_van)
        self.assertEqual(self._qty(self.item, self.van), before - 2)

    def test_adjust_cap(self) -> None:
        with self._client(inventory__adjust=1), self._setting("max_adjust_qty", 3):
            with self.assertRaises(frappe.PermissionError):
                self._adjust(-4)
            self.assertTrue(self._adjust(-3)["meta"]["created"])
        with self._client(inventory__adjust=1), self._setting("max_adjust_qty", 0):
            self.assertTrue(self._adjust(-4)["meta"]["created"])  # 0 = no cap

    def test_admin_adjust_is_unchanged(self) -> None:
        frappe.set_user("Administrator")
        before = self._qty(self.item, self.other)
        stock_api.adjust(
            client_id=self._cid(), item_code=self.item, delta=4, warehouse=self.other, company=self.company
        )
        self.assertEqual(self._qty(self.item, self.other), before + 4)
        stock_api.adjust(
            client_id=self._cid(), item_code=self.item, delta=-4, warehouse=self.other, company=self.company
        )
        self.assertEqual(self._qty(self.item, self.other), before)

    # -- opening stock through the item sync (R3) ----------------------------------------

    def _item_payload(self, **extra) -> dict:
        code = f"VSX-OPEN-{random_string(6).upper()}"
        return {
            "item_code": code,
            "item_name": code,
            "item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
            "stock_uom": "Nos",
            "selling_rate": 12,
            "company": self.company,
            "opening_warehouse": self.van,
            **extra,
        }

    def test_field_user_cannot_book_opening_stock_and_nothing_is_written(self) -> None:
        payload = self._item_payload(opening_quantity=50)
        self._as_user()
        with self.assertRaises(frappe.PermissionError):
            sync_item_bundle(client_id=self._cid(), item=payload)
        frappe.set_user("Administrator")
        self.assertFalse(frappe.db.exists("Item", payload["item_code"]))
        self.assertEqual(self._qty(payload["item_code"], self.van), 0)

    def test_field_user_can_still_create_an_item_without_opening_stock(self) -> None:
        payload = self._item_payload()
        self._as_user()
        res = sync_item_bundle(client_id=self._cid(), item=payload)
        self.assertTrue(res["meta"]["created"])
        frappe.set_user("Administrator")
        self.assertEqual(self._qty(payload["item_code"], self.van), 0)

    def test_batch_sync_reports_the_refusal_and_creates_nothing(self) -> None:
        payload = self._item_payload(opening_quantity=5)
        self._as_user()
        res = sync_batch(
            [{"id": "1", "entity_type": "product", "op": "create", "client_id": self._cid(), "payload": payload}]
        )
        result = res["data"]["results"][0]
        self.assertFalse(result["success"])
        self.assertIn("opening stock", result["error"])
        frappe.set_user("Administrator")
        self.assertFalse(frappe.db.exists("Item", payload["item_code"]))

    def test_admin_still_books_opening_stock(self) -> None:
        payload = self._item_payload(opening_quantity=7, purchase_rate=5)
        frappe.set_user("Administrator")
        sync_item_bundle(client_id=self._cid(), item=payload)
        self.assertEqual(self._qty(payload["item_code"], self.van), 7)
        remarks = frappe.get_all(
            "Stock Entry Detail", filters={"item_code": payload["item_code"]}, pluck="parent"
        )
        self.assertEqual(frappe.db.get_value("Stock Entry", remarks[0], "remarks"), "Opening stock")

    def test_vansale_admin_role_books_opening_stock_too(self) -> None:
        admin = self._make_van_user(self.van, roles=("VanSale User", "VanSale Admin"))
        payload = self._item_payload(opening_quantity=3, purchase_rate=5)
        frappe.set_user(admin)
        sync_item_bundle(client_id=self._cid(), item=payload)
        frappe.set_user("Administrator")
        self.assertEqual(self._qty(payload["item_code"], self.van), 3)

    # -- backstop: Stock Entry (R4a) -----------------------------------------------------

    def test_backstop_stock_entry_purposes(self) -> None:
        self._as_user()
        # Receipt and anything that is not a transfer / write-off: never, even
        # with both features on
        with self._client(inventory__adjust=1, inventory__transfer=1):
            with self.assertRaisesRegex(frappe.PermissionError, "Stock Entry type"):
                self._stock_entry("Material Receipt", [{"t_warehouse": self.van, "qty": 1}]).insert()
            for purpose in ("Manufacture", "Repack", "Material Consumption", "Send to Subcontractor"):
                with self.assertRaises(frappe.PermissionError, msg=purpose):
                    access.check_doc_access(
                        self._stock_entry(purpose, [{"s_warehouse": self.van, "qty": 1}]), "validate"
                    )
        # Transfer: feature off, then on but between the wrong warehouses
        row = {"s_warehouse": self.main, "t_warehouse": self.van, "qty": 1}
        with self.assertRaisesRegex(frappe.PermissionError, "not enabled for your account"):
            self._stock_entry("Material Transfer", [row]).insert()
        with self._client(inventory__transfer=1), self._transfer_point(self.main):
            bad = {"s_warehouse": self.other, "t_warehouse": self.van, "qty": 1}
            with self.assertRaisesRegex(frappe.PermissionError, "not a VanSaleX transfer point"):
                self._stock_entry("Material Transfer", [row, bad]).insert()  # one bad line is enough
            ok = self._stock_entry("Material Transfer", [row]).insert()
            self.assertEqual(ok.docstatus, 0)
        # Write-off: the same rules as stock.adjust
        issue = {"s_warehouse": self.van, "qty": 1}
        with self.assertRaisesRegex(frappe.PermissionError, "not enabled for your account"):
            self._stock_entry("Material Issue", [issue]).insert()
        with self._client(inventory__adjust=1):
            self.assertEqual(self._stock_entry("Material Issue", [issue]).insert().docstatus, 0)
            with self.assertRaisesRegex(frappe.PermissionError, "assigned warehouse"):
                self._stock_entry("Material Issue", [{"s_warehouse": self.other, "qty": 1}]).insert()

    def test_backstop_stock_entry_submit_of_a_draft_somebody_else_made(self) -> None:
        frappe.set_user("Administrator")
        draft = self._stock_entry(
            "Material Transfer", [{"s_warehouse": self.other, "t_warehouse": self.van, "qty": 1}]
        ).insert()
        self._as_user()
        with self._client(inventory__transfer=1), self._transfer_point(self.main):
            with self.assertRaisesRegex(frappe.PermissionError, "not a VanSaleX transfer point"):
                frappe.get_doc("Stock Entry", draft.name).submit()
        frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("Stock Entry", draft.name, "docstatus"), 0)

    def test_backstop_stock_entry_admin_and_non_field_users_are_free(self) -> None:
        frappe.set_user("Administrator")
        se = self._stock_entry("Material Receipt", [{"t_warehouse": self.other, "qty": 1}]).insert()
        self.assertTrue(se.name)
        frappe.set_user(self._make_van_user(self.van, user_type="Admin"))  # Admin-type profile
        self.assertTrue(self._stock_entry("Material Receipt", [{"t_warehouse": self.other, "qty": 1}]).insert().name)

    # -- backstop: Payment Entry (R4b) -----------------------------------------------------

    def _payment_entry(self, payment_type: str):
        return frappe.get_doc({"doctype": "Payment Entry", "payment_type": payment_type, "company": self.company})

    def test_backstop_payment_entry_pay_and_internal_transfer(self) -> None:
        self._as_user()
        for ptype in ("Pay", "Internal Transfer"):
            with self.assertRaisesRegex(frappe.PermissionError, "isn't available to VanSaleX field users", msg=ptype):
                self._payment_entry(ptype).insert()
        # the purchase bill's own payment (flagged by invoice_cash_payment_service) passes the backstop
        auto = self._payment_entry("Pay")
        auto.flags.zatgo_auto_cash_payment = True
        access.check_doc_access(auto, "before_insert")
        access.check_doc_access(auto, "validate")
        # a validate of a Receive is not a second collections check
        with self._client(collections=0):
            access.check_doc_access(self._payment_entry("Receive"), "validate")
            with self.assertRaises(frappe.PermissionError):
                access.check_doc_access(self._payment_entry("Receive"), "before_insert")

    def test_backstop_payment_entry_admin_is_free(self) -> None:
        frappe.set_user("Administrator")
        access.check_doc_access(self._payment_entry("Pay"), "before_insert")  # no-op for Administrator
        frappe.set_user(self._make_van_user(self.van, roles=("VanSale User", "VanSale Admin")))
        access.check_doc_access(self._payment_entry("Pay"), "before_insert")

    # -- backstop: sales feature switches off the vansalex API (R4c) -------------------------

    def _invoice(self, rate: float = 10, **doc) -> "frappe.model.document.Document":
        row = {"item_code": self.priced, "qty": 2, "rate": rate, "warehouse": self.van}
        row.update(doc.pop("row", {}))
        return frappe.get_doc(
            {
                "doctype": "Sales Invoice",
                "customer": self.customer,
                "company": self.company,
                "posting_date": today(),
                "update_stock": 1,
                "set_warehouse": self.van,
                "custom_payment_type": "Cash",
                "items": [row],
                **doc,
            }
        )

    def _order(self, rate: float = 10, **doc):
        order = self._invoice(rate, **doc)
        order.doctype = "Sales Order"
        return order

    def test_backstop_rate_needs_edit_rate(self) -> None:
        self._as_user()
        access.check_doc_access(self._invoice(10), "before_insert")  # the item's price
        with self.assertRaises(frappe.PermissionError):
            access.check_doc_access(self._invoice(5), "before_insert")
        with self.assertRaises(frappe.PermissionError):
            access.check_doc_access(self._order(5), "before_insert")
        with self._client(sales_invoice__edit_rate=1):
            access.check_doc_access(self._invoice(5), "before_insert")
        # the real insert path is wired to the same check
        with self.assertRaisesRegex(frappe.PermissionError, "Changing the rate"):
            self._invoice(5).insert()

    def test_backstop_blank_rate_is_filled_with_the_price(self) -> None:
        self._as_user()
        inv = self._invoice(0)
        access.check_doc_access(inv, "before_insert")
        self.assertEqual(flt(inv.items[0].rate), 10)

    def test_backstop_discount_is_capped_and_needs_its_feature(self) -> None:
        self._as_user()
        with self._setting("max_discount_percent", 10):
            access.check_doc_access(self._invoice(additional_discount_percentage=5), "before_insert")
            with self.assertRaises(frappe.ValidationError):
                access.check_doc_access(self._invoice(additional_discount_percentage=20), "before_insert")
            # an absolute discount counts by what share of the net it takes
            with self.assertRaises(frappe.ValidationError):
                access.check_doc_access(self._invoice(discount_amount=10), "before_insert")  # 10 of 20
            access.check_doc_access(self._invoice(discount_amount=1), "before_insert")  # 5%
            # line discount: its own feature (off by default), then the same cap
            line = {"discount_percentage": 5, "price_list_rate": 10, "rate": 9.5}
            with self.assertRaises(frappe.PermissionError):
                access.check_doc_access(self._invoice(9.5, row=line), "before_insert")
            with self._client(sales_invoice__line_discount=1):
                access.check_doc_access(self._invoice(9.5, row=line), "before_insert")
                over = {"discount_percentage": 20, "price_list_rate": 10, "rate": 8}
                with self.assertRaises(frappe.ValidationError):
                    access.check_doc_access(self._invoice(8, row=over), "before_insert")
        with self._setting("max_discount_percent", 0):  # discounts off altogether
            with self.assertRaises(frappe.PermissionError):
                access.check_doc_access(self._invoice(additional_discount_percentage=1), "before_insert")

    def test_backstop_credit_sale(self) -> None:
        self._set_profile(allow_credit_sales="No")
        self._as_user()
        access.check_doc_access(self._invoice(), "before_insert")  # Cash
        for kw in ({"custom_payment_type": "Credit"}, {"custom_payment_type": ""}):
            with self.assertRaises(frappe.PermissionError, msg=str(kw)):
                access.check_doc_access(self._invoice(**kw), "before_insert")
        # nothing on the payment type but paid on the invoice itself (POS payments): not credit
        paid = self._invoice(custom_payment_type="", payments=[{"mode_of_payment": "Cash", "amount": 20}])
        access.check_doc_access(paid, "before_insert")
        frappe.set_user("Administrator")
        self._set_profile(allow_credit_sales="Yes")
        self._as_user()
        access.check_doc_access(self._invoice(custom_payment_type="Credit"), "before_insert")

    def test_backstop_warehouse_follows_change_warehouse(self) -> None:
        self._as_user()
        access.check_doc_access(self._invoice(), "validate")  # the van
        elsewhere = {"warehouse": self.other}
        with self.assertRaises(frappe.PermissionError):
            access.check_doc_access(self._invoice(row=elsewhere), "validate")
        with self.assertRaises(frappe.PermissionError):
            access.check_doc_access(self._invoice(set_warehouse=self.other, row={"warehouse": self.van}), "validate")
        with self.assertRaises(frappe.PermissionError):
            access.check_doc_access(self._order(row=elsewhere), "validate")
        frappe.set_user("Administrator")
        self._set_profile(allow_warehouse_change="Yes")
        self._as_user()
        with self._flag(self.other, "zg_vansalex_selectable"):
            access.check_doc_access(self._invoice(row=elsewhere), "validate")

    def test_backstop_leaves_returns_admins_and_api_built_documents_alone(self) -> None:
        self._set_profile(allow_credit_sales="No")
        self._as_user()
        bad = self._invoice(5, custom_payment_type="Credit", row={"warehouse": self.other})
        with self.assertRaises(frappe.PermissionError):
            access.check_doc_access(bad, "before_insert")
        # built (and checked) by the vansalex API
        access.mark_api_validated(bad)
        access.check_doc_access(bad, "before_insert")
        access.check_doc_access(bad, "validate")
        # a return has its own rules (sales_return module, the original's rates)
        ret = self._invoice(5, is_return=1, custom_payment_type="Credit", row={"warehouse": self.other, "qty": -1})
        access.check_doc_access(ret, "before_insert")
        access.check_doc_access(ret, "validate")
        frappe.set_user(self._make_van_user(self.van, roles=("VanSale User", "VanSale Admin")))
        access.check_doc_access(self._invoice(5, row={"warehouse": self.other}), "validate")

    # -- the same, over HTTP (/api/resource, a real session) ---------------------------------

    def _http(self, client, method: str, path: str, **kwargs):
        """One WSGI request in its own thread (frappe.local is per thread), the
        way Frappe's own API tests do it."""
        site, out = frappe.local.site, {}

        def run() -> None:
            with patch("frappe.app.get_site_name", return_value=site):
                out["response"] = getattr(client, method)(path, **kwargs)

        thread = Thread(target=run)
        thread.start()
        thread.join()
        return out["response"]

    def test_resource_api_enforces_the_backstop_for_a_logged_in_field_user(self) -> None:
        password = f"Vsx!{random_string(10)}9aZ#"
        update_password(self.user, password)
        frappe.db.commit()
        client = get_test_client()
        login = self._http(client, "post", "/api/method/login", data={"usr": self.user, "pwd": password})
        self.assertEqual(login.status_code, 200, login.get_data(as_text=True))

        # a session that works: the van user may read a warehouse
        read = self._http(client, "get", f"/api/resource/Warehouse/{self.van}")
        self.assertEqual(read.status_code, 200, read.get_data(as_text=True))

        before = frappe.db.count("Stock Entry")
        posts = {
            "Stock Entry": {
                "stock_entry_type": "Material Receipt",
                "company": self.company,
                "items": [{"item_code": self.item, "qty": 5, "t_warehouse": self.van, "basic_rate": 10}],
            },
            "Payment Entry": {"payment_type": "Pay", "company": self.company},
            "Sales Invoice": {
                "customer": self.customer,
                "company": self.company,
                "posting_date": today(),
                "update_stock": 1,
                "set_warehouse": self.van,
                "custom_payment_type": "Cash",
                "items": [{"item_code": self.priced, "qty": 1, "rate": 5, "warehouse": self.van}],
            },
        }
        for doctype, body in posts.items():
            res = self._http(client, "post", f"/api/resource/{doctype}", json=body)
            self.assertEqual(res.status_code, 403, f"{doctype}: {res.get_data(as_text=True)[:300]}")
            self.assertIn("PermissionError", res.get_data(as_text=True))
        self.assertEqual(frappe.db.count("Stock Entry"), before, "no stock was booked")
        self.assertFalse(
            frappe.db.exists("Sales Invoice", {"customer": self.customer}), "no invoice was created"
        )

    # -- ensure_vansale_perms is seed-once (R5) ------------------------------------------------

    def _perm_row(self, doctype: str, role: str = "VanSale User"):
        return frappe.db.get_value(
            "Custom DocPerm", {"parent": doctype, "role": role}, ["name", "write", "create"], as_dict=True
        )

    def _forget(self, doctype: str, role: str = "VanSale User") -> None:
        frappe.db.delete("DefaultValue", {"defkey": _seeded_key(doctype, role), "parent": "__global"})
        frappe.clear_cache()

    def test_perms_are_seeded_once_and_then_left_to_the_admin(self) -> None:
        deleted, edited = "Address", "Item Price"
        try:
            ensure_vansale_perms()
            self.assertTrue(frappe.db.get_global(_seeded_key(deleted, "VanSale User")))
            # an admin removes a grant and clears another flag
            frappe.db.delete("Custom DocPerm", {"parent": deleted, "role": "VanSale User"})
            row = self._perm_row(edited)
            frappe.db.set_value("Custom DocPerm", row.name, "write", 0)
            ensure_vansale_perms()  # = the next migrate
            self.assertIsNone(self._perm_row(deleted), "a removed grant stays removed")
            self.assertEqual(self._perm_row(edited).write, 0, "an edited flag is not reset")
        finally:
            # leave the site as it was: forget the markers so the seed restores both
            for dt in (deleted, edited):
                self._forget(dt)
            ensure_vansale_perms()
            frappe.db.commit()
        self.assertTrue(self._perm_row(deleted))
        self.assertEqual(self._perm_row(edited).write, 1)

    def test_first_run_tops_an_existing_grant_up_without_removing_anything(self) -> None:
        doctype = "Item Price"
        row = self._perm_row(doctype)
        try:
            self._forget(doctype)
            frappe.db.set_value("Custom DocPerm", row.name, "write", 0)
            ensure_vansale_perms()  # a site upgrading from the always-reconcile version
            after = self._perm_row(doctype)
            self.assertEqual(after.write, 1)
            self.assertEqual(after.name, row.name)
            self.assertTrue(frappe.db.get_global(_seeded_key(doctype, "VanSale User")))
        finally:
            ensure_vansale_perms()
            frappe.db.commit()
