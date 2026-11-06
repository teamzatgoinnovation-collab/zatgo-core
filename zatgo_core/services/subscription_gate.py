"""Subscription gate: a tenant site whose free trial ended (or whose subscription lapsed) becomes read-only.

The platform (ZatGo Space) owns the subscription. It pushes the state into this site's `site_config.json` as
`zg_subscription` (bench `set-config`) -- a file only the platform's bench user can write, so nobody inside the
site, System Manager and Administrator included, can extend their own trial. The dates travel with the state,
so the site enforces expiry by itself even when a later push is missed.

    {"enforcement_on": 1, "status": "TRIAL", "trial_ends_at": "2026-12-06T10:00:00+00:00",
     "paid_until": null, "site_url": "...", "portal_url": "...", "synced_at": "..."}

No `zg_subscription` (every site that is not a Space customer site, and every Space site before the platform
turns enforcement on) means unrestricted: this is fail-open on purpose, so an unmanaged site is never bricked.

Read-only means: everything can still be viewed, reports and dashboards run, people can log in and pay; every
create / update / delete / submit / cancel / amend / import is refused -- in the Desk, over REST, in custom
endpoints, in integrations and in background jobs. Three layers, because no single hook sees everything:

1. `gate_requests` (before_request): the known write endpoints and `/api/resource` write verbs.
2. `doc_has_permission` (has_permission "*"): a write permission check on any DocType answers no.
3. `enforce_doc_write` (doc_events "*"): every document write, `ignore_permissions` or not -- this is what
   catches custom whitelisted endpoints, integrations and jobs.

Not covered, by design of Frappe: code that writes with raw SQL / `frappe.db.set_value` / `db_set` never runs a
document event. That is the one known bypass (docs/subscription.md).
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from typing import Any

import frappe
from frappe import _

CONF_KEY = "zg_subscription"
GRACE_DAYS = 3

READ_ONLY_STATUSES = {"EXPIRED", "SUSPENDED", "PENDING_PAYMENT", "DELETION_SCHEDULED", "DELETED"}
KNOWN_STATUSES = READ_ONLY_STATUSES | {"TRIAL", "ACTIVE"}

# Document writes that must keep working: logs, queues, caches the platform itself needs to run.
EXEMPT_DOCTYPES = {
    "Error Log", "Activity Log", "Access Log", "Scheduled Job Log", "Version", "Comment", "Communication",
    "Email Queue", "Email Queue Recipient", "Notification Log", "Route History", "Console Log", "Error Snapshot",
    "Prepared Report", "RQ Job", "RQ Worker", "Deleted Document", "Document Share Log", "Log Setting",
    "Integration Request", "Webhook Request Log", "Submission Queue", "Scheduler Event", "Energy Point Log",
    "ZG Audit Log", "Sessions", "Document Follow", "Notification Settings", "View Log", "Email Unsubscribe",
    "Webhook", "OAuth Bearer Token", "OAuth Authorization Code", "Token Cache", "Data Import Log",
    "DocShare",
}
# Writes to these are refused unless the person edits their own record (password, language, preferences).
OWN_RECORD_DOCTYPES = {"User", "User Settings", "ZG User Preferences", "ZG Device Token"}

WRITE_PTYPES = {"write", "create", "delete", "submit", "cancel", "amend", "import", "rename", "mask"}

# Whitelisted methods that write. Reads (get, get_list, get_value, ...) are not listed and stay open.
_WRITE_METHODS = {
    "frappe.client.insert", "frappe.client.insert_many", "frappe.client.save", "frappe.client.set_value",
    "frappe.client.delete", "frappe.client.delete_doc", "frappe.client.submit", "frappe.client.cancel",
    "frappe.client.bulk_update", "frappe.client.rename_doc", "frappe.client.attach_file",
    "frappe.desk.form.save.savedocs", "frappe.desk.form.save.cancel", "frappe.desk.reportview.delete_items",
    "frappe.desk.doctype.bulk_update.bulk_update.submit_cancel_or_update_docs",
    "frappe.core.doctype.data_import.data_import.form_start_import",
    "frappe.core.doctype.data_import.data_import.start_import",
    "frappe.model.workflow.apply_workflow", "frappe.model.rename_doc.update_document_title",
    "frappe.desk.form.document_follow.follow_document", "frappe.handler.upload_file", "upload_file",
    "frappe.desk.form.assign_to.add", "frappe.desk.form.assign_to.add_multiple",
    "frappe.desk.doctype.event.event.send_event_digest",
}
_WRITE_METHOD_PREFIXES = (
    "frappe.desk.doctype.bulk_update.", "frappe.core.doctype.data_import.", "frappe.model.rename_doc.",
)
_REST_WRITE_VERBS = {"POST", "PUT", "PATCH", "DELETE"}
_REST_RESOURCE_PREFIXES = ("api/resource/", "api/v2/document/")


# --- state ---------------------------------------------------------------------------------------------------

def raw_state() -> dict[str, Any] | None:
    """The platform's pushed state, or None for a site the platform does not manage."""
    value = frappe.conf.get(CONF_KEY)
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return None
    return value if isinstance(value, dict) else None


def _parse(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def remaining_days(ends_at: datetime | None, now: datetime) -> int | None:
    """Whole days left, rounded up, never negative: 29 days 23 hours left reads 30; the last hour reads 1."""
    if ends_at is None:
        return None
    return max(0, math.ceil((ends_at - now).total_seconds() / 86400))


def evaluate(state: dict[str, Any] | None, now: datetime | None = None) -> dict[str, Any]:
    """Pure: the effective subscription picture for a pushed state at `now` (UTC). No frappe access."""
    now = now or now_utc()
    if not state or not state.get("enforcement_on"):
        return {"managed": False, "status": None, "read_only": False, "remaining_days": None,
                "trial_ends_at": None, "paid_until": None, "reason": None}

    status = str(state.get("status") or "").upper()
    trial_end = _parse(state.get("trial_ends_at"))
    paid_until = _parse(state.get("paid_until"))
    paid = bool(paid_until and now < paid_until)
    read_only = False
    reason = None

    if status in READ_ONLY_STATUSES:
        read_only, reason = True, status.lower()
    elif status == "TRIAL":
        if trial_end is not None and now >= trial_end and not paid:
            read_only, reason = True, "trial_ended"
    elif status == "ACTIVE":
        if paid_until is not None and now > paid_until + timedelta(days=GRACE_DAYS):
            read_only, reason = True, "payment_overdue"
    elif status not in KNOWN_STATUSES:
        # A state this code does not know is not a reason to lock a customer out.
        status = status or "UNKNOWN"

    effective = status
    if status == "TRIAL" and read_only:
        effective = "EXPIRED"
    return {
        "managed": True,
        "status": effective,
        "read_only": read_only,
        "remaining_days": remaining_days(trial_end, now) if status == "TRIAL" else None,
        "trial_ends_at": trial_end.isoformat() if trial_end else None,
        "paid_until": paid_until.isoformat() if paid_until else None,
        "reason": reason,
    }


def current(now: datetime | None = None) -> dict[str, Any]:
    result = evaluate(raw_state(), now)
    state = raw_state() or {}
    result["site_url"] = state.get("site_url")
    result["portal_url"] = state.get("portal_url")
    return result


def is_read_only() -> bool:
    return bool(current()["read_only"])


def _in_system_context() -> bool:
    flags = frappe.flags
    return bool(flags.in_install or flags.in_migrate or flags.in_patch or flags.in_uninstall
                or getattr(flags, "in_platform_sync", False))


def read_only_message() -> str:
    info = current()
    if info["reason"] == "trial_ended":
        return _("Your ZatGo ERP free trial has ended. This site is read-only: you can still view everything. "
                 "Activate a monthly subscription to continue editing.")
    if info["status"] == "SUSPENDED":
        return _("This site is suspended and read-only. Contact ZatGo support or reactivate your subscription.")
    return _("This site is read-only because its subscription is not active. You can still view everything. "
             "Activate or renew your monthly subscription to continue editing.")


def _refuse(doctype: str | None = None) -> None:
    message = read_only_message()
    if doctype:
        message = f"{message} ({_(doctype)})"
    frappe.throw(message, frappe.PermissionError, title=_("Read-only site"))


# --- layer 1: requests ---------------------------------------------------------------------------------------

def is_write_method(method: str | None) -> bool:
    if not method:
        return False
    return method in _WRITE_METHODS or method.startswith(_WRITE_METHOD_PREFIXES)


def gate_requests() -> None:
    """before_request: refuse the known write endpoints while the site is read-only."""
    request = getattr(frappe.local, "request", None)
    if request is None or not is_read_only():
        return
    path = (getattr(request, "path", "") or "").strip("/")
    verb = (getattr(request, "method", "") or "GET").upper()
    if path.startswith(_REST_RESOURCE_PREFIXES) and verb in _REST_WRITE_VERBS:
        _refuse()
    from zatgo_core.services.app_gate import requested_method

    if is_write_method(requested_method()):
        _refuse()


# --- layer 2: permission checks ------------------------------------------------------------------------------

def _is_own_record(doc: Any) -> bool:
    return frappe.session.user != "Guest" and getattr(doc, "name", None) == frappe.session.user


def _exempt(doctype: str | None, doc: Any = None) -> bool:
    if not doctype or doctype in EXEMPT_DOCTYPES:
        return True
    if doctype == "Contact":
        # Saving a User keeps the Contact that mirrors it in step: the person's own, nobody else's.
        return doc is not None and getattr(doc, "user", None) == frappe.session.user
    if doctype in OWN_RECORD_DOCTYPES:
        return doc is None or _is_own_record(doc) or getattr(doc, "owner", None) == frappe.session.user
    return False


def doc_has_permission(doc: Any = None, ptype: str | None = None, user: str | None = None, **kwargs: Any) -> bool:
    """has_permission "*": True (never None -- that is a denial) unless this is a write on a read-only site."""
    if ptype not in WRITE_PTYPES or _in_system_context():
        return True
    if not is_read_only():
        return True
    return _exempt(getattr(doc, "doctype", None), doc)


# --- layer 3: document events --------------------------------------------------------------------------------

def enforce_doc_write(doc: Any, method: str | None = None, *args: Any, **kwargs: Any) -> None:
    """doc_events "*": refuse any document write on a read-only site, `ignore_permissions` or not."""
    if _in_system_context() or not frappe.conf.get(CONF_KEY):
        return
    if _exempt(getattr(doc, "doctype", None), doc):
        return
    if is_read_only():
        _refuse(getattr(doc, "doctype", None))


def guard_job(fn):
    """Wrap a scheduler job that writes: it does nothing while the site is read-only."""
    import functools

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any):
        if is_read_only():
            return None
        return fn(*args, **kwargs)

    return wrapper


# --- platform push -------------------------------------------------------------------------------------------

def boot_payload() -> dict[str, Any]:
    """What the Desk banner needs; never raises (boot must not break)."""
    try:
        info = current()
        if not info["managed"]:
            return {"managed": False}
        return {k: info[k] for k in ("managed", "status", "read_only", "remaining_days", "trial_ends_at",
                                     "paid_until", "reason", "portal_url", "site_url")}
    except Exception:
        frappe.log_error(title="ZatGo subscription boot payload failed")
        return {"managed": False}
