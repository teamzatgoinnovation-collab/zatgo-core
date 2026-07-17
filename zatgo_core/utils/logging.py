"""Centralized logging for ZatGo Core."""

from __future__ import annotations

from typing import Any

import frappe


def get_logger(channel: str = "system"):
    """Return a namespaced Frappe logger.

    Channels: system | api | error | security | performance
    """
    return frappe.logger(f"zatgo_core.{channel}")


def log_api(message: str, **context: Any) -> None:
    get_logger("api").info("%s | %s", message, context)


def log_error(message: str, **context: Any) -> None:
    get_logger("error").error("%s | %s", message, context)


def log_security(message: str, **context: Any) -> None:
    get_logger("security").warning("%s | %s", message, context)


def log_performance(message: str, **context: Any) -> None:
    get_logger("performance").info("%s | %s", message, context)
