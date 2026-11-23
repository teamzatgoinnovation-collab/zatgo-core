"""ZatGo ERP: the Workspace is the source of the sidebar (services/erp_workspace.py, services/app_sidebar.py).

An administrator adds a DocType / Page / Report by editing the workspace; the sidebar follows when it is saved, a release
adds new default items once without undoing what the site changed, and a repeated sync changes nothing."""

from __future__ import annotations

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase

from zatgo_core.services import erp_workspace

NAME = erp_workspace.NAME
EXTRA = "Stock Balance"  # a Report that is not a default item


def _sidebar() -> list[tuple]:
    return [(r.type, r.label, r.link_type, r.link_to, int(r.child or 0)) for r in frappe.get_doc("Workspace Sidebar", NAME).items]


def _forget(marker: str) -> None:
    """A set_global(key, 0) still reads as set (the stored value is the string "0"): drop the row."""
    frappe.db.delete("DefaultValue", {"parent": "__global", "defkey": marker})
    frappe.clear_cache()  # get_global reads Frappe's cached defaults


def _links(label: str) -> list[str]:
    """The labels of the sidebar rows under the section [label]."""
    out, inside = [], False
    for typ, lab, _lt, _to, _child in _sidebar():
        if typ == "Section Break":
            inside = lab == label
        elif inside:
            out.append(lab)
    return out


def _counts(ws) -> dict[str, tuple[int, int]]:
    """Card label -> (link_count on the Card Break, links really under it)."""
    out, current = {}, None
    for r in ws.links:
        if r.type == "Card Break":
            current = r.label
            out[current] = [r.link_count or 0, 0]
        elif current:
            out[current][1] += 1
    return {k: tuple(v) for k, v in out.items()}


def _recount(ws) -> None:
    current = None
    for r in ws.links:
        if r.type == "Card Break":
            current = r
            current.link_count = 0
        elif current:
            current.link_count += 1


class TestErpWorkspaceSidebar(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        frappe.set_user("Administrator")
        erp_workspace.sync_erp_desk()

    def tearDown(self) -> None:
        # leave the site as it was: the default items back in, the test report out
        ws = frappe.get_doc("Workspace", NAME)
        ws.links = [r for r in ws.links if not (r.link_type == "Report" and r.link_to == EXTRA)]
        _recount(ws)
        ws.save(ignore_permissions=True)
        _forget("zg_erp_ws_doctype_payment_reconciliation")
        erp_workspace.sync_erp_desk()
        frappe.db.rollback()

    def test_sidebar_is_home_dashboard_then_the_cards(self):
        rows = _sidebar()
        self.assertEqual(rows[0][1:4], ("Home", "Workspace", NAME))
        self.assertEqual(rows[1][1:4], ("Dashboard", "Dashboard", erp_workspace.DASHBOARD))
        self.assertEqual([r[1] for r in rows if r[0] == "Section Break"], [s[0] for s in erp_workspace.SECTIONS])
        self.assertIn("Sales Invoice", _links("Transactions"))

    def test_a_report_added_in_the_workspace_reaches_the_sidebar_on_save(self):
        ws = frappe.get_doc("Workspace", NAME)
        self.assertTrue(erp_workspace._add_link(ws, "Reports", {"label": "Stock Balance", "link_type": "Report", "link_to": EXTRA, "ref_doctype": "Bin", "is_query_report": 1}))
        ws.save(ignore_permissions=True)  # the Desk editor saves the same way -> doc_events -> sidebar sync
        self.assertIn("Stock Balance", _links("Reports"))
        have, real = _counts(frappe.get_doc("Workspace", NAME))["Reports"]
        self.assertEqual(have, real)  # the Card Break's link_count follows (the editor's own clean-up relies on it)

    def test_a_default_item_the_site_deleted_is_not_brought_back(self):
        ws = frappe.get_doc("Workspace", NAME)
        ws.links = [r for r in ws.links if r.link_to != "Payment Reconciliation"]
        _recount(ws)
        ws.save(ignore_permissions=True)
        self.assertNotIn("Payment Reconciliation", _links("Transactions"))
        erp_workspace.sync_erp_desk()
        erp_workspace.ensure_default_items()
        self.assertNotIn("Payment Reconciliation", [r.link_to for r in frappe.get_doc("Workspace", NAME).links])
        self.assertNotIn("Payment Reconciliation", _links("Transactions"))

    def test_a_new_default_item_is_added_once(self):
        ws = frappe.get_doc("Workspace", NAME)
        ws.links = [r for r in ws.links if r.link_to != "Payment Reconciliation"]
        _recount(ws)
        ws.save(ignore_permissions=True)
        _forget("zg_erp_ws_doctype_payment_reconciliation")  # "this release ships it, the site never had it"
        erp_workspace.ensure_default_items()
        self.assertIn("Payment Reconciliation", [r.link_to for r in frappe.get_doc("Workspace", NAME).links])
        erp_workspace.sync_erp_desk()
        self.assertIn("Payment Reconciliation", _links("Transactions"))

    def test_a_repeated_sync_changes_nothing(self):
        before = _sidebar()
        erp_workspace.sync_erp_desk()
        erp_workspace.sync_erp_desk()
        self.assertEqual(_sidebar(), before)
        self.assertEqual(frappe.db.count("Workspace Sidebar", {"name": NAME}), 1)
