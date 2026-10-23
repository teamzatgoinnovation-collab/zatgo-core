"""Register the app catalog (and the hand-written manifests) into the plugin registry.

The app catalog (services/app_catalog.py) is the source of truth for the apps zatgo_core ships; the plugin
registry (`ZG Registered Application` + `ZG Setting Section`) is a one-way projection of it for config-center
clients, carrying the site's REAL switch state and the app's real version. Hand-written manifests
(plugins/manifests/*.py) describe apps the catalog does not know (POS, Delivery, Kitchen); one the catalog
also lists (VanSaleX) keeps its hand-written sections but takes its title, version and enabled state from the
catalog, so the two never disagree.
"""

from __future__ import annotations

from zatgo_core import __version__
from zatgo_core.plugins.manifests import BUNDLED_MANIFESTS
from zatgo_core.services import app_catalog
from zatgo_core.services.plugin_registry_service import PluginRegistryService
from zatgo_core.services.app_state import switches
from zatgo_core.utils.logging import get_logger

logger = get_logger("system")

# `ZG Registered Application.category` is a Select; catalog groups map onto its options.
PLATFORM_GROUPS = ("core", "industries")
CATEGORY_PLATFORM = "Platform"
CATEGORY_OTHER = "Other"

# Catalog-derived rows: the site's switch is the truth, an admin's edit of `enabled` must not outlive it.
CATALOG_AUTHORITATIVE = ("enabled",)


def _registry_category(app: dict) -> str:
    return CATEGORY_PLATFORM if app["group"] in PLATFORM_GROUPS else CATEGORY_OTHER


def _is_enabled(app: dict, on: dict[str, bool]) -> int:
    """1 for an app with no switch (always on); else this site's switch."""
    return int(bool(on.get(app["key"]))) if app["switch_field"] else 1


def catalog_manifests() -> list[dict]:
    """Registry manifests for the app catalog: every module's own app_manifest.py and the core entries, so
    a new sub-app is registered with no list to edit. An app that also has a hand-written manifest (e.g.
    VanSaleX) keeps its sections and takes the catalog's title, version and enabled state."""
    hand_written = {m["app_key"]: m for m in BUNDLED_MANIFESTS}
    on = switches()
    out = []
    for order, app in enumerate(app_catalog.catalog()):
        base = hand_written.get(app["key"])
        if base is None and not app["settings"]:
            continue  # switch-only apps (Desk theme, language switcher, VanSaleX web) have nothing to configure
        version = app.get("version") or __version__
        if base is not None:
            out.append(
                {
                    **base,
                    "title": app["label"],
                    "version": version,
                    "enabled": _is_enabled(app, on),
                }
            )
            continue
        out.append(
            {
                "app_key": app["key"],
                "title": app["label"],
                "version": version,
                "icon": app["icon"],
                "category": _registry_category(app),
                "menu_order": 100 + order,
                "enabled": _is_enabled(app, on),
                "visible": 1,
                "roles": ",".join(app["roles"]),
                "depends_on": ",".join(app.get("requires") or ()),
                "description": app["description"],
                "settings_route": "/desk/zg-app-hub",
                "sections": [
                    {
                        "section_key": frappe_scrub(dt),
                        "label": label,
                        "icon": "setting",
                        "sort_order": (i + 1) * 10,
                        "link_doctype": dt,
                        "component": "",
                    }
                    for i, (dt, label) in enumerate(app["settings"])
                ],
            }
        )
    return out


def frappe_scrub(name: str) -> str:
    return name.strip().lower().replace(" ", "_").replace("-", "_")


def discover_and_register_manifests() -> dict[str, int]:
    """Register the hand-written manifests the catalog does not own, then the catalog's. Idempotent: a
    re-run changes nothing (and writes no history) unless a manifest or a switch changed."""
    catalog_keys = {a["key"] for a in app_catalog.catalog()}
    batches = (
        ([m for m in BUNDLED_MANIFESTS if m["app_key"] not in catalog_keys], ()),
        (catalog_manifests(), CATALOG_AUTHORITATIVE),
    )
    registered = 0
    changed = 0
    for manifests, authoritative in batches:
        for manifest in manifests:
            try:
                result = PluginRegistryService.register_application(
                    dict(manifest), ignore_permissions=True, authoritative=authoritative
                )
                registered += 1
                changed += int(bool(result.get("changed")))
            except Exception:
                logger.exception("Failed to register manifest %s", manifest.get("app_key"))
    logger.info("Registered %s plugin manifests (%s changed)", registered, changed)
    return {"registered": registered, "changed": changed}
