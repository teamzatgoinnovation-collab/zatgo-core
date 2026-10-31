"""The Settings Map: every app's settings as rows with a control, a scope and a status -- and the one safe way to change one.

`describe()` walks the app catalog (services/app_catalog.py): per app its settings DocTypes -> tabs (Tab Breaks, as in
services/app_page.py) -> sections -> rows. A row says which control shows it (switch, choice, select, number, ...), its
current value, whether that value is stored (a Check on a Single reads 0 when nothing is stored: tabSingles is read, see
services/app_state.py), whether the caller may change it, and what the setting does today (services/settings_notes.py).

`save_field()` changes ONE field through the document's own save, so controller validation, permissions and the audit
trail all run. It never uses frappe.client.set_value or db.set_single_value. App switches are not changed here (they go
through api/v1/app_hub.set_switch), nor are secrets, tables, attachments, hidden or read-only fields.
"""

from __future__ import annotations

import math
from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, strip_html

from zatgo_core import __version__
from zatgo_core.services import app_catalog, app_page, app_state, settings_notes, settings_palette

LAYOUT = {"Section Break", "Column Break", "Tab Break", "HTML", "Button", "Heading", "Fold", "Image", "Geolocation"}
NUMBERS = {"Int", "Float", "Currency", "Percent"}
LONG_TEXT = {"Small Text", "Text", "Long Text", "Text Editor", "Markdown Editor", "HTML Editor", "Code", "JSON"}
MAX_CHOICES = 4  # a Select with at most this many options is a choose-one group, longer ones a dropdown

SCOPE_LABELS = {
    "site": "Site", "company": "Company", "branch": "Branch", "user": "User", "role": "Role",
    "device": "Device", "warehouse": "Warehouse",
}


class SettingsMapError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def route(doctype: str) -> str:
    return "/desk/" + frappe.scrub(doctype).replace("_", "-")


def select_options(df: Any) -> list[str]:
    return [o for o in (df.options or "").split("\n") if o.strip()]


def control_for(df: Any) -> str:
    """Which control shows a field."""
    ft = df.fieldtype
    if ft == "Check":
        return "switch"
    if ft == "Select":
        return "choice" if len(select_options(df)) <= MAX_CHOICES else "select"
    if ft == "Link":
        return "link"
    if ft in NUMBERS:
        return "number"
    if ft == "Password":
        return "password"
    if ft in ("Table", "Table MultiSelect"):
        return "table"
    if ft in ("Attach", "Attach Image"):
        return "attach"
    if ft in LONG_TEXT:
        return "textarea"
    if ft in ("Date", "Time", "Datetime"):
        return ft.lower()
    return "text"


def locked_reason(df: Any) -> str | None:
    """Why a field cannot be changed from the map (None: it can). Independent of the caller."""
    if df.fieldtype in LAYOUT:
        return "layout"
    if df.hidden:
        return "hidden"
    if df.read_only:
        return "read_only"
    if df.fieldtype == "Password":
        return "secret"
    if df.fieldtype in ("Table", "Table MultiSelect"):
        return "table"
    if df.fieldtype in ("Attach", "Attach Image"):
        return "attachment"
    if df.fieldname in app_catalog.switch_fields().values():
        return "app_switch"
    return None


def _stored_fields(doctype: str) -> dict[str, Any]:
    try:
        rows = frappe.db.sql("select field, value from `tabSingles` where doctype = %s", (doctype,))
    except Exception:
        return {}
    return {field: value for field, value in rows}


def _plain(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def _owners() -> dict[str, str]:
    """DocType -> the first app that lists it (that app shows its tabs unless the notes say otherwise)."""
    out: dict[str, str] = {}
    for app in app_catalog.catalog():
        for dt, _label in app["settings"]:
            out.setdefault(dt, app["key"])
    return out


def _row(df: Any, doc: Any, stored: dict[str, Any], writable_doctype: bool, dt: str) -> dict[str, Any]:
    control = control_for(df)
    notes = settings_notes.field(dt, df.fieldname)
    reason = locked_reason(df)
    row: dict[str, Any] = {
        "fieldname": df.fieldname,
        "label": df.label or df.fieldname,
        "fieldtype": df.fieldtype,
        "control": control,
        "description": df.description or None,
        "default": df.default,
        "depends_on": df.depends_on or None,
        "scope": notes["scope"],
        "status": notes["status"],
        "enforced_by": notes["enforced_by"],
        "note": notes["note"],
        "stored": df.fieldname in stored,
        "writable": writable_doctype and reason is None,
        "locked": reason,
    }
    if control in ("choice", "select"):
        row["options"] = select_options(df)
    elif control == "link":
        row["options"] = df.options
    value = doc.get(df.fieldname)
    if control == "switch":
        row["value"] = cint(value)
    elif control == "password":
        from frappe.utils.password import get_decrypted_password

        row["value"] = None
        row["is_set"] = bool(get_decrypted_password(dt, dt, df.fieldname, raise_exception=False))
    elif control == "table":
        row["value"] = None
        row["summary"] = _("{0} rows").format(len(value or []))
        row["open"] = route(dt)
    elif control == "attach":
        row["value"] = None
        row["is_set"] = bool(value)
        row["open"] = route(dt)
    else:
        row["value"] = _plain(value)
    return row


def _describe_doctype(app: dict[str, Any], dt: str, label: str, owners: dict[str, str]) -> dict[str, Any] | None:
    if not frappe.db.exists("DocType", dt) or not frappe.has_permission(dt, "read"):
        return None
    meta = frappe.get_meta(dt)
    doc = frappe.get_single(dt) if meta.issingle else frappe.new_doc(dt)
    stored = _stored_fields(dt)
    writable = bool(frappe.has_permission(dt, "write"))
    tab_owner = settings_notes.doctype(dt).get("tabs") or {}
    default_owner = owners.get(dt)
    tabs: list[dict[str, Any]] = []
    tab: dict[str, Any] | None = None
    section: dict[str, Any] | None = None
    mine = default_owner == app["key"]  # fields before the first Tab Break
    for df in meta.fields:
        if df.fieldtype == "Tab Break":
            owner = tab_owner.get(df.fieldname, default_owner)
            mine = owner == app["key"]
            tab, section = None, None
            if mine and not df.hidden:
                tab = {"key": df.fieldname, "label": df.label or df.fieldname, "sections": []}
                tabs.append(tab)
            continue
        if not mine:
            continue
        if df.fieldtype == "Section Break":
            section = None
            if tab is None:
                tab = {"key": "", "label": label, "sections": []}
                tabs.append(tab)
            section = {"label": df.label or "", "rows": []}
            tab["sections"].append(section)
            continue
        if df.fieldtype in LAYOUT or df.hidden or df.fieldname in app_catalog.switch_fields().values():
            continue
        if tab is None:
            tab = {"key": "", "label": label, "sections": []}
            tabs.append(tab)
        if section is None:
            section = {"label": "", "rows": []}
            tab["sections"].append(section)
        section["rows"].append(_row(df, doc, stored, writable, dt))
    for t in tabs:
        t["sections"] = [s for s in t["sections"] if s["rows"]]
    tabs = [t for t in tabs if t["sections"]]
    if not tabs:
        return None
    return {
        "doctype": dt,
        "label": label,
        "route": route(dt),
        "writable": writable,
        "note": settings_notes.doctype(dt).get("note"),
        "tabs": tabs,
    }


def _counts(settings: list[dict[str, Any]]) -> dict[str, int]:
    out = {"fields": 0, "editable": 0, **{s: 0 for s in settings_notes.STATUSES}}
    for dt in settings:
        for tab in dt["tabs"]:
            for section in tab["sections"]:
                for row in section["rows"]:
                    out["fields"] += 1
                    out["editable"] += 1 if row["writable"] else 0
                    out[row["status"]] += 1
    return out


def _visible(app: dict[str, Any]) -> bool:
    roles = set(frappe.get_roles())
    return frappe.session.user == "Administrator" or bool(roles.intersection(app["roles"]))


def describe(only: str | None = None) -> dict[str, Any]:
    """Every app the caller may see, with its settings. `only` limits it to one app key."""
    on = app_state.switches()
    owners = _owners()
    apps = []
    for app in app_catalog.catalog():
        if only and app["key"] != only:
            continue
        if not _visible(app):
            continue
        settings = [
            d for dt, label in app["settings"] if (d := _describe_doctype(app, dt, label, owners)) is not None
        ]
        shown = {d["doctype"] for d in settings}
        # Settings the caller's roles cannot open (e.g. Chat AI Settings is for its own admins): said, not hidden.
        restricted = [label for dt, label in app["settings"] if dt not in shown and frappe.db.exists("DocType", dt) and not frappe.has_permission(dt, "read")]
        has_switch = bool(app["switch_field"])
        apps.append(
            {
                "key": app["key"],
                "label": app["label"],
                "group": app["group"],
                "icon": app["icon"],
                "description": app["description"],
                "palette": settings_palette.palette(app["color"]),
                "has_switch": has_switch,
                "enabled": bool(on.get(app["key"])) if has_switch else True,
                "scopes": ["site", *app["scoped"]],
                "clients": list(app["clients"]),
                "device": [
                    {"client": client, "items": [{"label": a, "note": b} for a, b in items]}
                    for client, items in app["device"].items()
                ],
                "settings": settings,
                "restricted": restricted,
                "counts": _counts(settings),
            }
        )
    return {
        "version": __version__,
        "scopes": SCOPE_LABELS,
        "statuses": list(settings_notes.STATUSES),
        "apps": apps,
    }


# -- writing ------------------------------------------------------------------------------------------------------


def _coerce(df: Any, value: Any) -> Any:
    ft = df.fieldtype
    if ft == "Check":
        if isinstance(value, str):
            value = value.strip().lower() in ("1", "true", "yes", "on")
        return 1 if value else 0
    if ft in NUMBERS:
        # flt() turns "abc" into 0 and would overwrite a limit silently: parse strictly.
        try:
            number = 0.0 if value in (None, "") else float(str(value).strip())
            if not math.isfinite(number):
                raise ValueError
        except (TypeError, ValueError, OverflowError):
            raise SettingsMapError("invalid_value", _("{0} needs a number").format(df.label))
        if ft == "Int":
            if number != int(number):
                raise SettingsMapError("invalid_value", _("{0} needs a whole number").format(df.label))
            return int(number)
        return number
    if ft == "Select":
        options = select_options(df)
        if (value or "") not in options and not (value in (None, "") and "" in (df.options or "").split("\n")):
            raise SettingsMapError("invalid_value", _("{0}: choose one of {1}").format(df.label, ", ".join(options)))
        return value or ""
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        raise SettingsMapError("invalid_value", _("{0} needs a plain value").format(df.label))
    return str(value)


def save_field(doctype: str, fieldname: str, value: Any) -> dict[str, Any]:
    """Change one field of an app's settings DocType through its document save. Raises SettingsMapError."""
    if doctype not in app_catalog.settings_doctypes() or not frappe.db.exists("DocType", doctype):
        raise SettingsMapError("not_settings", _("{0} is not an app settings DocType").format(doctype))
    if not frappe.has_permission(doctype, "write"):
        raise SettingsMapError("forbidden", _("You may not change {0}").format(doctype))
    meta = frappe.get_meta(doctype)
    if not meta.issingle:
        raise SettingsMapError("not_single", _("{0} is not a single settings form").format(doctype))
    df = meta.get_field(fieldname)
    if df is None:
        raise SettingsMapError("unknown_field", _("{0} has no field {1}").format(doctype, fieldname))
    if reason := locked_reason(df):
        raise SettingsMapError("locked_field", _("{0} cannot be changed here ({1})").format(df.label or fieldname, reason))
    new = _coerce(df, value)
    doc = frappe.get_doc(doctype)
    old = doc.get(fieldname)
    if (cint(old) if df.fieldtype == "Check" else (old if old is not None else "")) == new:
        return {"doctype": doctype, "fieldname": fieldname, "value": new, "changed": False, "stored": fieldname in _stored_fields(doctype)}
    doc.set(fieldname, new)
    try:
        doc.save()
    except frappe.PermissionError as exc:
        frappe.db.rollback()
        frappe.clear_messages()
        raise SettingsMapError("forbidden", strip_html(str(exc)) or _("Not permitted"))
    except frappe.ValidationError as exc:
        frappe.db.rollback()
        message = strip_html(str(exc)) or _("The value was refused")
        frappe.clear_messages()
        raise SettingsMapError("invalid_value", message)
    frappe.clear_document_cache(doctype, doctype)
    return {"doctype": doctype, "fieldname": fieldname, "value": new, "changed": True, "stored": fieldname in _stored_fields(doctype)}
