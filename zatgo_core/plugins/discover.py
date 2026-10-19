"""Discover bundled (and future hook-provided) manifests and register them."""

from __future__ import annotations

from zatgo_core.plugins.manifests import BUNDLED_MANIFESTS
from zatgo_core.services import app_catalog
from zatgo_core.services.plugin_registry_service import PluginRegistryService
from zatgo_core.utils.logging import get_logger

logger = get_logger("system")


def catalog_manifests() -> list[dict]:
    """Registry manifests for the app catalog (services/app_catalog.py): every
    module's own app_manifest.py and the core entries -- so a new sub-app is
    registered with no list to edit. Apps with a hand-written manifest in
    BUNDLED_MANIFESTS (e.g. VanSaleX) keep that one."""
    hand_written = {m["app_key"] for m in BUNDLED_MANIFESTS}
    out = []
    for order, app in enumerate(app_catalog.catalog()):
        if app["key"] in hand_written or not app["settings"]:
            continue
        out.append(
            {
                "app_key": app["key"],
                "title": app["label"],
                "version": "0.1.0",
                "icon": app["icon"],
                "category": "Core" if app["group"] in ("core", "industries") else "Apps",
                "menu_order": 100 + order,
                "enabled": 1,
                "visible": 1,
                "roles": ",".join(app["roles"]),
                "depends_on": "",
                "description": app["description"],
                "settings_route": "/app/zg-app-hub",
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
    """Register the bundled manifests and the app catalog into the plugin registry."""
    registered = 0
    for manifest in (*BUNDLED_MANIFESTS, *catalog_manifests()):
        try:
            PluginRegistryService.register_application(
                dict(manifest), ignore_permissions=True
            )
            registered += 1
        except Exception:
            logger.exception(
                "Failed to register manifest %s", manifest.get("app_key")
            )
    logger.info("Registered %s plugin manifests", registered)
    return {"registered": registered}
