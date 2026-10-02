# Copyright (c) 2026, ZatGo Innovation and contributors
# For license information, please see license.txt

from __future__ import annotations

from frappe.model.document import Document


class ZGVanSaleProfile(Document):
    # Invoice/return naming series used to live here (VanSale API only); they
    # are now per user + company in ZG Sales Invoice Naming Settings, enforced
    # for every Sales Invoice (patches/v0_2_3/move_van_profile_series_to_naming_rules).
    pass
