"""Which MyBis notifications a user asked for. Opt-in: nothing stored means off.

A user's choices are kept as User Defaults (`tabDefaultValue`, one row per key), which already exist on every site, need no
migration and are cleaned up with the user. The admin's limits (`ZG MyBis Settings`) decide which of them can be on at all.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import cint

from zatgo_core.zatgo_core.doctype.zg_mybis_settings import zg_mybis_settings as settings

# pref key -> (label for the app, the admin switch that must be on, or None)
PREFS: dict[str, tuple[str, str | None]] = {
    "sales_invoice": ("A sales invoice is submitted", "invoice_alerts"),
    "purchase_invoice": ("A purchase invoice is submitted", "invoice_alerts"),
    "daily_report": ("Daily report: sales, purchases, receipts, payments and balances", "daily_report"),
    "report_email": ("Also e-mail me the daily report", "report_email"),
}
_PREFIX = "mybis_notify_"


def _key(pref: str) -> str:
    return _PREFIX + pref


def allowed() -> dict[str, bool]:
    """Per pref: may it be on at all, under the admin's limits."""
    admin = settings.policy()["notifications"]
    return {pref: bool(admin[switch]) if switch else True for pref, (_label, switch) in PREFS.items()}


def get(user: str | None = None) -> dict[str, bool]:
    """The user's stored choices, False for anything not chosen (limits are applied by `effective`, not here)."""
    user = user or frappe.session.user
    return {pref: cint(frappe.defaults.get_user_default(_key(pref), user)) == 1 for pref in PREFS}


def effective(user: str | None = None) -> dict[str, bool]:
    """What actually applies: the user's choice, and the admin's limit on it."""
    ok = allowed()
    return {pref: on and ok[pref] for pref, on in get(user).items()}


def save(chosen: dict[str, Any], user: str | None = None) -> dict[str, bool]:
    """Store the pref keys present in `chosen` (unknown keys are ignored) for the user."""
    user = user or frappe.session.user
    for pref in PREFS:
        if pref in chosen:
            frappe.defaults.set_user_default(_key(pref), "1" if cint(chosen[pref]) else "0", user)
    return get(user)


def recipients(pref: str) -> list[str]:
    """Enabled users who turned `pref` on, while the admin's limit allows it."""
    if not allowed().get(pref):
        return []
    users = frappe.get_all("DefaultValue", filters={"defkey": _key(pref), "defvalue": "1", "parenttype": "__default"}, pluck="parent")
    users = [u for u in set(users) if u not in ("__default", "Guest")]
    if not users:
        return []
    return frappe.get_all("User", filters={"name": ("in", users), "enabled": 1}, pluck="name")
