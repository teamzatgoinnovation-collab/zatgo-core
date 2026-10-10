"""Logging helpers for ZatGo Space."""

from __future__ import annotations

import frappe


def get_logger():
    """Return the app-scoped Frappe logger."""
    return frappe.logger("zatgo_space")
