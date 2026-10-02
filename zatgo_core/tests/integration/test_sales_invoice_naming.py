"""User-wise Sales Invoice naming series (ZG Sales Invoice Naming Settings).

Covers services/sales_invoice_naming.py through the Sales Invoice
before_insert hook, the way each real entry point reaches it: plain
doc.insert() (desk save), frappe.client.insert (REST create), ERPNext's
make_return_doc ("Create > Return / Credit Note"), and the VanSaleX API
service functions.

Test series are "ZT..." prefixes so running this suite never advances a real
site's invoice counters (e.g. S1-/V1-). They're added to the Sales Invoice
naming_series options for the run and removed again in tearDownClass, along
with this class's rules; the settings' unmapped-user behaviour is restored
inside the one test that changes it.
"""

from __future__ import annotations

import contextvars
import re
import threading

import frappe
from erpnext.controllers.sales_and_purchase_return import make_return_doc
from frappe.client import insert as client_insert
from frappe.custom.doctype.property_setter.property_setter import make_property_setter
from frappe.model.document import Document
from frappe.model.naming import get_default_naming_series
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import random_string, today

from zatgo_core.services.naming_series import get_naming_series_options
from zatgo_core.services.sales_invoice_naming import (
    NOT_CONFIGURED_MESSAGE,
    SETTINGS_DOCTYPE,
    UNMAPPED_BLOCK,
    UNMAPPED_USE_DEFAULT,
    get_session_user_series,
)
from zatgo_core.services.vansalex_service import create_order, create_sales_return
from zatgo_core.tests.integration._fixtures import get_or_create_test_company

WEB, WEB_RET = "ZTS1-.##", "ZTS1-RET-.##"
VAN, VAN_RET = "ZTV1-.##", "ZTV1-RET-.##"
VAN_B, VAN_B_RET = "ZTB-.##", "ZTB-RET-.##"
WEB_WIDER = "ZTS1-.###"  # same counter as WEB; only used by a validation test
TEST_SERIES = [WEB, WEB_RET, VAN, VAN_RET, VAN_B, VAN_B_RET, WEB_WIDER]
# A different counter that can emit WEB's names (ZTS1-101). Added to the
# options only inside the test that checks it is refused: while it is an
# option, WEB can't be used in a rule at all.
WEB_OVERLAP = "ZTS1-1.##"

SECOND_COMPANY = "ZatGo Naming Test Co B"
OPTIONS_SETTER = {"doc_type": "Sales Invoice", "field_name": "naming_series", "property": "options"}


def _number(name: str, series: str) -> int:
    prefix = series.split(".")[0]
    match = re.fullmatch(re.escape(prefix) + r"(\d{2,})", name)
    if not match:
        raise AssertionError(f"{name!r} is not a {series} name")
    return int(match.group(1))


class TestSalesInvoiceNaming(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.company = get_or_create_test_company()
        cls.company_b = cls._get_or_create_second_company()

        cls.original_options = get_naming_series_options("Sales Invoice")
        cls.original_setter = frappe.db.get_value("Property Setter", OPTIONS_SETTER, ["name", "value"], as_dict=True)
        cls._set_si_options(cls.original_options + TEST_SERIES)
        cls.default_series = get_default_naming_series("Sales Invoice")

        cls.service_item = cls._make_item(stocked=False)
        cls.customer = cls._make_customer("ZT Naming Test Customer")
        cls.van_warehouse = cls._make_warehouse("ZTNamingVan")
        cls.stocked_item = cls._make_item(stocked=True, warehouse=cls.van_warehouse, qty=500)

        # Naming is per user, not per role. "VanSale User" is there because on
        # sites where setup/ensure_vansale_perms.py has run, its Custom DocPerm
        # rows currently make Frappe ignore the standard Sales Invoice perms
        # (Accounts User included).
        accounting = ["Accounts User", "Sales User", "VanSale User"]
        cls.web_user = cls._make_user("web", accounting)
        cls.van_user = cls._make_user("van", ["VanSale User"])
        frappe.get_doc(
            {
                "doctype": "ZG Van Sale Profile",
                "user": cls.van_user,
                "enabled": 1,
                "user_type": "Field User",
                "warehouse": cls.van_warehouse,
            }
        ).insert(ignore_permissions=True)
        cls.unmapped_user = cls._make_user("unmapped", accounting)
        cls.multi_user = cls._make_user("multi", accounting)
        cls.manager = cls._make_user("manager", ["ZG Invoice Naming Manager"])
        cls.sales_only = cls._make_user("salesonly", ["Sales User"])
        cls.test_users = {cls.web_user, cls.van_user, cls.unmapped_user, cls.multi_user, cls.manager}

        cls.behavior_before = frappe.get_single(SETTINGS_DOCTYPE).unmapped_user_behavior
        cls._configure(cls.default_rules())
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls) -> None:
        frappe.set_user("Administrator")
        settings = frappe.get_single(SETTINGS_DOCTYPE)
        settings.rules = [r for r in settings.rules if r.user not in cls.test_users]
        settings.unmapped_user_behavior = cls.behavior_before or UNMAPPED_USE_DEFAULT
        settings.save(ignore_permissions=True)
        if cls.original_setter:
            frappe.db.set_value("Property Setter", cls.original_setter.name, "value", cls.original_setter.value)
        else:
            frappe.db.delete("Property Setter", OPTIONS_SETTER)
        frappe.clear_cache(doctype="Sales Invoice")
        frappe.db.commit()
        super().tearDownClass()

    def tearDown(self) -> None:
        frappe.set_user("Administrator")

    # -- fixtures -----------------------------------------------------------

    @classmethod
    def default_rules(cls) -> list[dict]:
        return [
            {"user": cls.web_user, "company": cls.company, "normal_series": WEB, "return_series": WEB_RET},
            {"user": cls.van_user, "company": cls.company, "normal_series": VAN, "return_series": VAN_RET},
            {"user": cls.multi_user, "company": cls.company, "normal_series": VAN, "return_series": VAN_RET},
            {"user": cls.multi_user, "company": cls.company_b, "normal_series": VAN_B, "return_series": VAN_B_RET},
        ]

    @classmethod
    def _configure(cls, rules: list[dict], behavior: str | None = None) -> None:
        """Replace this class's rules (other rows on the site are kept) and commit."""
        settings = frappe.get_single(SETTINGS_DOCTYPE)
        settings.rules = [r for r in settings.rules if r.user not in cls.test_users]
        for rule in rules:
            settings.append("rules", {"enabled": 1, **rule})
        if behavior:
            settings.unmapped_user_behavior = behavior
        settings.save(ignore_permissions=True)
        frappe.db.commit()

    @classmethod
    def _set_si_options(cls, options: list[str]) -> None:
        make_property_setter(
            "Sales Invoice",
            "naming_series",
            "options",
            "\n".join(dict.fromkeys(o for o in options if o)),
            "Text",
            validate_fields_for_doctype=False,
        )
        frappe.clear_cache(doctype="Sales Invoice")

    @classmethod
    def _get_or_create_second_company(cls) -> str:
        if not frappe.db.exists("Company", SECOND_COMPANY):
            frappe.get_doc(
                {
                    "doctype": "Company",
                    "company_name": SECOND_COMPANY,
                    "abbr": "ZNTB",
                    "default_currency": "SAR",
                    "country": "Saudi Arabia",
                }
            ).insert(ignore_permissions=True)
        return SECOND_COMPANY

    @classmethod
    def _make_user(cls, label: str, roles: list[str]) -> str:
        email = f"zt.naming.{label}.{random_string(6).lower()}@zatgo.test"
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "ZT Naming",
                "last_name": label,
                "send_welcome_email": 0,
                "roles": [{"role": r} for r in roles],
            }
        ).insert(ignore_permissions=True)
        return email

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
    def _make_warehouse(cls, label: str) -> str:
        abbr = frappe.db.get_value("Company", cls.company, "abbr")
        name = f"{label} - {abbr}"
        if not frappe.db.exists("Warehouse", name):
            frappe.get_doc(
                {"doctype": "Warehouse", "warehouse_name": label, "company": cls.company}
            ).insert(ignore_permissions=True)
        return name

    @classmethod
    def _make_item(cls, stocked: bool, warehouse: str | None = None, qty: float = 0) -> str:
        code = f"ZT-NAMING-{random_string(6).upper()}"
        frappe.get_doc(
            {
                "doctype": "Item",
                "item_code": code,
                "item_name": code,
                "item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
                "stock_uom": "Nos",
                "is_stock_item": int(stocked),
            }
        ).insert(ignore_permissions=True)
        if stocked:
            frappe.get_doc(
                {
                    "doctype": "Stock Entry",
                    "stock_entry_type": "Material Receipt",
                    "company": cls.company,
                    "items": [{"item_code": code, "qty": qty, "t_warehouse": warehouse, "basic_rate": 10}],
                }
            ).insert(ignore_permissions=True).submit()
        return code

    def _invoice(self, company: str | None = None, submit: bool = False, **extra) -> Document:
        """A Sales Invoice saved as the current session user, like a desk save."""
        company = company or self.company
        doc = frappe.get_doc(
            {
                "doctype": "Sales Invoice",
                "customer": self.customer,
                "company": company,
                "currency": frappe.get_cached_value("Company", company, "default_currency"),
                "posting_date": today(),
                "due_date": today(),
                "items": [{"item_code": self.service_item, "qty": 1, "rate": 100}],
                **extra,
            }
        )
        doc.insert()
        if submit:
            doc.submit()
        return doc

    def _return_of(self, original: str) -> Document:
        """ERPNext's own return mapping, as "Create > Return / Credit Note" does."""
        ret = make_return_doc("Sales Invoice", original)
        ret.insert()
        return ret

    # -- Test 1-4: user → series, normal and return -------------------------

    def test_web_user_invoices_use_their_series_sequentially(self) -> None:
        frappe.set_user(self.web_user)
        first = self._invoice()
        second = self._invoice()
        self.assertEqual(first.naming_series, WEB)
        self.assertEqual(_number(second.name, WEB), _number(first.name, WEB) + 1)

    def test_web_user_return_uses_their_return_series(self) -> None:
        frappe.set_user(self.web_user)
        original = self._invoice(submit=True)
        ret = self._return_of(original.name)
        self.assertEqual(ret.naming_series, WEB_RET)
        _number(ret.name, WEB_RET)
        self.assertEqual(ret.return_against, original.name)
        self.assertNotEqual(ret.name, original.name)

    def test_van_user_invoice_through_vansale_api_uses_their_series(self) -> None:
        frappe.set_user(self.van_user)
        result = create_order(
            client_id=f"zt-naming-{random_string(10)}",
            customer=self.customer,
            items=[{"item_code": self.stocked_item, "qty": 1, "rate": 10}],
            warehouse=self.van_warehouse,
            company=self.company,
        )
        self.assertTrue(result["success"], result.get("error"))
        name = result["data"]["erp_name"]
        self.assertEqual(frappe.db.get_value("Sales Invoice", name, "naming_series"), VAN)
        _number(name, VAN)

    def test_van_user_return_through_vansale_api_uses_their_return_series(self) -> None:
        frappe.set_user(self.van_user)
        sale = create_order(
            client_id=f"zt-naming-{random_string(10)}",
            customer=self.customer,
            items=[{"item_code": self.stocked_item, "qty": 2, "rate": 10}],
            warehouse=self.van_warehouse,
            company=self.company,
        )
        original = sale["data"]["erp_name"]
        result = create_sales_return(
            client_id=f"zt-naming-ret-{random_string(10)}",
            return_against=original,
            items=[{"item_code": self.stocked_item, "qty": 1}],
            warehouse=self.van_warehouse,
        )
        self.assertTrue(result["success"], result.get("error"))
        ret = frappe.db.get_value(
            "Sales Invoice", result["data"]["erp_name"], ["name", "naming_series", "is_return"], as_dict=True
        )
        self.assertEqual((ret.naming_series, ret.is_return), (VAN_RET, 1))
        _number(ret.name, VAN_RET)

    def test_return_of_another_users_invoice_uses_the_returning_users_series(self) -> None:
        frappe.set_user(self.web_user)
        original = self._invoice(submit=True)
        frappe.set_user(self.multi_user)
        ret = self._return_of(original.name)
        self.assertEqual(ret.naming_series, VAN_RET)

    # -- Test 5: users without a rule ---------------------------------------

    def test_unmapped_user_keeps_erpnext_default_behaviour(self) -> None:
        frappe.set_user(self.unmapped_user)
        doc = self._invoice(submit=True)
        self.assertEqual(doc.naming_series, self.default_series)
        ret = self._return_of(doc.name)
        # The pre-existing generic "-RET-" switch still applies to them.
        self.assertIn("RET-", ret.naming_series)
        self.assertNotIn(ret.naming_series, TEST_SERIES)

    def test_block_setting_refuses_unmapped_users_but_not_mapped_or_administrator(self) -> None:
        try:
            self._configure(self.default_rules(), behavior=UNMAPPED_BLOCK)
            frappe.set_user(self.unmapped_user)
            with self.assertRaises(frappe.ValidationError) as ctx:
                self._invoice()
            self.assertIn(NOT_CONFIGURED_MESSAGE, str(ctx.exception))

            frappe.set_user(self.web_user)
            self.assertEqual(self._invoice().naming_series, WEB)

            frappe.set_user("Administrator")
            self.assertEqual(self._invoice().naming_series, self.default_series)
        finally:
            frappe.set_user("Administrator")
            frappe.db.rollback()
            self._configure(self.default_rules(), behavior=UNMAPPED_USE_DEFAULT)

    def test_disabled_rule_falls_back_like_an_unmapped_user(self) -> None:
        try:
            rules = self.default_rules()
            rules[0]["enabled"] = 0
            self._configure(rules)
            frappe.set_user(self.web_user)
            self.assertEqual(self._invoice().naming_series, self.default_series)
        finally:
            frappe.set_user("Administrator")
            self._configure(self.default_rules())

    # -- Test 6-7: API creation and a client-supplied series ----------------

    def test_rest_insert_overrides_a_client_supplied_series(self) -> None:
        payload = {
            "doctype": "Sales Invoice",
            "customer": self.customer,
            "company": self.company,
            "currency": "SAR",
            "posting_date": today(),
            "due_date": today(),
            "items": [{"item_code": self.service_item, "qty": 1, "rate": 50}],
        }
        # frappe.client.insert is what POST /api/resource/Sales Invoice runs.
        frappe.set_user(self.web_user)
        own = client_insert(dict(payload, naming_series=VAN))  # another user's series
        self.assertEqual(own["naming_series"], WEB)

        frappe.set_user(self.multi_user)
        inserted = client_insert(dict(payload, naming_series=WEB))
        self.assertEqual(inserted["naming_series"], VAN)
        _number(inserted["name"], VAN)

        bogus = client_insert(dict(payload, naming_series="HACK-.#####"))
        self.assertEqual(bogus["naming_series"], VAN)

    def test_return_flag_cannot_be_dodged_with_the_normal_series(self) -> None:
        frappe.set_user(self.web_user)
        original = self._invoice(submit=True)
        ret = make_return_doc("Sales Invoice", original.name)
        ret.naming_series = WEB  # try to number a credit note in the invoice sequence
        ret.insert()
        self.assertEqual(ret.naming_series, WEB_RET)

    # -- Test 8: concurrency --------------------------------------------------

    def _insert_concurrently(self, users: list[str], max_attempts: int = 1) -> tuple[dict, list[str]]:
        """Release one Sales Invoice insert per entry in `users` at the same
        instant, each in its own thread + DB connection. A worker that hits a
        QueryDeadlockError retries with a fresh document, like a client
        re-submitting (or Frappe's background-job runner). Returns
        ({user: [names]}, [repr of every error seen, including retried ones])."""
        for user in set(users):  # make sure each series counter row exists
            frappe.set_user(user)
            self._invoice()
        frappe.db.commit()
        frappe.set_user("Administrator")

        site, sites_path = frappe.local.site, frappe.local.sites_path
        barrier = threading.Barrier(len(users))
        names: dict[str, list[str]] = {u: [] for u in users}
        errors: list[str] = []

        def worker(user: str) -> None:
            frappe.init(site, sites_path=sites_path)
            frappe.connect()
            try:
                frappe.set_user(user)
                barrier.wait(timeout=30)
                for _attempt in range(max_attempts):
                    doc = frappe.get_doc(
                        {
                            "doctype": "Sales Invoice",
                            "customer": self.customer,
                            "company": self.company,
                            "currency": "SAR",
                            "posting_date": today(),
                            "due_date": today(),
                            "items": [{"item_code": self.service_item, "qty": 1, "rate": 10}],
                        }
                    )
                    try:
                        doc.insert()
                        frappe.db.commit()
                        names[user].append(doc.name)
                        return
                    except frappe.QueryDeadlockError as e:
                        frappe.db.rollback()
                        errors.append(repr(e))
            except Exception as e:
                frappe.db.rollback()
                errors.append(repr(e))
            finally:
                frappe.destroy()

        # Each worker gets an empty context, so frappe.local is its own.
        threads = [
            threading.Thread(target=contextvars.Context().run, args=(worker, user)) for user in users
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=120)
        return names, errors

    def test_concurrent_inserts_on_one_series_never_share_a_number(self) -> None:
        # Frappe's counter is a row lock on tabSeries. On MariaDB 11.8
        # (innodb_snapshot_isolation=ON) a racing insert can be refused with
        # error 1020 ("Record has changed since last read"), which Frappe
        # raises as QueryDeadlockError (HTTP 508); that rolls back cleanly and
        # never yields a duplicate or a skipped number.
        workers = 6
        names, errors = self._insert_concurrently([self.web_user] * workers, max_attempts=20)

        self.assertTrue(all("QueryDeadlockError" in e for e in errors), errors)
        created = names[self.web_user]
        self.assertEqual(len(created), workers, errors)
        numbers = sorted(_number(n, WEB) for n in created)
        self.assertEqual(numbers, list(range(numbers[0], numbers[0] + workers)), created)

    def test_users_on_different_series_do_not_contend(self) -> None:
        for _round in range(4):
            names, errors = self._insert_concurrently([self.web_user, self.van_user])
            self.assertEqual(errors, [])
            _number(names[self.web_user][0], WEB)
            _number(names[self.van_user][0], VAN)

    # -- Test 9: existing invoices -------------------------------------------

    def test_existing_invoices_keep_their_names_and_amendments_follow_the_original(self) -> None:
        try:
            self._configure([r for r in self.default_rules() if r["user"] != self.web_user])
            frappe.set_user(self.web_user)
            old = self._invoice(submit=True)
            self.assertEqual(old.naming_series, self.default_series)
        finally:
            frappe.set_user("Administrator")
            self._configure(self.default_rules())

        frappe.set_user(self.web_user)
        new = self._invoice()
        self.assertEqual(new.naming_series, WEB)
        self.assertEqual(
            frappe.db.get_value("Sales Invoice", old.name, ["name", "naming_series"]),
            (old.name, self.default_series),
        )

        frappe.set_user("Administrator")
        frappe.get_doc("Sales Invoice", old.name).cancel()
        amended = frappe.copy_doc(frappe.get_doc("Sales Invoice", old.name))
        amended.amended_from = old.name
        amended.docstatus = 0
        frappe.set_user(self.web_user)
        amended.insert()
        self.assertEqual(amended.name, f"{old.name}-1")
        self.assertEqual(amended.naming_series, self.default_series)

    # -- Test 10: multiple companies -----------------------------------------

    def test_rule_is_picked_by_the_invoice_company(self) -> None:
        frappe.set_user(self.multi_user)
        in_a = self._invoice(company=self.company)
        in_b = self._invoice(company=self.company_b)
        self.assertEqual(in_a.naming_series, VAN)
        self.assertEqual(in_b.naming_series, VAN_B)

    def test_user_with_rule_in_one_company_only_is_unmapped_in_another(self) -> None:
        frappe.set_user(self.web_user)
        self.assertEqual(self._invoice(company=self.company_b).naming_series, self.default_series)

    # -- configuration --------------------------------------------------------

    def _settings_with(self, *rules: dict):
        settings = frappe.get_single(SETTINGS_DOCTYPE)
        settings.rules = []
        for rule in rules:
            settings.append("rules", {"user": self.web_user, "company": self.company, "enabled": 1, **rule})
        return settings

    def test_config_rejects_a_duplicate_user_company_rule(self) -> None:
        settings = self._settings_with(
            {"normal_series": WEB, "return_series": WEB_RET},
            {"normal_series": VAN, "return_series": VAN_RET, "enabled": 0},
        )
        with self.assertRaisesRegex(frappe.ValidationError, "already has a rule"):
            settings.validate()

    def test_config_rejects_series_that_are_not_sales_invoice_options(self) -> None:
        settings = self._settings_with({"normal_series": "NOPE-.##", "return_series": WEB_RET})
        with self.assertRaisesRegex(frappe.ValidationError, "not a Sales Invoice naming series"):
            settings.validate()

    def test_config_rejects_returns_sharing_the_invoice_counter(self) -> None:
        for normal, ret in ((WEB, WEB), (WEB, WEB_WIDER)):
            settings = self._settings_with({"normal_series": normal, "return_series": ret})
            with self.assertRaises(frappe.ValidationError):
                settings.validate()

    def test_config_rejects_counters_that_can_emit_the_same_name(self) -> None:
        try:
            self._set_si_options(self.original_options + TEST_SERIES + [WEB_OVERLAP])
            for normal in (WEB_OVERLAP, WEB):  # as a rule, or as an option another rule overlaps
                settings = self._settings_with({"normal_series": normal, "return_series": WEB_RET})
                with self.assertRaisesRegex(frappe.ValidationError, "same invoice number"):
                    settings.validate()
        finally:
            frappe.db.rollback()
            self._set_si_options(self.original_options + TEST_SERIES)
            frappe.db.commit()

    def test_config_allows_users_to_share_a_series(self) -> None:
        settings = self._settings_with({"normal_series": VAN, "return_series": VAN_RET})
        settings.append(
            "rules",
            {"user": self.van_user, "company": self.company, "normal_series": VAN, "return_series": VAN_RET},
        )
        settings.validate()

    def test_only_naming_managers_can_change_the_mapping(self) -> None:
        self.assertTrue(frappe.has_permission(SETTINGS_DOCTYPE, "write", user=self.manager))
        for user in (self.sales_only, self.van_user, self.web_user):
            self.assertFalse(frappe.has_permission(SETTINGS_DOCTYPE, "read", user=user), user)

        frappe.set_user(self.web_user)
        settings = frappe.get_doc(SETTINGS_DOCTYPE)
        settings.rules[0].normal_series = VAN
        with self.assertRaises(frappe.PermissionError):
            settings.save()

        frappe.set_user(self.manager)
        settings = frappe.get_doc(SETTINGS_DOCTYPE)
        settings.save()  # a manager-only user can save the page as themselves

    def test_boot_payload_lists_only_the_session_users_enabled_rules(self) -> None:
        frappe.set_user(self.multi_user)
        self.assertEqual(
            get_session_user_series(),
            {
                self.company: {"normal_series": VAN, "return_series": VAN_RET},
                self.company_b: {"normal_series": VAN_B, "return_series": VAN_B_RET},
            },
        )
        frappe.set_user(self.unmapped_user)
        self.assertEqual(get_session_user_series(), {})

    def test_rule_pointing_at_a_removed_series_refuses_instead_of_renumbering(self) -> None:
        try:
            self._set_si_options([o for o in get_naming_series_options("Sales Invoice") if o != WEB])
            frappe.db.commit()
            frappe.set_user(self.web_user)
            with self.assertRaisesRegex(frappe.ValidationError, "no longer a Sales Invoice"):
                self._invoice()
        finally:
            frappe.set_user("Administrator")
            frappe.db.rollback()
            self._set_si_options(self.original_options + TEST_SERIES)
            frappe.db.commit()
