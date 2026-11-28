"""Only the stop's own delivery boy, or a manager, may change it through the delivery API.

Couriers hold only their real Delivery role. The Desk User and manager here also hold VanSale User, the role that keeps
DocType write once ensure_vansale_perms has run (it leaves Desk User's write out): without it they would stop at the
DocType check and the refusal below would pass without ever reaching the ownership check."""

from __future__ import annotations

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import flt, random_string

from zatgo_core.api.v1.delivery import stops
from zatgo_core.constants.roles import ROLES


class TestDeliveryStopAccess(IntegrationTestCase):
    def setUp(self) -> None:
        self.created: list[tuple[str, str]] = []
        self.own_user, self.own_boy = self._boy("own")
        self.other_user, self.other_boy = self._boy("other")
        self.desk_user = self._user("desk", "Desk User", ROLES["VANSALE_USER"])
        self.manager = self._user("mgr", ROLES["COMPANY_ADMIN"], "Desk User", ROLES["VANSALE_USER"])
        stop = frappe.get_doc(
            {
                "doctype": "ZatGo Delivery Stop",
                "title": f"Stop {random_string(6)}",
                "delivery_boy": self.own_boy,
                "status": "Out For Delivery",
                "cod_amount": 100,
            }
        ).insert(ignore_permissions=True)
        self.stop = stop.name
        self.created.append(("ZatGo Delivery Stop", stop.name))

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        for doctype, name in reversed(self.created):
            frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)

    def _user(self, tag: str, *roles: str) -> str:
        email = f"zgd-{tag}-{random_string(6).lower()}@example.test"
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": tag,
                "send_welcome_email": 0,
                "roles": [{"role": role} for role in roles],
            }
        ).insert(ignore_permissions=True)
        self.created.append(("User", email))
        return email

    def _boy(self, tag: str) -> tuple[str, str]:
        user = self._user(tag, ROLES["DELIVERY"])
        code = f"ZGD-{random_string(6).upper()}"
        boy = frappe.get_doc({"doctype": "Delivery Boy", "full_name": tag, "code": code, "user": user}).insert(
            ignore_permissions=True
        )
        self.created.append(("Delivery Boy", boy.name))
        return user, boy.name

    def _stop_value(self, field: str):
        return frappe.db.get_value("ZatGo Delivery Stop", self.stop, field)

    def test_test_users_pass_the_doctype_check(self) -> None:
        """Guards the tests below: every test user holds DocType write; refusals come from the ownership rules."""
        for user in (self.own_user, self.other_user, self.desk_user, self.manager):
            frappe.set_user(user)
            self.assertTrue(frappe.has_permission("ZatGo Delivery Stop", "write"), user)

    def test_a_courier_sees_and_writes_only_their_own_stops_on_every_route(self) -> None:
        """Not just the API: the document permission and list query (Desk, REST, reports, exports) too."""
        frappe.set_user(self.own_user)
        self.assertTrue(frappe.has_permission("ZatGo Delivery Stop", "write", doc=self.stop))
        self.assertIn(self.stop, frappe.get_list("ZatGo Delivery Stop", pluck="name"))
        frappe.set_user(self.other_user)
        self.assertFalse(frappe.has_permission("ZatGo Delivery Stop", "write", doc=self.stop))
        self.assertFalse(frappe.has_permission("ZatGo Delivery Stop", "read", doc=self.stop))
        self.assertNotIn(self.stop, frappe.get_list("ZatGo Delivery Stop", pluck="name"))
        frappe.set_user(self.desk_user)  # a dispatcher (not a courier): role permissions decide
        self.assertIn(self.stop, frappe.get_list("ZatGo Delivery Stop", pluck="name"))

    def test_another_courier_cannot_complete_the_stop(self) -> None:
        frappe.set_user(self.other_user)
        with self.assertRaises(frappe.PermissionError):
            stops.complete_delivery(self.stop, paid_amount=100)
        frappe.set_user("Administrator")
        self.assertEqual(self._stop_value("status"), "Out For Delivery")
        self.assertEqual(flt(self._stop_value("paid_amount")), 0)

    def test_desk_user_cannot_complete_the_stop(self) -> None:
        frappe.set_user(self.desk_user)
        with self.assertRaises(frappe.PermissionError):
            stops.complete_delivery(self.stop)

    def test_own_courier_completes_the_stop(self) -> None:
        frappe.set_user(self.own_user)
        done = stops.complete_delivery(self.stop, paid_amount=100)
        self.assertTrue(done["success"])
        frappe.set_user("Administrator")
        self.assertEqual(self._stop_value("status"), "Delivered")
        self.assertEqual(flt(self._stop_value("balance")), 0)

    def test_manager_can_complete_any_stop(self) -> None:
        frappe.set_user(self.manager)
        self.assertTrue(stops.complete_delivery(self.stop)["success"])

    def test_courier_cannot_take_a_stop_by_reassigning_it(self) -> None:
        frappe.set_user(self.other_user)
        with self.assertRaises(frappe.PermissionError):
            stops.assign(self.stop, self.other_boy)
        frappe.set_user("Administrator")
        self.assertEqual(self._stop_value("delivery_boy"), self.own_boy)

    def test_desk_user_can_still_dispatch(self) -> None:
        frappe.set_user(self.desk_user)
        self.assertTrue(stops.assign(self.stop, self.other_boy)["success"])
