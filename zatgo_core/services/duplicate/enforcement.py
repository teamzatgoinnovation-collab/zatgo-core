"""Server-side enforcement: one doc_events `validate` hook for every supported DocType.

Runs for Desk, REST, Data Import, the mobile / POS APIs -- anything that goes through `Document.insert/save`.
Block on strong matches (configurable), warn on possible ones, never act on fuzzy suggestions. An authorized
override (role + reason) is logged. For exact unique identifiers the check-then-insert is serialised with a
named DB lock held until the transaction ends, and re-read with locking reads, so two concurrent requests
cannot both pass.
"""

from __future__ import annotations

import hashlib
from typing import Any

import frappe
from frappe import _
from frappe.utils import escape_html

from zatgo_core.services.duplicate import config, matcher, normalizers

LOCK_WAIT_SECONDS = 10
_OVERRIDE_TTL = 600


class DuplicateRecordError(frappe.ValidationError):
    http_status_code = 409


def _skip() -> bool:
    flags = frappe.flags
    return bool(flags.in_migrate or flags.in_install or flags.in_patch or flags.in_uninstall)


def _signature(rule: dict[str, Any], values: dict[str, Any]) -> frozenset:
    sig = set()
    for spec in rule["fields"]:
        for raw in matcher._inputs(spec, values):
            sig.add((spec["fieldname"], normalizers.normalize(spec["kind"], raw)))
    return frozenset(sig)


def validate_document(doc, method: str | None = None) -> None:
    """doc_events handler (validate)."""
    if _skip():
        return
    rule = config.rule_for(doc.doctype)
    if not rule or doc.get("is_return"):
        return
    try:
        values = doc.as_dict()
        before = None if doc.is_new() else doc.get_doc_before_save()
        if before is not None and _signature(rule, before.as_dict()) == _signature(rule, values):
            return  # nothing identifying changed -- existing (legacy) duplicates never block unrelated edits
        exclude = None if doc.is_new() else doc.name
        _acquire_locks(doc.doctype, rule, values)
        found = matcher.find_matches(doc.doctype, values, exclude, rule=rule, fresh=True)
    except frappe.ValidationError:
        raise
    except Exception as e:
        if _is_snapshot_conflict(e):
            # MariaDB (innodb_snapshot_isolation) refuses a locking read of a matching row that another request
            # committed after this transaction's snapshot -- i.e. exactly the concurrent duplicate we guard against.
            frappe.throw(
                _("A record with the same identifier was just created by another request. Please refresh and check before saving."),
                exc=DuplicateRecordError,
                title=_("Duplicate record"),
            )
        frappe.log_error(title="Duplicate prevention check failed (save allowed)")
        return
    _apply(doc, rule, found)


def _is_snapshot_conflict(error: Exception) -> bool:
    """MariaDB error 1020 (ER_CHECKREAD): record changed since last read. Frappe re-raises it as QueryDeadlockError."""
    return "1020" in str(error.args[:1]) if error.args else False


def _apply(doc, rule: dict[str, Any], found: list[dict[str, Any]]) -> None:
    strong = [m for m in found if m["level"] == matcher.STRONG]
    possible = [m for m in found if m["level"] == matcher.POSSIBLE]
    if strong:
        _act(doc, rule, strong, rule["strong_action"], matcher.STRONG)
    if possible and not strong:
        _act(doc, rule, possible, rule["possible_action"], matcher.POSSIBLE)


def _act(doc, rule, matches, action: str, level: str) -> None:
    if action == "Ignore":
        return
    message = render_message(doc.doctype, rule, matches, level)
    if action == "Warn":
        frappe.msgprint(message, title=_("Possible duplicate"), indicator="orange")
        return
    if _override_accepted(doc, rule, matches, level):
        return
    frappe.throw(message, exc=DuplicateRecordError, title=_("Duplicate record"))


def render_message(doctype: str, rule, matches, level: str) -> str:
    shown = matcher.present(doctype, matches, rule)
    head = (
        _("A matching {0} already exists.") if level == matcher.STRONG else _("A similar {0} may already exist. Please verify before saving.")
    ).format(_(doctype))
    lines = []
    for item in shown:
        if item["restricted"]:
            lines.append(_("A matching record that you cannot view ({0} match)").format(_(item["level"])))
            continue
        fields = ", ".join(sorted({m["field"] for m in item["matched_on"]}))
        details = "; ".join(f"{escape_html(str(d['label']))}: {escape_html(str(d['value']))}" for d in item["details"])
        lines.append(f"<b>{escape_html(item['name'])}</b> — {escape_html(str(item['title']))} ({escape_html(fields)})" + (f"<br>{details}" if details else ""))
    return escape_html(head) + "<br>" + "<br>".join(lines)


# --- authorized override -------------------------------------------------------------------------

def _override_key(doctype: str) -> str:
    return f"zg_dup_override:{frappe.session.user}:{doctype}"


def can_override(rule: dict[str, Any]) -> bool:
    return bool(set(frappe.get_roles()) & set(config.override_roles(rule)))


def register_override(doctype: str, names: list[str], reason: str) -> None:
    """Remember (10 min, this user) that the user accepted these existing records as non-duplicates."""
    frappe.cache.set_value(_override_key(doctype), {"names": sorted(names), "reason": reason or ""}, expires_in_sec=_OVERRIDE_TTL)


def _override_accepted(doc, rule, matches, level) -> bool:
    if not can_override(rule):
        return False
    names = {m["name"] for m in matches}
    token = frappe.cache.get_value(_override_key(doc.doctype)) or {}
    requested = bool(doc.flags.get("zg_duplicate_override") or frappe.form_dict.get("zg_duplicate_override"))
    if requested:
        reason = doc.flags.get("zg_duplicate_override_reason") or frappe.form_dict.get("zg_duplicate_override_reason") or ""
    elif names <= set(token.get("names") or ()):
        reason = token.get("reason", "")
    else:
        return False
    if config.settings()["override_needs_reason"] and not str(reason).strip():
        return False
    frappe.cache.delete_value(_override_key(doc.doctype))
    log = frappe.get_doc({
        "doctype": "ZG Duplicate Override Log",
        "ref_doctype": doc.doctype,
        "ref_name": doc.name,
        "user": frappe.session.user,
        "matched_records": ", ".join(sorted(names)),
        "level": level,
        "reason": reason,
    })
    log.insert(ignore_permissions=True)  # same transaction as the save -- both stand or both roll back
    return True


# --- concurrency ---------------------------------------------------------------------------------

def lock_name(doctype: str, kind: str, key: str) -> str:
    digest = hashlib.md5(f"{frappe.local.site}|{doctype}|{kind}|{key}".encode()).hexdigest()
    return f"zgdup:{digest}"  # MariaDB lock names are limited to 64 characters


def _held() -> set:
    """Locks this DB connection holds. Kept on the connection object, not on frappe.local: a named lock belongs to
    the session, and a session that already holds a name gets it again at once -- so the bookkeeping must be per
    connection, whatever else is shared between threads."""
    db = frappe.db
    if getattr(db, "_zg_duplicate_locks", None) is None:
        db._zg_duplicate_locks = set()
    return db._zg_duplicate_locks


def _acquire_locks(doctype: str, rule: dict[str, Any], values: dict[str, Any]) -> None:
    """Named locks on the normalised exact identifiers of this record, held until commit / rollback."""
    names = sorted({
        lock_name(doctype, spec["kind"], normalizers.normalize(spec["kind"], raw))
        for spec in rule["fields"]
        if spec["role"] == "Unique Identifier"
        for raw in matcher._inputs(spec, values)
        if normalizers.normalize(spec["kind"], raw)
    })  # sorted: every request takes them in the same order, so two requests cannot deadlock each other
    held = _held()
    for name in names:
        if name in held:
            continue
        got = frappe.db.sql("select get_lock(%s, %s)", (name, LOCK_WAIT_SECONDS))[0][0]
        if got != 1:
            frappe.throw(_("Another request is creating a record with the same identifier. Please retry."), exc=DuplicateRecordError)
        held.add(name)
    if names and not getattr(frappe.db, "_zg_duplicate_release_registered", False):
        frappe.db._zg_duplicate_release_registered = True
        frappe.db.after_commit.add(release_locks)
        frappe.db.after_rollback.add(release_locks)


def release_locks() -> None:
    held = _held()
    for name in list(held):
        try:
            frappe.db.sql("select release_lock(%s)", (name,))
        except Exception:
            pass
    held.clear()
    frappe.db._zg_duplicate_release_registered = False
