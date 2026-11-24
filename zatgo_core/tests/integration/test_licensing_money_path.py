"""Money path under real, imported licences (Phase 9, brief Part 18 items 21-28): upgrade and downgrade by
replacement licence, stock and general ledger integrity, payments, purchase returns. Throwaway key outside sites/.

Every posting goes through ERPNext's own controllers; the licence only decides whether a user may start it."""

from __future__ import annotations

import os
import tempfile

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import nowdate, random_string

from zatgo_core.licensing import crypto, editions, entitlement, issuer, issuing, licence_policy, licences
from zatgo_core.licensing import site_identity
from zatgo_core.tests.integration._fixtures import get_or_create_cash_mode_of_payment, get_or_create_test_company


class TestLicensedMoneyPath(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.tmp = tempfile.mkdtemp(prefix="zg-licence-money-")
        cls.key_path = os.path.join(cls.tmp, "issuer.pem")
        cls.key = crypto.generate_private_key()
        crypto.write_private_key(cls.key, cls.key_path)
        cls.kid = crypto.key_id(cls.key.public_key())
        cls.site = site_identity.site_id(create=True)
        cls.company = get_or_create_test_company()
        abbr = frappe.db.get_value("Company", cls.company, "abbr")
        cls.warehouse = f"LicenceMoney - {abbr}"
        if not frappe.db.exists("Warehouse", cls.warehouse):
            frappe.get_doc({"doctype": "Warehouse", "warehouse_name": "LicenceMoney", "company": cls.company}).insert(
                ignore_permissions=True)
        group = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
        cls.stock_item = f"LIC-MONEY-STK-{random_string(5).upper()}"
        cls.service_item = f"LIC-MONEY-SRV-{random_string(5).upper()}"
        for code, is_stock in ((cls.stock_item, 1), (cls.service_item, 0)):
            frappe.get_doc({"doctype": "Item", "item_code": code, "item_name": code, "item_group": group,
                            "stock_uom": "Nos", "is_stock_item": is_stock}).insert(ignore_permissions=True)
        cls.customer = "Licence Money Customer"
        if not frappe.db.exists("Customer", cls.customer):
            frappe.get_doc({"doctype": "Customer", "customer_name": cls.customer, "customer_type": "Company",
                            "customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
                            "territory": frappe.db.get_value("Territory", {"is_group": 0}, "name")}).insert(
                ignore_permissions=True)
        cls.supplier = "Licence Money Supplier"
        if not frappe.db.exists("Supplier", cls.supplier):
            frappe.get_doc({"doctype": "Supplier", "supplier_name": cls.supplier,
                            "supplier_group": frappe.db.get_value("Supplier Group", {"is_group": 0}, "name")}).insert(
                ignore_permissions=True)
        cls.cash = frappe.db.get_value("Account", {"company": cls.company, "account_type": "Cash", "is_group": 0},
                                       "name")
        get_or_create_cash_mode_of_payment(cls.company, cls.cash)
        cls.user = f"zg-lic-money-{random_string(6).lower()}@example.com"
        frappe.get_doc({"doctype": "User", "email": cls.user, "first_name": "Licence money", "send_welcome_email": 0,
                        "roles": [{"role": r} for r in ("System Manager", "Accounts Manager", "Stock Manager",
                                                        "Sales Manager", "Purchase Manager")]}).insert(
            ignore_permissions=True)

    @classmethod
    def tearDownClass(cls) -> None:
        crypto.trust_for_tests(None)
        try:
            os.remove(cls.key_path)
            os.rmdir(cls.tmp)
        except OSError:
            pass
        super().tearDownClass()

    def setUp(self) -> None:
        frappe.set_user("Administrator")
        crypto.trust_for_tests({self.kid: crypto.b64e(crypto.raw_public(self.key.public_key()))})
        frappe.local.conf[issuer.CONF_KEY] = 1
        frappe.local.conf[issuing.KEY_CONF] = self.key_path
        editions.seed_presets()
        frappe.db.set_value(licences.DOCTYPE, {"is_current": 1}, "is_current", 0, update_modified=False)
        frappe.db.delete("DefaultValue", {"parent": "__default", "defkey": licence_policy.HWM_KEY})
        frappe.local.conf[entitlement.CONF_KEY] = 1
        licences.clear_cache()

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        for key in (issuer.CONF_KEY, issuing.KEY_CONF, entitlement.CONF_KEY):
            frappe.local.conf.pop(key, None)
        frappe.db.delete("DefaultValue", {"parent": "__default", "defkey": licence_policy.HWM_KEY})
        licences.clear_cache()

    # -- helpers ------------------------------------------------------------------------------------------------

    def _license(self, edition_id: str, replaces: str | None = None) -> dict:
        frappe.set_user("Administrator")
        issued = issuing.issue(edition_id, "Money Test Co", [self.site], replaces=replaces)
        licences.import_licence(issued["file"])
        licences.clear_cache()
        frappe.set_user(self.user)
        return issued

    def _receipt(self, qty: int = 5):
        return frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "company": self.company,
                               "items": [{"item_code": self.stock_item, "qty": qty, "t_warehouse": self.warehouse,
                                          "basic_rate": 10}]})

    def _invoice(self):
        return frappe.get_doc({"doctype": "Sales Invoice", "customer": self.customer, "company": self.company,
                               "currency": "SAR", "conversion_rate": 1, "due_date": nowdate(),
                               "items": [{"item_code": self.service_item, "qty": 2, "rate": 50}]})

    @staticmethod
    def _balanced(voucher: str) -> float:
        rows = frappe.get_all("GL Entry", filters={"voucher_no": voucher, "is_cancelled": 0},
                              fields=["debit", "credit"])
        debit, credit = sum(r.debit for r in rows), sum(r.credit for r in rows)
        assert rows and abs(debit - credit) < 0.005, (voucher, debit, credit)
        return debit

    # -- upgrade, downgrade -------------------------------------------------------------------------------------

    def test_upgrade_then_downgrade_keeps_history(self) -> None:
        sales = self._license("sales")
        with self.assertRaises(frappe.PermissionError):
            self._receipt().insert(ignore_permissions=True)

        self._license("sales_inventory", replaces=sales["licence_id"])  # upgrade: version 2 of the same licence
        se = self._receipt().insert(ignore_permissions=True)
        se.submit()
        sle = frappe.get_all("Stock Ledger Entry", filters={"voucher_no": se.name, "is_cancelled": 0},
                             fields=["actual_qty", "stock_value_difference"])
        self.assertEqual(sum(r.actual_qty for r in sle), 5)
        self.assertAlmostEqual(sum(r.stock_value_difference for r in sle), 50)

        self._license("sales", replaces=sales["licence_id"])  # downgrade: version 3
        self.assertEqual(licences.current_doc().licence_version, 3)
        with self.assertRaises(frappe.PermissionError):
            self._receipt().insert(ignore_permissions=True)
        doc = frappe.get_doc("Stock Entry", se.name)
        self.assertTrue(frappe.has_permission("Stock Entry", "read", doc=doc, user=self.user))
        doc.cancel()  # history stays reversible
        self.assertEqual(frappe.db.count("Stock Ledger Entry", {"voucher_no": se.name, "is_cancelled": 0}), 0)
        amended = frappe.copy_doc(doc)
        amended.amended_from = doc.name
        amended.docstatus = 0
        with self.assertRaises(frappe.PermissionError):
            amended.insert(ignore_permissions=True)

    # -- payments -------------------------------------------------------------------------------------------

    def test_invoice_and_payment_post_balanced_ledgers(self) -> None:
        self._license("sales")  # the Sales edition includes customer payments
        si = self._invoice().insert(ignore_permissions=True)
        si.submit()
        self.assertEqual(self._balanced(si.name), 100)
        from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

        pe = get_payment_entry("Sales Invoice", si.name)
        pe.mode_of_payment = "Cash"
        pe.paid_to = self.cash
        pe.reference_no = random_string(6)
        pe.reference_date = nowdate()
        pe.insert(ignore_permissions=True)
        pe.submit()
        self.assertEqual(self._balanced(pe.name), 100)
        self.assertEqual(frappe.db.get_value("Sales Invoice", si.name, "outstanding_amount"), 0)
        self.assertTrue(frappe.db.exists("Payment Ledger Entry", {"voucher_no": pe.name, "delinked": 0}))

    # -- purchases ------------------------------------------------------------------------------------------

    def test_purchase_invoice_and_debit_note(self) -> None:
        self._license("sales")
        purchase = {"doctype": "Purchase Invoice", "supplier": self.supplier, "company": self.company,
                    "currency": "SAR", "conversion_rate": 1, "bill_no": random_string(6), "bill_date": nowdate(),
                    "items": [{"item_code": self.service_item, "qty": 1, "rate": 30}]}
        with self.assertRaises(frappe.PermissionError):
            frappe.get_doc(dict(purchase)).insert(ignore_permissions=True)

        self._license("accounting")  # includes purchase invoices and returns
        pi = frappe.get_doc(dict(purchase)).insert(ignore_permissions=True)
        pi.submit()
        self.assertEqual(self._balanced(pi.name), 30)
        from erpnext.accounts.doctype.purchase_invoice.purchase_invoice import make_debit_note

        note = make_debit_note(pi.name)
        note.insert(ignore_permissions=True)
        note.submit()
        self.assertEqual((note.is_return, note.return_against), (1, pi.name))
        self.assertEqual(self._balanced(note.name), 30)
        # ERPNext 16 books the return against itself by default (update_outstanding_for_self): the payment ledger
        # still nets the supplier's balance to zero.
        net = sum(frappe.get_all("Payment Ledger Entry", filters={"party": self.supplier, "delinked": 0,
                                                                   "voucher_no": ["in", [pi.name, note.name]]},
                                 pluck="amount"))
        self.assertAlmostEqual(net, 0)
