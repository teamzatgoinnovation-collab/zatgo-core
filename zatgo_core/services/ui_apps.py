"""Per-site UI: the SaaS theme, the language switcher and the VanSaleX web page.

All three used to be separate apps (saas_theme, language_switcher a.k.a.
modifyme, vansalex_web) installed on some sites only. They now ship inside zatgo_core and
are switched on per site in ZG System Settings -> Desk Appearance, so a
site keeps exactly the look it had (patches/v0_2_9/carry_over_ui_apps.py).

Desk assets: a hooks.py `app_include_css/js` would load them on every site
zatgo_core is installed on. Frappe's Desk page (frappe/www/desk.py) also
reads `app_include_css/js` from the site config, so `add_desk_includes` (a
before_request hook) puts them on the request's own config copy when the
site has them switched on -- still in <head>, no flash of the stock look.

Login page: the theme's two-column login is served by `ThemedLoginPage`
(a page_renderer hook) only while the theme is on; otherwise /login is
Frappe's own page.
"""

from __future__ import annotations

import hashlib
import os
from functools import lru_cache

import frappe
from frappe.website.page_renderers.template_page import TemplatePage

SETTINGS = "ZG System Settings"

THEME_CSS = "saas_theme/css/saas_theme.css"
THEME_JS = "saas_theme/js/saas_theme.js"
SWITCHER_CSS = "language_switcher/css/language_switcher.css"
SWITCHER_JS = "language_switcher/js/language_switcher.js"

LOGIN_TEMPLATE = "templates/saas_theme/login.html"


def switches() -> dict[str, bool]:
    """This site's switches; both off when the settings (or the fields, mid
    migrate) aren't there yet."""
    try:
        doc = frappe.get_cached_doc(SETTINGS)
    except Exception:
        return {"saas_theme": False, "language_switcher": False, "vansalex_web": False}
    return {
        "saas_theme": bool(doc.get("enable_saas_theme")),
        "language_switcher": bool(doc.get("enable_language_switcher")),
        "vansalex_web": bool(doc.get("enable_vansalex_web")),
    }


@lru_cache(maxsize=None)
def asset_url(relpath: str) -> str:
    """/assets URL of a file in zatgo_core/public, versioned by its content
    so a deploy is picked up at once (Frappe serves /assets for 12 h)."""
    path = frappe.get_app_path("zatgo_core", "public", relpath)
    try:
        with open(path, "rb") as f:
            version = hashlib.md5(f.read()).hexdigest()[:10]
    except OSError:
        version = "0"
    return f"/assets/zatgo_core/{relpath}?v={version}"


def desk_includes() -> tuple[list[str], list[str]]:
    """(css, js) this site adds to Desk."""
    on = switches()
    css: list[str] = []
    js: list[str] = []
    if on["saas_theme"]:
        css.append(asset_url(THEME_CSS))
        js.append(asset_url(THEME_JS))
    if on["language_switcher"]:
        css.append(asset_url(SWITCHER_CSS))
        js.append(asset_url(SWITCHER_JS))
    return css, js


def add_desk_includes() -> None:
    """before_request hook: only the Desk page (/desk..., /app redirects
    there) reads these; every other request is left alone."""
    request = getattr(frappe.local, "request", None)
    path = (getattr(request, "path", "") or "").strip("/")
    if not (path == "desk" or path.startswith("desk/")):
        return
    css, js = desk_includes()
    if not (css or js):
        return
    conf = frappe.local.conf
    # New lists: frappe.local.conf is a shallow copy of the cached site
    # config, so appending in place would leak into later requests.
    conf["app_include_css"] = [*(conf.get("app_include_css") or []), *css]
    conf["app_include_js"] = [*(conf.get("app_include_js") or []), *js]


class ThemedLoginPage(TemplatePage):
    """/login with the SaaS theme's template, on sites that have it on.
    Context is Frappe's own login context (frappe.www.login.get_context) --
    no copy of any login / auth logic -- plus the full page width the
    two-column layout needs."""

    def can_render(self):
        return self.path == "login" and switches()["saas_theme"]

    def set_template_path(self):
        self.app = "zatgo_core"
        self.app_path = frappe.get_app_path("zatgo_core")
        self.file_dir = os.path.dirname(LOGIN_TEMPLATE)
        self.template_path = LOGIN_TEMPLATE
        self.basepath = os.path.join(self.app_path, self.file_dir)
        self.filename = os.path.basename(LOGIN_TEMPLATE)
        self.basename = os.path.splitext(os.path.join(self.app_path, LOGIN_TEMPLATE))[0]
        self.name = "login"

    def set_pymodule(self):
        # Not a www page: no co-located .py; context comes from update_context.
        self.pymodule_name = None

    def update_context(self):
        from frappe.www.login import get_context as core_login_context

        super().update_context()
        # Never cached: the stock and themed pages share the "login" cache key.
        self.context.no_cache = 1
        data = core_login_context(self.context)
        if data:
            self.context.update(data)
        self.context.full_width = True


def ensure_ui_apps() -> None:
    """after_install / after_migrate: Arabic must be a selectable Language
    where the switcher is on."""
    if switches()["language_switcher"]:
        from zatgo_core.api.v1.language import enable_supported_languages

        enable_supported_languages()
