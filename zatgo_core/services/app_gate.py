"""Server-side gate for ZatGo apps: an app that is switched off is not reachable.

One rule for every app in the catalog (services/app_catalog.py) -- the switch itself is read by
services/app_state.py:

- `gate_api` (before_request): a whitelisted method under an app's `api_prefixes` answers 404 while the app
  is off, guests included. Bundled modules also get their module path and their old app's path (clients
  built against the old apps, compat_methods.py).
- `require_app` / `@app_api(key)`: for code that must refuse by itself -- the decorator goes under
  `@frappe.whitelist()`, like industries/gate.py's `@industry_api`, and also demands a login (and roles).

Frontend toggles are not security: this is what makes "off" real. Nothing here touches data -- an app that is
off keeps every record, role and setting.
"""

from __future__ import annotations

import functools
from typing import Any, Callable

import frappe
from frappe import _

from zatgo_core.services import app_catalog, app_state

_METHOD_URLS = ("api/method/", "api/v1/method/", "api/v2/method/")


def requested_method() -> str | None:
    """The dotted whitelisted-method path this request calls (REST path or `cmd`), if any."""
    request = getattr(frappe.local, "request", None)
    path = (getattr(request, "path", "") or "").strip("/")
    for prefix in _METHOD_URLS:
        if path.startswith(prefix):
            return path[len(prefix):]
    form = getattr(frappe.local, "form_dict", None) or {}
    return form.get("cmd") or None


def gate_api() -> None:
    """before_request: a whitelisted method of a switched-off app answers 404."""
    method = requested_method()
    if not method:
        return
    for key, prefixes in app_catalog.api_prefixes().items():
        if method.startswith(prefixes) and not app_state.is_on(key):
            raise frappe.DoesNotExistError(f"{method} is not available on this site")


def require_app(key: str) -> None:
    """Refuse (PermissionError) unless the app is on for this site."""
    if not app_state.is_on(key):
        app = app_catalog.get(key)
        frappe.throw(_("{0} is not enabled on this site.").format(app["label"] if app else key), frappe.PermissionError)


def app_api(key: str, roles: tuple[str, ...] = ()) -> Callable:
    """Decorator for an app's whitelisted method, under @frappe.whitelist(): authenticated, app on, and (when
    `roles` is given) one of those roles or System Manager. DocType permissions still apply inside."""

    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if frappe.session.user == "Guest":
                frappe.throw(_("Login required"), frappe.AuthenticationError)
            require_app(key)
            if roles and not (set(frappe.get_roles()) & (set(roles) | {"System Manager"})):
                frappe.throw(_("Not permitted"), frappe.PermissionError)
            return fn(*args, **kwargs)

        return wrapper

    return deco
