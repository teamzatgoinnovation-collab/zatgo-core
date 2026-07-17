"""Scheduler / background jobs for ZatGo Core."""

from __future__ import annotations

from zatgo_core.utils.logging import get_logger

logger = get_logger("system")


def sync_application_registry() -> None:
    """No-op placeholder (client apps are site settings, not Frappe app sync)."""
    logger.info(
        "scheduler sync_application_registry skipped — "
        "use ZG Application Settings for Electron/Flutter/Web clients"
    )


def daily() -> None:
    """Daily maintenance entrypoint."""
    logger.info("zatgo_core daily job ok")
