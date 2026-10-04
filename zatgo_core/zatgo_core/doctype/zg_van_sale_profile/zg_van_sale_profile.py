# Copyright (c) 2026, ZatGo Innovation and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe.model.document import Document


class ZGVanSaleProfile(Document):
    # Invoice/return naming series used to live here (VanSale API only); they
    # are now per user + company in ZG Sales Invoice Naming Settings, enforced
    # for every Sales Invoice (patches/v0_2_3/move_van_profile_series_to_naming_rules).

    def validate(self) -> None:
        # access_overrides can only switch modules/features OFF for this user
        # (services/vansalex_access.py); one row per key.
        seen: set[str] = set()
        for row in self.get("access_overrides") or []:
            if row.access_key in seen:
                frappe.throw(f"Modules & Features row {row.idx}: '{row.access_key}' is listed twice.")
            seen.add(row.access_key)
