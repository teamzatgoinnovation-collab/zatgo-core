"""Multi-industry layer: per-site activation, dependencies, role AND industry
access, API gating, Desk entries, pilots (Gym, Jewellery, Restaurant)."""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import add_days, getdate, random_string, today

from zatgo_core.industries import gate, registry
from zatgo_core.industries.sync import ensure_rows, sync_industries
from zatgo_core.tests.integration._fixtures import get_or_create_test_company

SETTINGS = "ZG System Settings"


def _set_industries(*keys: str) -> None:
    """Switch exactly these industries on, via a real settings save."""
    frappe.set_user("Administrator")
    doc = frappe.get_doc(SETTINGS)
    ensure_rows(doc)
    for row in doc.enabled_industries:
        row.enabled = 1 if row.industry in keys else 0
    doc.save(ignore_permissions=True)
    frappe.clear_document_cache(SETTINGS, SETTINGS)


class IndustryTestBase(IntegrationTestCase):
    def setUp(self) -> None:
        frappe.set_user("Administrator")
        doc = frappe.get_doc(SETTINGS)
        self._before = {r.industry for r in doc.enabled_industries if r.enabled}
        _set_industries()

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        _set_industries(*self._before)

    def _user(self, *roles: str) -> str:
        email = f"industry.test.{random_string(6).lower()}@zatgo.test"
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "Industry",
                "send_welcome_email": 0,
                "roles": [{"role": r} for r in roles],
            }
        ).insert(ignore_permissions=True)
        return email

    def _gate_404(self, method: str) -> bool:
        orig = getattr(frappe.local, "request", None)
        try:
            frappe.local.request = frappe._dict(path=f"/api/method/{method}")
            gate.gate_industry_api()
            return False
        except frappe.DoesNotExistError:
            return True
        finally:
            frappe.local.request = orig


class TestIndustryActivation(IndustryTestBase):
    def test_default_is_everything_off(self) -> None:
        self.assertEqual(gate.enabled_keys(), set())
        doc = frappe.get_doc(SETTINGS)
        self.assertEqual(len(doc.enabled_industries), 17)

    def test_enable_disable_and_persist(self) -> None:
        _set_industries("gym", "jewellery")
        frappe.clear_cache()
        self.assertEqual(gate.enabled_keys(), {"gym", "jewellery"})
        self.assertTrue(gate.is_enabled("gym"))
        self.assertFalse(gate.is_enabled("restaurant"))
        _set_industries("restaurant")
        self.assertEqual(gate.enabled_keys(), {"restaurant"})
        _set_industries()
        self.assertEqual(gate.enabled_keys(), set())

    def test_unavailable_industry_cannot_be_enabled(self) -> None:
        doc = frappe.get_doc(SETTINGS)
        ensure_rows(doc)
        for row in doc.enabled_industries:
            row.enabled = 1 if row.industry == "salon" else 0
        # ensure_rows on validate clears the flag of a not-yet-available industry
        doc.save(ignore_permissions=True)
        self.assertEqual(gate.enabled_keys(), set())
        with self.assertRaises(frappe.ValidationError):
            gate.validate_selection({"salon"})
        with self.assertRaises(frappe.ValidationError):
            gate.validate_selection({"not-an-industry"})

    def test_industry_dependency_is_enforced(self) -> None:
        dep = registry.Industry(
            key="gym", label="Gym", description="", requires=(), requires_industries=("jewellery",), implemented=True
        )
        with patch.dict(registry.INDUSTRIES, {"gym": dep}):
            with self.assertRaises(frappe.ValidationError):
                gate.validate_selection({"gym"})
            gate.validate_selection({"gym", "jewellery"})

    def test_missing_core_capability_is_rejected(self) -> None:
        need = registry.Industry(
            key="gym", label="Gym", description="", requires=("manufacturing",), implemented=True
        )
        with patch.dict(registry.INDUSTRIES, {"gym": need}), patch.dict(
            registry.CAPABILITIES, {"manufacturing": "No Such DocType"}
        ):
            with self.assertRaises(frappe.ValidationError):
                gate.validate_selection({"gym"})

    def test_unreadable_settings_fail_closed(self) -> None:
        _set_industries("gym")
        with patch("frappe.get_cached_doc", side_effect=Exception("boom")):
            self.assertEqual(gate.enabled_keys(), set())

    def test_workspace_follows_the_switch(self) -> None:
        self.assertFalse(frappe.db.exists("Workspace", "ZatGo Gym"))
        _set_industries("gym")
        self.assertTrue(frappe.db.exists("Workspace", "ZatGo Gym"))
        self.assertTrue(frappe.db.exists("Workspace Sidebar", "ZatGo Gym"))
        self.assertTrue(frappe.db.exists("Desktop Icon", "ZatGo Gym"))
        self.assertFalse(frappe.db.exists("Workspace", "ZatGo Jewellery"))
        _set_industries()
        self.assertFalse(frappe.db.exists("Workspace", "ZatGo Gym"))
        self.assertFalse(frappe.db.exists("Desktop Icon", "ZatGo Gym"))

    def test_boot_lists_enabled_industries(self) -> None:
        from zatgo_core.events.boot import boot_session

        _set_industries("gym")
        info = frappe._dict()
        boot_session(info)
        self.assertEqual(info.zatgo_core["industries"], ["gym"])

    def test_scheduled_job_guard(self) -> None:
        self.assertFalse(gate.guard_job("gym"))
        _set_industries("gym")
        self.assertTrue(gate.guard_job("gym"))


class TestIndustryAccess(IndustryTestBase):
    """role permission AND industry enabled."""

    def test_permission_matrix_gym(self) -> None:
        from zatgo_core.api.v1.gym import membership

        _set_industries("gym")
        plan = frappe.get_doc(
            {"doctype": "ZG Gym Plan", "plan_name": f"Matrix {random_string(5)}", "duration_days": 30, "price": 10}
        ).insert()
        permitted = self._user("ZG Gym User")
        other = self._user("Sales User")
        cases = [
            (True, permitted, True),
            (True, other, False),
            (False, permitted, False),
            (False, other, False),
        ]
        for enabled, user, expect in cases:
            _set_industries(*(("gym",) if enabled else ()))
            frappe.set_user(user)
            try:
                if expect:
                    self.assertEqual(membership.plans()["success"], True)
                else:
                    with self.assertRaises(frappe.PermissionError):
                        membership.plans()
            finally:
                frappe.set_user("Administrator")
            # Documents: has_permission needs a doc for the controller hooks.
            doc_allowed = frappe.has_permission("ZG Gym Plan", "read", doc=plan, user=user)
            self.assertEqual(doc_allowed, expect, f"doc enabled={enabled} user={user}")
            frappe.set_user(user)
            try:
                rows = frappe.get_list("ZG Gym Plan", limit_page_length=5)
            except frappe.PermissionError:
                rows = []
            finally:
                frappe.set_user("Administrator")
            self.assertEqual(bool(rows), expect, f"list enabled={enabled} user={user}")

    def test_guest_is_rejected(self) -> None:
        from zatgo_core.api.v1.gym import membership

        _set_industries("gym")
        frappe.set_user("Guest")
        try:
            with self.assertRaises(frappe.AuthenticationError):
                membership.plans()
        finally:
            frappe.set_user("Administrator")

    def test_query_conditions_hide_disabled_industry_rows(self) -> None:
        self.assertEqual(gate.industry_query_conditions("x", "ZG Gym Plan"), "1=0")
        self.assertEqual(gate.industry_query_conditions("x", "Sales Invoice"), "")
        _set_industries("gym")
        self.assertEqual(gate.industry_query_conditions("x", "ZG Gym Plan"), "")

    def test_core_doctypes_are_never_gated(self) -> None:
        # (Not asserting a role's Customer read: sites with VanSale Custom
        # DocPerms drop the standard ones -- unrelated to industries.)
        for dt in ("Customer", "Sales Invoice", "Item", "Journal Entry"):
            self.assertTrue(gate.industry_doc_has_permission(frappe._dict(doctype=dt)))
            self.assertEqual(gate.industry_query_conditions("u", dt), "")

    def test_api_404_where_industry_off(self) -> None:
        for m in (
            "zatgo_core.api.v1.gym.membership.plans",
            "zatgo_core.api.v1.jewellery.pricing.price",
            "zatgo_core.api.v1.resto_pos.tables.list",
        ):
            self.assertTrue(self._gate_404(m), m)
        self.assertFalse(self._gate_404("zatgo_core.api.v1.vansalex.me.context"))
        _set_industries("gym", "jewellery", "restaurant")
        for m in (
            "zatgo_core.api.v1.gym.membership.plans",
            "zatgo_core.api.v1.jewellery.pricing.price",
            "zatgo_core.api.v1.resto_pos.tables.list",
        ):
            self.assertFalse(self._gate_404(m), m)

    def test_permission_hook_returns_never_none(self) -> None:
        for dt in ("ZG Gym Plan", "Sales Invoice"):
            self.assertIsNotNone(gate.industry_doc_has_permission(frappe._dict(doctype=dt)))
            self.assertIsNotNone(gate.industry_query_conditions("u", dt))


class TestGymIndustry(IndustryTestBase):
    def setUp(self) -> None:
        super().setUp()
        _set_industries("gym")
        self.company = get_or_create_test_company()
        name = f"Gym Test Member {random_string(5)}"
        self.customer = frappe.get_doc(
            {"doctype": "Customer", "customer_name": name, "customer_type": "Individual"}
        ).insert(ignore_permissions=True).name
        self.plan = frappe.get_doc(
            {"doctype": "ZG Gym Plan", "plan_name": f"Monthly {random_string(5)}", "duration_days": 30, "price": 150}
        ).insert()

    def _membership(self, start=None):
        return frappe.get_doc(
            {
                "doctype": "ZG Gym Membership",
                "member": self.customer,
                "plan": self.plan.name,
                "company": self.company,
                "start_date": start or today(),
            }
        ).insert()

    def test_end_date_status_and_amount(self) -> None:
        m = self._membership()
        self.assertEqual(getdate(m.end_date), add_days(getdate(), 29))
        self.assertEqual(m.status, "Active")
        self.assertEqual(m.amount, 150)
        old = self._membership(add_days(today(), -60))
        self.assertEqual(old.status, "Expired")

    def test_invalid_plan_rejected(self) -> None:
        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc({"doctype": "ZG Gym Plan", "plan_name": f"Bad {random_string(4)}", "duration_days": 0, "price": 1}).insert()

    def test_renew_once(self) -> None:
        from zatgo_core.api.v1.gym import membership

        m = self._membership()
        new = membership.renew(m.name)["data"]
        self.assertEqual(getdate(new["start_date"]), add_days(getdate(m.end_date), 1))
        with self.assertRaises(frappe.ValidationError):
            membership.renew(m.name)

    def test_attendance_requires_active_membership(self) -> None:
        from zatgo_core.api.v1.gym import membership

        m = self._membership()
        self.assertIn("name", membership.check_in(m.name)["data"])
        expired = self._membership(add_days(today(), -90))
        with self.assertRaises(frappe.ValidationError):
            membership.check_in(expired.name)

    def test_bill_without_item_is_rejected(self) -> None:
        from zatgo_core.api.v1.gym import membership

        m = self._membership()
        with self.assertRaises(frappe.ValidationError):
            membership.bill(m.name)


class TestJewelleryIndustry(IndustryTestBase):
    def test_item_fields_follow_the_switch(self) -> None:
        _set_industries("jewellery")
        cf = frappe.db.get_value("Custom Field", {"dt": "Item", "fieldname": "zg_jewellery_purity"}, "hidden")
        self.assertEqual(cf, 0)
        _set_industries()
        cf = frappe.db.get_value("Custom Field", {"dt": "Item", "fieldname": "zg_jewellery_purity"}, "hidden")
        self.assertEqual(cf, 1)

    def test_price_breakdown(self) -> None:
        from zatgo_core.api.v1.jewellery import pricing

        _set_industries("jewellery")
        code = f"JW-{random_string(5)}"
        frappe.get_doc(
            {
                "doctype": "Item",
                "item_code": code,
                "item_name": code,
                "item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name") or "All Item Groups",
                "stock_uom": "Nos",
                "is_stock_item": 0,
                "zg_jewellery_metal": "Gold",
                "zg_jewellery_purity": "22K",
                "zg_jewellery_gross_weight": 11,
                "zg_jewellery_stone_weight": 1,
                "zg_jewellery_making_charge": 10,
                "zg_jewellery_wastage": 5,
            }
        ).insert(ignore_permissions=True)
        frappe.get_doc(
            {"doctype": "ZG Metal Rate", "metal": "Gold", "purity": "22K", "rate_date": add_days(today(), -1), "rate_per_gram": 100}
        ).insert()
        out = pricing.price(code)["data"]
        # net 10 g (gross - stone) x 100 = 1000; wastage 5% = 50; making 10 x 10 = 100
        self.assertEqual((out["metal_value"], out["wastage"], out["making_charge"], out["total"]), (1000, 50, 100, 1150))

    def test_missing_rate_is_an_error(self) -> None:
        from zatgo_core.industries.jewellery import service

        _set_industries("jewellery")
        with self.assertRaises(frappe.ValidationError):
            service.latest_rate("Platinum", "950", "2001-01-01")

    def test_api_blocked_where_off(self) -> None:
        from zatgo_core.api.v1.jewellery import pricing

        with self.assertRaises(frappe.PermissionError):
            pricing.rate("Gold", "22K")


class TestRestaurantIndustry(IndustryTestBase):
    def test_restaurant_patch_enables_only_where_used(self) -> None:
        from zatgo_core.patches.v0_4_0 import enable_restaurant_where_used as patch_mod

        with patch.object(frappe.db, "count", return_value=0):
            patch_mod.execute()
        self.assertFalse(gate.is_enabled("restaurant"))
        with patch.object(frappe.db, "count", return_value=3):
            patch_mod.execute()
        frappe.clear_document_cache(SETTINGS, SETTINGS)
        self.assertTrue(gate.is_enabled("restaurant"))
        self.assertFalse(gate.is_enabled("gym"))

    def test_resto_documents_nobodys_where_off(self) -> None:
        self.assertEqual(gate.industry_query_conditions("u", "ZG Table"), "1=0")
        _set_industries("restaurant")
        self.assertEqual(gate.industry_query_conditions("u", "ZG Table"), "")

    def test_sync_is_idempotent(self) -> None:
        _set_industries("restaurant")
        sync_industries()
        sync_industries()
        self.assertEqual(frappe.db.count("Workspace", {"name": "ZatGo Restaurant"}), 1)


class TestZatGoDeskEntry(IndustryTestBase):
    def test_zatgo_entry_survives_migrate_purge(self) -> None:
        from zatgo_core.install import after_migrate

        after_migrate()
        self.assertTrue(frappe.db.exists("Workspace", "ZatGo"))
        self.assertTrue(frappe.db.exists("Workspace Sidebar", "ZatGo"))
        icon = frappe.db.get_value("Desktop Icon", "ZatGo", ["link_type", "link_to", "hidden"], as_dict=True)
        self.assertEqual((icon.link_type, icon.link_to, icon.hidden), ("Workspace Sidebar", "ZatGo", 0))
        items = frappe.get_doc("Workspace Sidebar", "ZatGo").items
        self.assertIn("ZG System Settings", [i.link_to for i in items])

    def test_zatgo_entry_is_rebuilt_from_nothing(self) -> None:
        # Fresh install: the synced Workspace may be missing (its roles do not
        # exist yet when Frappe imports it) -- ensure_core_desk brings it back.
        from zatgo_core.setup.ensure_core_desk import ensure_core_desk

        for dt in ("Desktop Icon", "Workspace Sidebar", "Workspace"):
            if frappe.db.exists(dt, "ZatGo"):
                frappe.delete_doc(dt, "ZatGo", force=1, ignore_permissions=True)
        ensure_core_desk()
        for dt in ("Workspace", "Workspace Sidebar", "Desktop Icon"):
            self.assertTrue(frappe.db.exists(dt, "ZatGo"), dt)


class TestTextileIndustry(IndustryTestBase):
    def test_enable_shows_item_fields_and_workspace(self) -> None:
        _set_industries("textile")
        for fn in ("zg_textile_fabric", "zg_textile_roll_length", "zg_textile_width"):
            self.assertEqual(frappe.db.get_value("Custom Field", {"dt": "Item", "fieldname": fn}, "hidden"), 0, fn)
        self.assertTrue(frappe.db.exists("Workspace", "ZatGo Textile"))

    def test_fields_saved_on_item_and_hidden_when_off(self) -> None:
        _set_industries("textile")
        code = f"TX-{random_string(5)}"
        frappe.get_doc(
            {
                "doctype": "Item",
                "item_code": code,
                "item_name": code,
                "item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name") or "All Item Groups",
                "stock_uom": "Nos",
                "is_stock_item": 0,
                "zg_textile_fabric": "Cotton",
                "zg_textile_is_roll": 1,
                "zg_textile_roll_length": 50,
                "zg_textile_width": 150,
            }
        ).insert(ignore_permissions=True)
        self.assertEqual(frappe.db.get_value("Item", code, ["zg_textile_fabric", "zg_textile_roll_length"]), ("Cotton", 50))
        _set_industries()
        self.assertEqual(frappe.db.get_value("Custom Field", {"dt": "Item", "fieldname": "zg_textile_fabric"}, "hidden"), 1)
        self.assertFalse(frappe.db.exists("Workspace", "ZatGo Textile"))
        self.assertEqual(frappe.db.get_value("Item", code, "zg_textile_fabric"), "Cotton")  # data kept

    def test_no_special_roles_or_gated_doctypes(self) -> None:
        self.assertEqual(registry.INDUSTRIES["textile"].doctypes, ())
