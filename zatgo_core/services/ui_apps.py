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

# switch key -> ZG System Settings field
SWITCH_FIELDS = {
    "saas_theme": "enable_saas_theme",
    "language_switcher": "enable_language_switcher",
    "vansalex_web": "enable_vansalex_web",
    # Bundled modules (services/bundled_apps.py)
    "chat_ai": "enable_chat_ai",
    "tracker": "enable_tracker",
    "zatgo_space": "enable_zatgo_space",
}


def switches() -> dict[str, bool]:
    """This site's switches; both off when the settings (or the fields, mid
    migrate) aren't there yet."""
    try:
        doc = frappe.get_cached_doc(SETTINGS)
    except Exception:
        return dict.fromkeys(SWITCH_FIELDS, False)
    return {key: bool(doc.get(field)) for key, field in SWITCH_FIELDS.items()}


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


# Old separate apps that still inject their own copy while installed
# (between the migrate that carries their switch over and their uninstall).
OLD_UI_APPS = {"saas_theme": ("saas_theme",), "language_switcher": ("language_switcher", "modifyme")}


def desk_includes() -> tuple[list[str], list[str]]:
    """(css, js) this site adds to Desk."""
    on = switches()
    installed = set(frappe.get_installed_apps())
    for key, old_apps in OLD_UI_APPS.items():
        if installed.intersection(old_apps):
            on[key] = False  # the old app's own hooks load it -- never twice
    css: list[str] = []
    js: list[str] = []
    if on["saas_theme"]:
        css.append(asset_url(THEME_CSS))
        js.append(asset_url(THEME_JS))
    if on["language_switcher"]:
        css.append(asset_url(SWITCHER_CSS))
        js.append(asset_url(SWITCHER_JS))
    from zatgo_core.services.bundled_apps import DESK_ASSETS

    for key, (app_css, app_js) in DESK_ASSETS.items():
        if on.get(key):
            css.extend(asset_url(p) for p in app_css)
            js.extend(asset_url(p) for p in app_js)
    return css, js


# Requests that never render the Desk page.
_NOT_DESK = ("api/", "assets/", "files/", "private/", "socket.io", "backups")


def add_desk_includes() -> None:
    """before_request hook. Only the Desk page (frappe/www/desk.py) reads
    these, but it is served at /desk... and also at "/" itself for a System
    User (the home page resolves to "desk"), so every page request gets them
    -- harmless elsewhere; API / asset / file requests are skipped."""
    request = getattr(frappe.local, "request", None)
    path = (getattr(request, "path", "") or "").strip("/")
    if path.startswith(_NOT_DESK):
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
    """after_install / after_migrate: adopt modules of the old separate apps,
    Arabic selectable where the switcher is on, bundled modules set up /
    taken off the Desk per their switch."""
    _adopt_old_bundled_modules()
    _ensure_bundled_doctypes()
    if switches()["language_switcher"]:
        from zatgo_core.api.v1.language import enable_supported_languages

        enable_supported_languages()
    from zatgo_core.services.bundled_apps import sync_bundled_apps

    sync_bundled_apps()


def _adopt_old_bundled_modules() -> None:
    """Module Defs of the bundled modules on every site, and a site that has
    chat_ai / tracker / zatgo_space installed keeps it:
    its switch goes on and its Module Def moves to zatgo_core (the old app
    is then removed from the site's installed apps without uninstalling --
    uninstall would drop its tables). Decided by the SITE's installed apps
    only: a Module Def tagged with the old app proves nothing, because
    migrate tags new Module Defs from every app in the bench's apps.txt."""
    from zatgo_core.services.bundled_apps import BUNDLED

    installed = set(frappe.get_installed_apps())
    changed = False
    for key, (_folder, module, _names) in BUNDLED.items():
        # The module is zatgo_core's on every site: Module Defs are only made
        # by install-app (never by migrate), and a tag left by the bench's
        # apps.txt is corrected -- without switching anything on.
        app_name = frappe.db.get_value("Module Def", module, "app_name")
        if app_name is None:
            frappe.get_doc(
                {"doctype": "Module Def", "module_name": module, "app_name": "zatgo_core"}
            ).insert(ignore_permissions=True, ignore_if_duplicate=True)
            changed = True
        elif app_name != "zatgo_core":
            frappe.db.set_value("Module Def", module, "app_name", "zatgo_core", update_modified=False)
            changed = True
        if key in installed:
            frappe.db.set_single_value(SETTINGS, SWITCH_FIELDS[key], 1)
            changed = True
    if changed:
        frappe.clear_document_cache(SETTINGS, SETTINGS)
        frappe.clear_cache()


def _ensure_bundled_doctypes() -> None:
    """migrate syncs DocTypes only for the modules in the CACHED module map
    (frappe.local.app_modules): on the first migrate after the bundled
    modules were added to modules.txt it can silently skip all of them. If
    one is missing, rebuild the map and sync zatgo_core again."""
    from frappe.model.sync import sync_for

    if all(frappe.db.exists("DocType", dt) for dt in ("Chat AI Settings", "Tracker Settings", "Space Settings")):
        return
    frappe.cache.delete_value("app_modules")
    try:
        frappe.client_cache.delete_value("installed_app_modules")
    except Exception:
        pass
    frappe.setup_module_map()
    sync_for("zatgo_core", force=False)
    frappe.clear_cache()
