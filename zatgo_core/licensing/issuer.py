"""Issuer mode: the one internal ZatGo site where editions are written (and, from Phase 5, licences signed).

A site is the issuer when its `site_config.json` has `"zg_licence_issuer": 1` -- a file only the bench user can
write, so no in-site user (System Manager or Administrator) can make a customer site an issuer (decision D2).
On every other site editions are read-only: there they are only templates the vendor already turned into licences.
"""

from __future__ import annotations

import frappe
from frappe import _

CONF_KEY = "zg_licence_issuer"


def is_issuer_site() -> bool:
    value = frappe.conf.get(CONF_KEY)
    return value in (1, True, "1", "true", "True")


def require_issuer() -> None:
    if not is_issuer_site():
        frappe.throw(
            _("Editions are created and changed on the ZatGo licence issuer site only."),
            frappe.PermissionError,
            title=_("Not the issuer site"),
        )


def require_issuer_manager() -> None:
    """Issuer site + System Manager: who may change editions."""
    require_issuer()
    if frappe.session.user != "Administrator" and "System Manager" not in frappe.get_roles():
        frappe.throw(_("Only a System Manager can change editions."), frappe.PermissionError)
