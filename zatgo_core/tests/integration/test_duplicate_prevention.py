"""Duplicate Prevention: matching, enforcement, override, Link search, privacy, import, concurrency.

Runs against real ERPNext documents (no mocks). Each test makes its own uniquely named records."""

from __future__ import annotations

import threading

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import random_string

from zatgo_core.api.v1.duplicate import lookup
from zatgo_core.services.duplicate import config, enforcement, matcher
from zatgo_core.services.duplicate.defaults import seed_defaults
from zatgo_core.services.duplicate.enforcement import DuplicateRecordError
from zatgo_core.services.duplicate.link_search import search_link


def _tag() -> str:
    return random_string(8).upper()


def _vat() -> str:
    return "3" + "".join(str(ord(c) % 10) for c in random_string(13)) + "3"


class DuplicateTestCase(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        frappe.set_user("Administrator")
        seed_defaults()
        frappe.db.set_single_value("ZG System Settings", "enable_duplicate_prevention", 1)
        frappe.clear_document_cache("ZG System Settings", "ZG System Settings")
        if frappe.db.exists("ZG Duplicate Prevention Settings"):
            frappe.db.set_single_value("ZG Duplicate Prevention Settings", "enabled", 1)
        config.clear_cache()
        cls.group = frappe.db.get_value("Customer Group", {"is_group": 0}) or "All Customer Groups"
        cls.territory = frappe.db.get_value("Territory", {"is_group": 0}) or "All Territories"
        cls.supplier_group = frappe.db.get_value("Supplier Group", {"is_group": 0}) or "All Supplier Groups"
        cls.item_group = frappe.db.get_value("Item Group", {"is_group": 0}) or "All Item Groups"
        cls.uom = frappe.db.get_value("UOM", "Nos") or frappe.db.get_value("UOM", {}) or "Nos"

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        enforcement.release_locks()
        super().tearDown()

    def customer(self, name=None, vat=None, **extra):
        doc = frappe.get_doc({"doctype": "Customer", "customer_name": name or f"Dup Cust {_tag()}", "customer_group": self.group,
                              "territory": self.territory, "customer_type": "Company", "tax_id": vat, **extra})
        return doc

    def supplier(self, name=None, vat=None):
        return frappe.get_doc({"doctype": "Supplier", "supplier_name": name or f"Dup Supp {_tag()}", "supplier_group": self.supplier_group,
                               "tax_id": vat})

    def item(self, name=None, code=None, barcode=None):
        doc = {"doctype": "Item", "item_code": code or f"DUP-{_tag()}", "item_name": name or f"Dup Item {_tag()}",
               "item_group": self.item_group, "stock_uom": self.uom, "is_stock_item": 0}
        if barcode:
            doc["barcodes"] = [{"barcode": barcode}]
        return frappe.get_doc(doc)

    def levels(self, doctype, values, exclude=None):
        return {m["name"]: m["level"] for m in matcher.find_matches(doctype, values, exclude)}


class TestMatching(DuplicateTestCase):
    def test_same_customer_vat_is_strong_and_blocked(self):  # 3
        vat = _vat()
        first = self.customer(vat=vat).insert()
        self.assertEqual(self.levels("Customer", {"customer_name": f"Other {_tag()}", "tax_id": f" {vat[:3]}-{vat[3:]} "}).get(first.name), "strong")
        with self.assertRaises(DuplicateRecordError):
            self.customer(vat=vat).insert()

    def test_same_customer_name_different_mobile_is_possible_only(self):  # 4
        name = f"ABC Trading {_tag()}"
        first = self.customer(name=name).insert()
        first.db_set("mobile_no", "+966500000001")
        doc = self.customer(name=name.lower(), mobile_no="+966500000002")
        self.assertEqual(self.levels("Customer", doc.as_dict()).get(first.name), "possible")
        doc.insert()  # warn mode: allowed

    def test_same_supplier_vat_is_blocked(self):  # 5
        vat = _vat()
        self.supplier(vat=vat).insert()
        with self.assertRaises(DuplicateRecordError):
            self.supplier(vat=vat).insert()

    def test_same_item_name_different_code_is_refused(self):  # 2
        name = f"Steel Pipe {_tag()}"
        first = self.item(name=name).insert()
        second = self.item(name=name.lower())
        self.assertEqual(self.levels("Item", second.as_dict()).get(first.name), "possible")
        with self.assertRaises(DuplicateRecordError):  # Item rule: possible matches block (still a possible match, not strong)
            second.insert()
        second.flags.zg_duplicate_override = True  # an authorized user can still save it, with a reason
        second.flags.zg_duplicate_override_reason = "Different supplier grade"
        second.insert()

    def test_same_barcode_twice_is_refused(self):  # 1
        code = f"BC{_tag()}"
        first = self.item(barcode=code).insert()
        self.assertEqual(self.levels("Item", {"barcodes": [{"barcode": code}]}).get(first.name), "strong")
        with self.assertRaises(frappe.ValidationError):  # ERPNext's own check or ours -- either way refused
            self.item(barcode=code).insert()

    def test_shared_contact_email_is_possible_not_blocking(self):  # 6
        email = f"shared{_tag()}@example.com"
        for _ in range(2):
            frappe.get_doc({"doctype": "Contact", "first_name": f"P{_tag()}", "email_ids": [{"email_id": email, "is_primary": 1}]}).insert()
        probe = {"email_ids": [{"email_id": email}], "first_name": f"New{_tag()}"}
        self.assertEqual({m["level"] for m in matcher.find_matches("Contact", probe)}, {"possible"})
        frappe.get_doc({"doctype": "Contact", "first_name": f"N{_tag()}", "email_ids": [{"email_id": email, "is_primary": 1}]}).insert()

    def test_phone_formats_and_email_case_match(self):  # 7, 8
        tag = _tag().lower()
        lead = frappe.get_doc({"doctype": "Lead", "first_name": f"L{tag}", "email_id": f"Case.{tag}@Example.COM", "mobile_no": "+966 50 111 2222"}).insert()
        self.assertIn(lead.name, self.levels("Lead", {"email_id": f"case.{tag}@example.com"}))
        for form in ("0501112222", "00966501112222", "966501112222", "+966-50-111-2222"):
            self.assertIn(lead.name, self.levels("Lead", {"mobile_no": form}), form)
        both = self.levels("Lead", {"mobile_no": "0501112222", "email_id": f"CASE.{tag}@example.com"})
        self.assertEqual(both.get(lead.name), "strong")  # several identifiers

    def test_existing_record_excluded_when_editing(self):  # 9
        vat = _vat()
        doc = self.customer(vat=vat).insert()
        self.assertNotIn(doc.name, self.levels("Customer", doc.as_dict(), exclude=doc.name))
        doc.reload()
        doc.territory = self.territory
        doc.save()  # unrelated edit and own VAT: never blocked by itself

    def test_arabic_and_english_names(self):
        first = self.customer(name=f"مؤسسة النور {_tag()}").insert()
        probe = first.customer_name.replace("مؤسسة", "مؤسسه")
        self.assertIn(first.name, self.levels("Customer", {"customer_name": probe}))

    def test_transaction_rule_blocks_supplier_bill_no_pair(self):
        rule = config.rule_for("Purchase Invoice")
        self.assertEqual(rule["type"], "Transaction")
        self.assertEqual(rule["strong_action"], "Block")


class TestEnforcement(DuplicateTestCase):
    def test_rest_style_insert_is_blocked(self):  # 10
        vat = _vat()
        self.customer(vat=vat).insert()
        with self.assertRaises(DuplicateRecordError):
            frappe.call("frappe.client.insert", doc={"doctype": "Customer", "customer_name": f"Rest {_tag()}", "customer_group": self.group,
                                                     "territory": self.territory, "tax_id": vat})

    def test_data_import_cannot_bypass(self):  # 11
        from frappe.core.doctype.data_import.data_import import start_import
        vat = _vat()
        self.customer(vat=vat).insert()
        csv = f"Customer Name,Customer Group,Territory,Tax ID\nImported {_tag()},{self.group},{self.territory},{vat}\n"
        file = frappe.get_doc({"doctype": "File", "file_name": f"dup_{_tag()}.csv", "content": csv, "is_private": 1}).insert()
        imp = frappe.get_doc({"doctype": "Data Import", "reference_doctype": "Customer", "import_type": "Insert New Records", "import_file": file.file_url}).insert()
        frappe.db.commit()  # the importer commits / rolls back its own transaction
        try:
            start_import(imp.name)
            self.assertEqual(frappe.db.count("Customer", {"tax_id": vat}), 1)  # only the pre-existing one
            self.assertTrue(frappe.db.exists("Data Import Log", {"data_import": imp.name, "success": 0}))
        finally:
            for name in frappe.get_all("Customer", filters={"tax_id": vat}, pluck="name"):
                frappe.delete_doc("Customer", name, force=True)
            frappe.db.delete("Data Import Log", {"data_import": imp.name})
            frappe.delete_doc("Data Import", imp.name, force=True)
            frappe.delete_doc("File", file.name, force=True)
            frappe.db.commit()

    def test_authorized_override_is_logged(self):  # 13
        vat = _vat()
        existing = self.customer(vat=vat).insert()
        doc = self.customer(vat=vat)
        doc.flags.zg_duplicate_override = True
        doc.flags.zg_duplicate_override_reason = "Same legal entity, second branch"
        doc.insert()
        log = frappe.get_all("ZG Duplicate Override Log", filters={"ref_name": doc.name}, fields=["matched_records", "reason", "user"])
        self.assertEqual(log[0]["matched_records"], existing.name)
        self.assertEqual(log[0]["user"], "Administrator")

    def test_override_without_reason_is_refused(self):
        vat = _vat()
        self.customer(vat=vat).insert()
        doc = self.customer(vat=vat)
        doc.flags.zg_duplicate_override = True
        with self.assertRaises(DuplicateRecordError):
            doc.insert()

    def test_registered_override_token_allows_one_save(self):
        vat = _vat()
        existing = self.customer(vat=vat).insert()
        lookup.override("Customer", [existing.name], "Branch of the same company")
        self.customer(vat=vat).insert()
        with self.assertRaises(DuplicateRecordError):  # single use
            self.customer(vat=vat).insert()

    def test_unauthorized_user_cannot_override(self):  # 14
        vat = _vat()
        self.customer(vat=vat).insert()
        user = _plain_user()
        frappe.set_user(user)
        doc = self.customer(vat=vat)
        doc.flags.zg_duplicate_override = True
        doc.flags.zg_duplicate_override_reason = "please"
        with self.assertRaises(DuplicateRecordError):
            enforcement.validate_document(doc)
        with self.assertRaises(frappe.PermissionError):
            lookup.override("Customer", ["x"], "reason")

    def test_switch_off_disables_everything(self):
        vat = _vat()
        self.customer(vat=vat).insert()
        frappe.db.set_single_value("ZG Duplicate Prevention Settings", "enabled", 0)
        config.clear_cache()
        try:
            self.customer(vat=vat).insert()
        finally:
            frappe.db.set_single_value("ZG Duplicate Prevention Settings", "enabled", 1)
            config.clear_cache()


class TestLookupAndPrivacy(DuplicateTestCase):
    def test_link_search_by_name_id_and_vat(self):  # 15
        vat = _vat()
        doc = self.customer(name=f"ABC Trading {_tag()}", vat=vat).insert()
        by_name = search_link(doctype="Customer", txt=doc.customer_name)
        by_id = search_link(doctype="Customer", txt=doc.name)
        by_vat = search_link(doctype="Customer", txt=vat)
        for found in (by_name, by_id, by_vat):
            self.assertIn(doc.name, [r["value"] for r in found])
        row = next(r for r in by_name if r["value"] == doc.name)
        self.assertIn(f"VAT: {vat}", row["description"])

    def test_link_search_through_the_request_handler(self):
        # What frappe.handler.execute_cmd does for an overridden method: resolve it from the hooks and call it with
        # the whole request (cmd and anything else the browser sent). The core function takes named arguments only.
        doc = self.customer(name=f"Handler Trading {_tag()}").insert()
        override = frappe.get_hooks("override_whitelisted_methods")["frappe.desk.search.search_link"][-1]
        result = frappe.call(frappe.get_attr(override), cmd="frappe.desk.search.search_link", doctype="Customer",
                             txt=doc.customer_name, page_length=10, extra_unknown_arg="x")
        self.assertIn(doc.name, [r["value"] for r in result])

    def test_check_api_returns_details_for_permitted_user(self):  # 16
        vat = _vat()
        doc = self.customer(vat=vat).insert()
        out = lookup.check("Customer", {"customer_name": "x", "tax_id": vat})["data"]
        self.assertEqual(out["level"], "strong")
        match = out["matches"][0]
        self.assertEqual(match["name"], doc.name)
        self.assertFalse(match["restricted"])
        self.assertIn("tax_id", [d["fieldname"] for d in match["details"]])

    def test_user_without_permission_cannot_look_up_or_see_records(self):  # 16
        vat = _vat()
        doc = self.customer(vat=vat).insert()
        frappe.set_user(_plain_user())
        with self.assertRaises(frappe.PermissionError):
            lookup.check("Customer", {"tax_id": vat})
        rule = config.rule_for("Customer")
        shown = matcher.present("Customer", matcher.find_matches("Customer", {"tax_id": vat}), rule)
        self.assertEqual([m["restricted"] for m in shown], [True])
        self.assertNotIn(doc.name, str(shown))
        self.assertNotIn(vat, str(shown))
        with self.assertRaises(DuplicateRecordError) as ctx:
            enforcement.validate_document(self.customer(vat=vat))
        self.assertNotIn(doc.name, str(ctx.exception))

    def test_guest_is_refused(self):
        frappe.set_user("Guest")
        with self.assertRaises(frappe.AuthenticationError):
            lookup.form_config("Customer")


class TestConcurrency(DuplicateTestCase):
    def test_identifier_lock_excludes_a_second_connection(self):  # 12 (lock level)
        key = enforcement.lock_name("Customer", "Tax ID", _vat())
        self.assertEqual(frappe.db.sql("select get_lock(%s, 0)", key)[0][0], 1)
        site = frappe.local.site
        result = {}

        def other():
            frappe.init(site)
            frappe.connect()
            result["got"] = frappe.db.sql("select get_lock(%s, 0)", key)[0][0]
            frappe.destroy()

        t = threading.Thread(target=other)
        t.start()
        t.join()
        frappe.db.sql("select release_lock(%s)", key)
        self.assertEqual(result["got"], 0)

    def test_two_simultaneous_creates_only_one_wins(self):  # 12 (end to end)
        vat = _vat()
        site = frappe.local.site
        frappe.db.commit()  # the worker threads are separate connections: they must see our fixtures
        outcomes: list[str] = []
        created: list[str] = []
        barrier = threading.Barrier(2)

        def worker(i: int):
            frappe.init(site)
            frappe.connect()
            frappe.set_user("Administrator")
            try:
                doc = frappe.get_doc({"doctype": "Customer", "customer_name": f"Race {vat} {i}", "customer_group": self.group,
                                      "territory": self.territory, "tax_id": vat})
                barrier.wait(timeout=10)
                doc.insert()
                frappe.db.commit()
                created.append(doc.name)
                outcomes.append("created")
            except DuplicateRecordError:
                frappe.db.rollback()
                outcomes.append("blocked")
            except Exception as e:  # pragma: no cover - reported by the assertion below
                frappe.db.rollback()
                outcomes.append(f"error:{type(e).__name__}:{e}")
            finally:
                frappe.destroy()

        threads = [threading.Thread(target=worker, args=(i,)) for i in (1, 2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(60)
        try:
            self.assertEqual(sorted(outcomes), ["blocked", "created"], outcomes)
            self.assertEqual(frappe.db.count("Customer", {"tax_id": vat}), 1)
        finally:
            for name in created:
                frappe.delete_doc("Customer", name, force=True)
            frappe.db.commit()


def _plain_user() -> str:
    email = f"dup_plain_{_tag().lower()}@example.com"
    user = frappe.get_doc({"doctype": "User", "email": email, "first_name": "Plain", "send_welcome_email": 0, "enabled": 1})
    user.insert(ignore_permissions=True)
    user.add_roles("Desk User")
    return email
