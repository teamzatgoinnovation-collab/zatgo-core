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
        self._validate_accounts()
        # access_overrides can only switch modules/features OFF for this user
        # (services/vansalex_access.py); one row per key.
        seen: set[str] = set()
        for row in self.get("access_overrides") or []:
            if row.access_key in seen:
                frappe.throw(f"Modules & Features row {row.idx}: '{row.access_key}' is listed twice.")
            seen.add(row.access_key)

    def _validate_accounts(self) -> None:
        """Cash / Bank Account: an enabled ledger account of that type, of
        the van warehouse's company. Checked when set or changed, so an
        older value can't block saving the rest of the profile."""
        from zatgo_core.services.vansalex_settings import check_account

        company = frappe.db.get_value("Warehouse", self.warehouse, "company") if self.warehouse else None
        for fieldname, account_type in (("cash_account", "Cash"), ("bank_account", "Bank")):
            if self.has_value_changed(fieldname):
                check_account(self.get(fieldname), account_type, self.meta.get_label(fieldname), company)
