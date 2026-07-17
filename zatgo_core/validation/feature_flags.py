"""Validation for ZG Feature Flag."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import frappe

from zatgo_core.constants.settings import FEATURE_FLAG_STATUSES

if TYPE_CHECKING:
    from frappe.model.document import Document

_FLAG_KEY_RE = re.compile(r"^[a-z][a-z0-9_.-]*$")


def validate_feature_flag(doc: Document) -> None:
    """Validate flag key format and status."""
    if not doc.flag_key:
        frappe.throw(frappe._("Flag Key is required"))
    if not _FLAG_KEY_RE.match(doc.flag_key):
        frappe.throw(
            frappe._(
                "Flag Key must be lowercase snake/dot notation starting with a letter"
            )
        )
    if doc.status not in FEATURE_FLAG_STATUSES:
        frappe.throw(frappe._("Invalid feature flag status"))
    if doc.rollout_percent is not None and not (0 <= int(doc.rollout_percent) <= 100):
        frappe.throw(frappe._("Rollout Percent must be between 0 and 100"))
