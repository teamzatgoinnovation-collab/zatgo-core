"""Enabled Industry child table controller (rows of ZatGo System Settings -> Industries)."""

from __future__ import annotations

from frappe.model.document import Document


class EnabledIndustry(Document):
    """One row per registered industry (zatgo_core/industries/registry.py)."""

    pass
