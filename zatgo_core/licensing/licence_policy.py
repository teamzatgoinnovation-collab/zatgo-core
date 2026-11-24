"""Time policy of the licence in force (Phase 7): expiry, grace, trial end, clock rollback.

When the site enforces its licence (`zg_licence_enforcement` in site_config):
- **before** the expiry date: normal (the Licence page warns 30 days ahead, a trial 7 days ahead);
- **grace**: from the day after expiry for the licence's `grace_days`: everything still works, every page warns;
- **after the grace**: the site becomes **read-only** through `services/subscription_gate.py` -- the same gate a
  lapsed Space subscription uses (decision D3: the most restrictive of the two wins). Viewing, reports, backups,
  exports and importing a new licence keep working; nothing is deleted.
- **clock rollback**: the highest time this site has seen is kept (global default `zg_licence_clock_hwm`, moved
  forward at most hourly). A server clock more than the tolerance behind it (site_config
  `zg_licence_clock_tolerance_hours`, default 48) makes the site read-only until the clock is right again.
  An offline server's clock is not a trusted time source: this is best effort, and someone with database access
  can reset the mark (docs/licensing.md).

Lifetime and Perpetual licences never expire. `evaluate` is pure; the rest reads the licence and the mark.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Mapping

DEFAULT_TOLERANCE_HOURS = 48
HWM_KEY = "zg_licence_clock_hwm"
TOLERANCE_CONF = "zg_licence_clock_tolerance_hours"
_HWM_STEP = timedelta(hours=1)


def _as_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def evaluate(
    licence: Mapping[str, Any] | None,
    now: datetime,
    hwm: datetime | None = None,
    tolerance_hours: int = DEFAULT_TOLERANCE_HOURS,
) -> dict[str, Any]:
    """{"state": "none" | "ok" | "grace" | "read_only", "reason", "expiry_date", "grace_ends", "days_left"}.

    `licence` needs expiry_date (None = never) and grace_days; `now` and `hwm` are UTC-aware."""
    out: dict[str, Any] = {"state": "none", "reason": None, "expiry_date": None, "grace_ends": None,
                           "days_left": None}
    if not licence:
        return out
    if hwm is not None and now + timedelta(hours=max(0, int(tolerance_hours))) < hwm:
        out.update(state="read_only", reason="clock_rollback")
        return out
    expiry = _as_date(licence.get("expiry_date"))
    if expiry is None:
        out["state"] = "ok"
        return out
    today = now.date()
    grace_ends = expiry + timedelta(days=max(0, int(licence.get("grace_days") or 0)))
    out.update(expiry_date=str(expiry), grace_ends=str(grace_ends))
    if today <= expiry:
        out.update(state="ok", days_left=(expiry - today).days)
    elif today <= grace_ends:
        out.update(state="grace", reason="licence_grace", days_left=(grace_ends - today).days)
    else:
        out.update(state="read_only", reason="licence_expired", days_left=0)
    return out


# -- site side ----------------------------------------------------------------------------------------------

def tolerance_hours() -> int:
    import frappe
    from frappe.utils import cint

    value = frappe.conf.get(TOLERANCE_CONF)
    return DEFAULT_TOLERANCE_HOURS if value in (None, "") else max(0, cint(value))


def high_water_mark() -> datetime | None:
    import frappe

    cached = getattr(frappe.local, "zg_licence_hwm", None)
    if cached is not None:
        return cached or None
    # Read the row itself (not frappe.db.get_default's cache): bump() writes it without clearing any cache.
    raw = frappe.db.get_value("DefaultValue", {"parent": "__default", "defkey": HWM_KEY}, "defvalue")
    value = None
    if raw:
        try:
            value = datetime.fromisoformat(str(raw))
            value = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        except ValueError:
            value = None
    frappe.local.zg_licence_hwm = value or False
    return value


def bump(now: datetime) -> None:
    """Move the mark forward (never back), at most once an hour.

    Written straight to the DefaultValue row -- no document events: a document save would run the read-only gate,
    which asks this policy again (recursion), and on a read-only site the save itself would be refused."""
    import frappe

    if getattr(frappe.local, "zg_licence_bumping", False):
        return
    hwm = high_water_mark()
    if hwm is not None and (now < hwm or now - hwm < _HWM_STEP):
        return
    frappe.local.zg_licence_bumping = True
    try:
        write_mark(now)
    finally:
        frappe.local.zg_licence_bumping = False


def write_mark(when: datetime) -> None:
    """Store the mark as given (no document events, no cache clear). bump() is the only production caller."""
    import frappe

    value = when.isoformat(timespec="seconds")
    name = frappe.db.get_value("DefaultValue", {"parent": "__default", "defkey": HWM_KEY}, "name")
    if name:
        frappe.db.set_value("DefaultValue", name, "defvalue", value, update_modified=False)
    else:
        frappe.get_doc({"doctype": "DefaultValue", "parent": "__default", "parenttype": "__default",
                        "parentfield": "system_defaults", "defkey": HWM_KEY, "defvalue": value}).db_insert()
    frappe.local.zg_licence_hwm = when


def state(now: datetime | None = None) -> dict[str, Any]:
    """The policy for the licence in force; state "none" when enforcement is off or there is no licence."""
    from zatgo_core.licensing import entitlement, licences

    now = now or datetime.now(timezone.utc)
    if not entitlement.enforcement_switch():
        return evaluate(None, now)
    licence = licences.current_terms()
    if licence is None:
        return evaluate(None, now)
    result = evaluate(licence, now, high_water_mark(), tolerance_hours())
    if result["reason"] != "clock_rollback":
        bump(now)
    return result


def read_only_state(now: datetime | None = None) -> dict[str, Any] | None:
    """For subscription_gate: the licence's read-only verdict, or None."""
    result = state(now)
    return result if result["state"] == "read_only" else None
