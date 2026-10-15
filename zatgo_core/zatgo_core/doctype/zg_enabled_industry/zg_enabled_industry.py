"""ZG Enabled Industry child table controller (rows of ZG System Settings -> Industries)."""

from __future__ import annotations

from frappe.model.document import Document


class ZGEnabledIndustry(Document):
    """One row per registered industry (zatgo_core/industries/registry.py)."""

    pass
