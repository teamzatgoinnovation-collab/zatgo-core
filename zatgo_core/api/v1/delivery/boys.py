"""Delivery boys — ZG Delivery Boy DocType + linked ERPNext User (role: Delivery)."""

from __future__ import annotations

import re
from typing import Any

import frappe

from zatgo_core.api.response import ok
from zatgo_core.api.validators import require_login
from zatgo_core.constants.roles import ROLES
from zatgo_core.services.erpnext_reads import get_zg, list_zg
from zatgo_core.setup.ensure_roles import ensure_roles

DELIVERY_ROLE = ROLES["DELIVERY"]


def _map(row: Any) -> dict[str, Any]:
    r = row.as_dict() if callable(getattr(row, "as_dict", None)) else dict(row)
    user = r.get("user")
    username = None
    if user and frappe.db.exists("User", user):
        username = frappe.db.get_value("User", user, "username") or user
    points = int(r.get("points") or 0)
    return {
        "id": r.get("name"),
        "name": r.get("full_name") or r.get("name"),
        "full_name": r.get("full_name"),
        "code": r.get("code"),
        "phone": r.get("phone"),
        "status": r.get("status"),
        "user": user,
        "username": username,
        "vehicle": r.get("vehicle"),
        "notes": r.get("notes"),
        "points": points,
        "deliveries_done": int(r.get("deliveries_done") or 0),
        # 1 bonus star per 50 points
        "bonus": points // 50,
        "last_lat": r.get("last_lat"),
        "last_lng": r.get("last_lng"),
        "last_seen_at": str(r.get("last_seen_at") or "") or None,
    }


def _require_doctype() -> None:
    if not frappe.db.exists("DocType", "ZG Delivery Boy"):
        frappe.throw("ZG Delivery Boy DocType is not installed — migrate zatgo_core")


def _next_code() -> str:
    existing = frappe.get_all("ZG Delivery Boy", fields=["code"], limit_page_length=500)
    max_n = 0
    for row in existing:
        code = (row.get("code") or "").strip().upper()
        if code.startswith("DB-"):
            try:
                max_n = max(max_n, int(code[3:]))
            except ValueError:
                continue
    return f"DB-{max_n + 1:03d}"


def _split_name(full_name: str) -> tuple[str, str]:
    parts = full_name.strip().split(None, 1)
    if not parts:
        return "Delivery", "Boy"
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


def _normalize_username(username: str) -> str:
    raw = (username or "").strip().lower()
    if not raw:
        frappe.throw("username is required")
    # Allow email-as-username or simple login ids
    if "@" in raw:
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", raw):
            frappe.throw("Invalid username email format")
        return raw
    if not re.match(r"^[a-z0-9._-]{3,64}$", raw):
        frappe.throw(
            "username must be 3–64 chars: letters, numbers, dot, underscore, or hyphen"
        )
    return raw


def _email_for_username(username: str, email: str | None) -> str:
    if email and email.strip():
        return email.strip().lower()
    if "@" in username:
        return username
    return f"{username}@delivery.local"


def _ensure_delivery_role() -> None:
    ensure_roles()
    if not frappe.db.exists("Role", DELIVERY_ROLE):
        frappe.get_doc(
            {
                "doctype": "Role",
                "role_name": DELIVERY_ROLE,
                "desk_access": 1,
                "is_custom": 1,
            }
        ).insert(ignore_permissions=True)


def _create_delivery_user(
    *,
    full_name: str,
    username: str,
    password: str,
    email: str | None = None,
    phone: str | None = None,
) -> str:
    """Create ERPNext User with Delivery role. Returns User name (email)."""
    _ensure_delivery_role()

    uname = _normalize_username(username)
    mail = _email_for_username(uname, email)
    pwd = (password or "").strip()
    if len(pwd) < 6:
        frappe.throw("password must be at least 6 characters")

    if frappe.db.exists("User", mail):
        frappe.throw(f"User {mail} already exists")

    # Username uniqueness (when not using email as name)
    if frappe.db.exists("User", {"username": uname}):
        frappe.throw(f"Username {uname} is already taken")

    first, last = _split_name(full_name)
    login_username = uname if "@" not in uname else uname.split("@")[0]
    user = frappe.get_doc(
        {
            "doctype": "User",
            "email": mail,
            "first_name": first,
            "last_name": last or None,
            "username": login_username,
            "mobile_no": phone or None,
            "send_welcome_email": 0,
            "user_type": "System User",
            "enabled": 1,
            "new_password": pwd,
        }
    )
    user.flags.ignore_password_policy = True
    # Role before insert avoids "no roles enabled" system message
    user.append("roles", {"role": DELIVERY_ROLE})
    user.insert(ignore_permissions=True)
    # Ensure role + password persist even if insert hooks strip them
    user.add_roles(DELIVERY_ROLE)
    user.reload()
    if not user.enabled:
        user.enabled = 1
        user.save(ignore_permissions=True)
    return user.name


@frappe.whitelist()
def list(page: int | str = 1, page_size: int | str = 20) -> dict[str, Any]:
    return list_zg(
        "ZG Delivery Boy",
        fields=[
            "name",
            "full_name",
            "code",
            "phone",
            "status",
            "user",
            "vehicle",
            "notes",
            "points",
            "deliveries_done",
            "last_lat",
            "last_lng",
            "last_seen_at",
        ],
        page=page,
        page_size=page_size,
        map_row=_map,
    )


@frappe.whitelist()
def get(name: str) -> dict[str, Any]:
    return get_zg("ZG Delivery Boy", name, map_doc=lambda d: _map(d))


@frappe.whitelist()
def create(
    full_name: str,
    username: str,
    password: str,
    code: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    vehicle: str | None = None,
) -> dict[str, Any]:
    """Create ZG Delivery Boy + ERPNext User with role Delivery."""
    require_login()
    frappe.has_permission("ZG Delivery Boy", "create", throw=True)
    if not frappe.has_permission("User", "create"):
        frappe.throw(
            "Your ERPNext user cannot create Users — need permission to create delivery logins",
            frappe.PermissionError,
        )
    _require_doctype()

    boy_name = (full_name or "").strip()
    if not boy_name:
        frappe.throw("full_name is required")

    boy_code = (code or "").strip() or _next_code()
    boy_phone = (phone or "").strip() or None
    boy_vehicle = (vehicle or "").strip() or None

    if frappe.db.exists("ZG Delivery Boy", {"code": boy_code}):
        frappe.throw(f"Delivery boy code {boy_code} already exists")

    if boy_vehicle and not frappe.db.exists("ZG Vehicle", boy_vehicle):
        boy_vehicle = None

    user_name = _create_delivery_user(
        full_name=boy_name,
        username=username,
        password=password,
        email=email,
        phone=boy_phone,
    )

    doc = frappe.get_doc(
        {
            "doctype": "ZG Delivery Boy",
            "full_name": boy_name,
            "code": boy_code,
            "phone": boy_phone,
            "status": "Available",
            "user": user_name,
            "vehicle": boy_vehicle,
        }
    )
    doc.insert()
    frappe.db.commit()
    return ok(
        _map(doc),
        meta={
            "stub": False,
            "created": True,
            "source": "ZG Delivery Boy",
            "role": DELIVERY_ROLE,
            "user": user_name,
        },
    )


@frappe.whitelist()
def ensure(
    full_name: str | None = None,
    code: str | None = None,
    phone: str | None = None,
    username: str | None = None,
    password: str | None = None,
    email: str | None = None,
) -> dict[str, Any]:
    """Return existing boy by code, or create with User credentials when provided.

    No-args: boy linked to the logged-in User (Delivery app). Never invents a boy.
    """
    require_login()
    _require_doctype()

    boy_name = (full_name or "").strip()
    boy_code = (code or "").strip()
    boy_phone = (phone or "").strip() or None

    if boy_code:
        existing = frappe.db.exists("ZG Delivery Boy", {"code": boy_code})
        if existing:
            doc = frappe.get_doc("ZG Delivery Boy", existing)
            return ok(
                _map(doc),
                meta={"stub": False, "created": False, "source": "ZG Delivery Boy"},
            )

    if not boy_name:
        # Delivery app bootstrap: only the boy linked to the logged-in User.
        # Never invent the first boy — that filters the wrong route and shows empty stops.
        session_user = (frappe.session.user or "").strip()
        if not session_user or session_user == "Guest":
            frappe.throw("Login required", frappe.PermissionError)

        linked = frappe.db.get_value(
            "ZG Delivery Boy", {"user": session_user}, "name"
        )
        if linked:
            doc = frappe.get_doc("ZG Delivery Boy", linked)
            return ok(
                _map(doc),
                meta={
                    "stub": False,
                    "created": False,
                    "source": "ZG Delivery Boy",
                    "matched_by": "session_user",
                },
            )

        frappe.throw(
            "No delivery boy linked to your login. "
            "Sign in with the courier email/password from POS → Couriers "
            "(or open Desk and set User on the ZG Delivery Boy).",
            frappe.DoesNotExistError,
        )

    if not (username or "").strip() or not (password or "").strip():
        frappe.throw("username and password are required to create a delivery boy")

    return create(
        full_name=boy_name,
        username=username or "",
        password=password or "",
        code=boy_code or None,
        phone=boy_phone,
        email=email,
    )
