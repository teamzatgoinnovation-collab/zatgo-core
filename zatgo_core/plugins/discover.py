"""Discover bundled (and future hook-provided) manifests and register them."""

from __future__ import annotations

from zatgo_core.plugins.manifests import BUNDLED_MANIFESTS
from zatgo_core.services.plugin_registry_service import PluginRegistryService
from zatgo_core.utils.logging import get_logger

logger = get_logger("system")


def discover_and_register_manifests() -> dict[str, int]:
    """Register all bundled Phase-1 manifests into the plugin registry."""
    registered = 0
    for manifest in BUNDLED_MANIFESTS:
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
