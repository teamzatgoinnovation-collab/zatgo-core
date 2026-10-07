"""VanSaleX Settings controller — company-wide defaults for the VanSaleX
mobile app. Per-user overrides live on ZG Van Sale Profile; the effective
values are resolved by zatgo_core.services.vansalex_settings.resolve() and,
for Modules & Features, zatgo_core.services.vansalex_access.effective()."""

from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import cint, flt


class VanSaleXSettings(Document):
    def validate(self) -> None:
        if not 0 <= flt(self.max_discount_percent) <= 100:
            frappe.throw("Max Discount % must be between 0 and 100.")
        if self.default_payment_type == "Credit" and not self.allow_credit_sales:
            frappe.throw("Default Payment Type can't be Credit while credit sales are not allowed.")
        self._validate_access()

    def _validate_access(self) -> None:
        """Rows describe catalog keys only (label/kind/module come from the
        catalog, not the user); bump config_version when any switch changes
        so the app and support can tell configurations apart."""
        from zatgo_core.services.vansalex_access import APP_LOCATION, CATALOG, ROW_KEYS

        seen: set[str] = set()
        for row in self.get("access") or []:
            key = (row.access_key or "").strip()
            if key not in ROW_KEYS:
                frappe.throw(f"Row {row.idx}: unknown module/feature key '{key}'.")
            if key in seen:
                frappe.throw(f"Row {row.idx}: '{key}' is listed twice.")
            seen.add(key)
            kind, label, parent, _default, _derived = CATALOG[key]
            row.label, row.kind, row.parent_module = label, kind, parent or ""
            row.app_location = APP_LOCATION.get(key, "")

        before = self.get_doc_before_save()
        old = {r.access_key: cint(r.enabled) for r in (before.get("access") if before else None) or []}
        new = {r.access_key: cint(r.enabled) for r in self.get("access") or []}
        if old != new:
            self.config_version = cint(self.config_version) + 1
